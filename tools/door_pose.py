"""Offline estimator for tools.find_door: scan headings by least squares (loop closure included) and the door from two scans with an honest range interval.

  python -m tools.door_pose data/find_door/<run>/observations.json        # replay a run saved by tools.find_door (prints the estimate as JSON)

Conventions (the same as tools.scan_boards / tools.locate_door): each scan has its OWN start frame, robot at the origin, x forward, y left, metres; headings and bearings are positive to the
LEFT; a bearing is the angle of a target from the camera axis, so a fixed target's direction in the start frame is heading + bearing.

Why: find_door summed the per-pulse angles (measured from the boards when two consecutive stops share a board, otherwise FILLED with the calibrated prior or the running median, never revised).
With 2-3 boards about half of the pulses of a circle are filled, so the heading drifts by several degrees (2026-11-11: -1.7 and -8.2 deg over a circle) and the board positions smear.

solve_scan: the robot only rotates, so every landmark (board, door) has ONE direction phi in the start frame and each sighting says phi - heading[stop] = bearing. Unknowns: the heading of every
stop (heading[0] = 0), the scan's own mean pulse angle mu and one phi per landmark; a weak prior heading[k+1] - heading[k] = mu +/- sigma_pulse bridges the stops without a shared board. It is a
linear weighted least squares (Huber weights on the bearings). A board seen at the first and at the last stop closes the loop by itself: the closure error goes to the unmeasured pulses (weak
prior), not to the measured ones. The door is a landmark too (sightings of the dominant cluster only), so its direction comes with a standard deviation from the covariance.

locate_joint: each scan is re-expressed with its x axis along its own door direction (a rotation of the whole scan cancels, only the directions of the boards RELATIVE to the door matter).
The pose of scan 2 in scan 1 is fitted on the common boards with a 2x2 covariance per board (direction accurate, range noisy and growing with the square of the distance), instead of the
unweighted rigid fit. The uncertainty is propagated by Monte Carlo (fixed seed) over the board directions (full covariance of the scan solution), the ranges and a per-scan door bearing bias:
the result carries a 5-95 % interval of the range and range_reliable with the reasons. At least 2 common boards are needed (1 board leaves the pose undetermined).
Not modelled (knobs exist where cheap): the lens sits ahead of the turning centre (cam_fwd_m), a bearing scale error of the fisheye model, the robot creeping while it spins."""
import argparse
import json
import math

import numpy as np

from tools.find_door import dominant_bearing
from tools.locate_door import intersect, rigid_fit
from tools.scan_boards import PRIOR_PULSE_RAD, pulse_angle, wrap

SIGMA_BEARING_DEG = 0.5          # one board bearing (median of a few frames); residual rms on the 2026-11-11 scans: 0.2-0.5 deg, about 1 with an irregular pulse
PARALLAX_M = 0.03                # the lens is not on the turning axis: a board at range r gets an extra bearing sd of PARALLAX_M / r (0.7 m -> 2.5 deg, 3.5 m -> 0.5 deg)
SIGMA_PULSE_DEG = 3.0            # spread of one 0.2 s pulse around the scan's mean (measured 1.2-2 deg; single pulses 5-11 deg off, hence Huber weights)
PRIOR_PULSE_SD_DEG = 3.0         # how far the scan's mean pulse may sit from PRIOR_PULSE_RAD (23.1-26.6 deg seen on 2026-11-11)
SIGMA_DOOR_DEG = 1.5             # one stop's door bearing (median of its frames)
DOOR_BIAS_DEG = 1.0              # per-scan systematic error of the door direction (the detector agreed with the tape to about 1 deg)
RANGE_SD_FLOOR_M = 0.03          # board range sd = hypot(floor, RANGE_SD_PER_M2 * range^2): 150 mm markers, 0.07-0.08 m scatter at 3.7-4 m plus an unknown bias
RANGE_SD_PER_M2 = 0.01
HUBER_K = 2.5
MIN_RAY_DEG = 8.0                # reliability gates of locate_joint
MAX_REL_WIDTH = 0.6              # (p95 - p5) / median of the range from the final spot
MAX_CHI2_PER_DOF = 9.0
MIN_VALID_FRAC = 0.9


def _lsq(obs, n_stops, h0, prior_pulse, sig_pulse, sig_prior):
    """obs: [(stop, key, bearing_rad, sigma_rad)]. -> (headings, mu, keys, phi, cov of [h1.., mu, phi..], normalised bearing residuals). Linear: phi_key - h_stop = bearing (+ whole turns from h0)."""
    keys = sorted({o[1] for o in obs}, key=str)
    col = {k: n_stops + i for i, k in enumerate(keys)}                # columns: h_1..h_{K-1} at 0..K-2, mu at K-1, phi after
    first = {}
    for s, k, b, _ in obs:
        first.setdefault(k, h0[s] + b)
    n = n_stops + len(keys)
    rows, y, sig = [], [], []
    for s, k, b, sg in obs:
        r = np.zeros(n)
        r[col[k]] = 1.0
        if s > 0:
            r[s - 1] = -1.0
        rows.append(r)
        y.append(b + 2 * math.pi * round((first[k] - h0[s] - b) / (2 * math.pi)))
        sig.append(sg)
    nb = len(rows)
    for k in range(n_stops - 1):                                      # pulse prior: h_{k+1} - h_k - mu = 0
        r = np.zeros(n)
        r[k] = 1.0
        if k > 0:
            r[k - 1] = -1.0
        r[n_stops - 1] = -1.0
        rows.append(r)
        y.append(0.0)
        sig.append(sig_pulse)
    r = np.zeros(n)
    r[n_stops - 1] = 1.0
    rows.append(r)
    y.append(prior_pulse)
    sig.append(sig_prior)
    A, y, w = np.array(rows), np.array(y), 1.0 / np.array(sig)
    nh = len(rows) - 1                                                # Huber on the bearing AND pulse rows (one pulse can be 10 deg off the mean), not on the prior of mu
    for _ in range(8):
        x = np.linalg.lstsq(A * w[:, None], y * w, rcond=None)[0]
        res = (A @ x - y) / np.array(sig)
        w = 1.0 / np.array(sig)
        big = np.abs(res[:nh]) > HUBER_K
        w[:nh][big] *= np.sqrt(HUBER_K / np.abs(res[:nh][big]))
    Aw = A * w[:, None]
    cov = np.linalg.pinv(Aw.T @ Aw)
    return [0.0] + [float(v) for v in x[:n_stops - 1]], float(x[n_stops - 1]), keys, [float(x[col[k]]) for k in keys], cov, res[:nb]


def solve_scan(boards, n_stops, door=(), sigma_bearing_deg=SIGMA_BEARING_DEG, parallax_m=PARALLAX_M, sigma_pulse_deg=SIGMA_PULSE_DEG, prior_pulse_rad=PRIOR_PULSE_RAD,
               prior_pulse_sd_deg=PRIOR_PULSE_SD_DEG, sigma_door_deg=SIGMA_DOOR_DEG, cam_fwd_m=0.0, window_deg=10.0):
    """One spin scan. boards: [(stop, marker_id, bearing_rad, range_m)], door: [(stop, bearing_rad, inliers)] (every frame's sighting), n_stops: stops made (pulses + 1).
    cam_fwd_m: the lens this far ahead of the turning centre (bearings and ranges are moved to the centre first; 0 = not corrected).
    -> dict: headings_deg and heading_sd_deg per stop, pulse_deg (the scan's mean), boards {id: dir_deg, range_m, x_m, y_m, stops}, door_bearing_deg / door_sd_deg (None when not seen),
    dir_keys / dir_rad / dir_cov (landmark directions with their covariance, the door under the key "door"), bearing_resid_rms_deg."""
    if cam_fwd_m:
        boards = [(s, m, math.atan2(r * math.sin(b), r * math.cos(b) + cam_fwd_m), math.hypot(r * math.sin(b), r * math.cos(b) + cam_fwd_m)) for s, m, b, r in boards]
    per = [dict() for _ in range(n_stops)]
    for s, m, b, r in boards:
        per[s][m] = (b, r)
    h0 = [0.0]
    for k in range(1, n_stops):                                       # start values (only used to count whole turns): the running sum
        ang = pulse_angle(per[k - 1], per[k], min_range=0.0)[0]
        h0.append(h0[-1] + (prior_pulse_rad if ang is None else ang))
    sb = math.radians(sigma_bearing_deg)
    obs = [(s, str(m), b, math.hypot(sb, parallax_m / max(r, 0.2))) for s, m, b, r in boards]
    args = (prior_pulse_rad, math.radians(sigma_pulse_deg), math.radians(prior_pulse_sd_deg))
    h, mu, keys, phi, cov, res = _lsq(obs, n_stops, h0, *args)
    n_door, centre = 0, None
    if door:
        centre = dominant_bearing([(h[s] + b, inl) for s, b, inl in door], window_deg)[0]
        by_stop = {}
        for s, b, _ in door:
            if abs((math.degrees(h[s] + b) - centre + 180) % 360 - 180) <= window_deg:
                by_stop.setdefault(s, []).append(b)
                n_door += 1
        obs += [(s, "door", float(np.median(v)), math.radians(sigma_door_deg)) for s, v in sorted(by_stop.items())]
        h, mu, keys, phi, cov, res = _lsq(obs, n_stops, h, *args)
    i0 = n_stops
    sd_h = [0.0] + [math.sqrt(max(cov[i, i], 0.0)) for i in range(n_stops - 1)]
    out_b = {}
    for i, k in enumerate(keys):
        if k != "door":
            rng = float(np.median([r for _, m, _, r in boards if str(m) == k]))
            out_b[k] = dict(dir_deg=round(math.degrees(wrap(phi[i])), 2), range_m=round(rng, 3), x_m=rng * math.cos(phi[i]), y_m=rng * math.sin(phi[i]), stops=sum(1 for o in boards if str(o[1]) == k))
    d = keys.index("door") if "door" in keys else None
    nres = len(boards)
    return dict(headings_deg=[round(math.degrees(v), 2) for v in h], heading_sd_deg=[round(math.degrees(v), 2) for v in sd_h], pulse_deg=round(math.degrees(mu), 2), boards=out_b,
                door_bearing_deg=None if d is None else round(math.degrees(wrap(phi[d])), 2), door_sd_deg=None if d is None else round(math.degrees(math.sqrt(cov[i0 + d, i0 + d])), 2),
                door_cluster_sightings=n_door, door_sightings=len(door), dir_keys=keys, dir_rad=phi, dir_cov=cov[i0:, i0:].tolist(),
                bearing_resid_rms_deg=round(math.degrees(float(np.sqrt(np.mean((res[:nres] * [o[3] for o in obs[:nres]]) ** 2)))), 2) if nres else None)


def fit_pose(pa, ca, pb, cb, start=None, iters=8):
    """Pose (th, tx, ty) of frame B in frame A from matched points pa[i] ~ R(th) pb[i] + t, each with a 2x2 covariance (ca[i], cb[i]): Gauss-Newton on sum e' (ca + R cb R')^-1 e,
    started from the unweighted rigid fit. -> (th, tx, ty, chi2). Needs at least 2 points."""
    th, tx, ty = start if start is not None else rigid_fit([tuple(p) for p in pb], [tuple(p) for p in pa])[:3]
    chi2 = 0.0
    for it in range(iters + 1):
        c, s = math.cos(th), math.sin(th)
        R, dR = np.array([[c, -s], [s, c]]), np.array([[-s, -c], [c, -s]])
        H, g, chi2 = np.zeros((3, 3)), np.zeros(3), 0.0
        for a, A, b, B in zip(pa, ca, pb, cb):
            W = np.linalg.inv(A + R @ B @ R.T)
            e = a - R @ b - (tx, ty)
            J = np.column_stack((-np.eye(2), -dR @ b))
            H += J.T @ W @ J
            g += J.T @ W @ e
            chi2 += float(e @ W @ e)
        if it == iters:
            break
        d = np.linalg.solve(H + 1e-12 * np.eye(3), -g)
        tx, ty, th = tx + d[0], ty + d[1], th + d[2]
    return float(th), float(tx), float(ty), chi2


def _polar(psi, rho, var_psi, var_rho):
    """Point at angle psi, range rho -> (xy, 2x2 covariance from the direction and range variances)."""
    c, s = math.cos(psi), math.sin(psi)
    U = np.array([[c, -s], [s, c]])
    return np.array([rho * c, rho * s]), U @ np.diag([var_rho, rho * rho * var_psi]) @ U.T


def _range_sd(rho):
    return math.hypot(RANGE_SD_FLOOR_M, RANGE_SD_PER_M2 * rho * rho)


def locate_joint(s1, s2, stand_off_m=2.0, n_mc=300, seed=0, door_bias_deg=DOOR_BIAS_DEG):
    """s1, s2: solve_scan results of the first and the second scan. -> dict like tools.locate_door.locate (door in the first frame, in the second frame = the robot's final spot, sweet spot)
    plus range_from_second_interval_m (5-95 %), bearing_from_second_interval_deg, fit_chi2 / fit_dof, mc_valid_frac, range_reliable and reasons. ValueError when it cannot be computed at all."""
    if s1.get("door_bearing_deg") is None or s2.get("door_bearing_deg") is None:
        raise ValueError("the door was not seen in both scans")
    common = sorted(set(s1["boards"]) & set(s2["boards"]))
    if len(common) < 2:
        raise ValueError("need at least 2 boards seen in both scans to fix the second pose, got %s" % common)

    def gauge(s):                                                    # directions relative to the scan's own door direction, with their covariance
        k = s["dir_keys"]
        T = np.zeros((len(common), len(k)))
        for i, m in enumerate(common):
            T[i, k.index(m)], T[i, k.index("door")] = 1.0, -1.0
        return T @ np.array(s["dir_rad"]), T @ np.array(s["dir_cov"]) @ T.T, np.array([s["boards"][m]["range_m"] for m in common])

    def solve(psi_a, rho_a, psi_b, rho_b, va, vb, start=None, iters=8):
        A = [_polar(p, r, v, _range_sd(r) ** 2) for p, r, v in zip(psi_a, rho_a, va)]
        B = [_polar(p, r, v, _range_sd(r) ** 2) for p, r, v in zip(psi_b, rho_b, vb)]
        th, tx, ty, chi2 = fit_pose([a[0] for a in A], [a[1] for a in A], [b[0] for b in B], [b[1] for b in B], start, iters)
        hit = intersect((0.0, 0.0), 0.0, (tx, ty), th)              # both doors lie on their frame's x axis
        return th, tx, ty, chi2, hit

    (pa, Ca, ra), (pb, Cb, rb) = gauge(s1), gauge(s2)
    floor = math.radians(0.2) ** 2                                   # a board seen together with the door has a formal sd near 0: keep the weights finite
    va, vb = np.diag(Ca) + floor, np.diag(Cb) + floor
    th, tx, ty, chi2, hit = solve(pa, ra, pb, rb, va, vb)
    if hit is None or hit[2] <= 0 or hit[3] <= 0:
        raise ValueError("the two door rays do not meet in front of both spots (rays nearly parallel or a wrong bearing)")
    dof = 2 * len(common) - 3
    scale = max(1.0, chi2 / dof)                                      # a poor fit widens the interval
    rng = np.random.default_rng(seed)
    r2s, b2s = [], []
    bias = math.radians(door_bias_deg)
    for _ in range(n_mc):
        qa = rng.multivariate_normal(pa, Ca * scale + np.eye(len(common)) * floor) - rng.normal(0, bias)
        qb = rng.multivariate_normal(pb, Cb * scale + np.eye(len(common)) * floor) - rng.normal(0, bias)
        h = solve(qa, ra + rng.normal(0, 1, len(common)) * [_range_sd(r) * math.sqrt(scale) for r in ra], qb, rb + rng.normal(0, 1, len(common)) * [_range_sd(r) * math.sqrt(scale) for r in rb],
                  va, vb, (th, tx, ty), 2)[4]
        if h is not None and h[2] > 0 and h[3] > 0:
            r2s.append(h[3])
    d1, d2 = math.radians(s1["door_bearing_deg"]), math.radians(s2["door_bearing_deg"])
    c, s_ = math.cos(d1), math.sin(d1)
    r1, r2 = hit[2], hit[3]
    valid = len(r2s) / float(n_mc)
    lo, hi = (float(np.percentile(r2s, 5)), float(np.percentile(r2s, 95))) if r2s else (None, None)
    ray = abs(math.degrees(wrap(th)))
    k = max(0.0, 1.0 - stand_off_m / r2)
    reasons = []
    if ray < MIN_RAY_DEG:
        reasons.append("ray angle %.1f deg < %.0f: the two door rays are nearly parallel" % (ray, MIN_RAY_DEG))
    if chi2 / dof > MAX_CHI2_PER_DOF:
        reasons.append("board fit chi2 %.1f on %d dof: the common boards do not agree between the scans" % (chi2, dof))
    if valid < MIN_VALID_FRAC:
        reasons.append("only %.0f %% of the perturbed solutions give a door in front of both spots" % (100 * valid))
    if lo is None or (hi - lo) / r2 > MAX_REL_WIDTH:
        reasons.append("range interval %s m is wider than %.0f %% of the range" % ("none" if lo is None else "%.2f-%.2f" % (lo, hi), 100 * MAX_REL_WIDTH))
    return dict(door_x_m=round(r1 * c, 2), door_y_m=round(r1 * s_, 2), range_from_first_m=round(r1, 2), range_from_second_m=round(r2, 2),
                range_from_second_interval_m=None if lo is None else [round(lo, 2), round(hi, 2)], bearing_from_second_deg=s2["door_bearing_deg"],
                second_position_in_first_frame=[round(c * tx - s_ * ty, 2), round(s_ * tx + c * ty, 2)], second_heading_deg=round(math.degrees(wrap(th + d1 - d2)), 1),
                baseline_m=round(math.hypot(tx, ty), 2), ray_angle_deg=round(ray, 1), boards_used=common, fit_chi2=round(chi2, 2), fit_dof=dof, mc_valid_frac=round(valid, 3),
                door_in_second_frame=[round(r2 * math.cos(d2), 2), round(r2 * math.sin(d2), 2)], sweet_spot_in_second_frame=[round(r2 * k * math.cos(d2), 2), round(r2 * k * math.sin(d2), 2)],
                stand_off_m=stand_off_m, door_sd_deg=[s1["door_sd_deg"], s2["door_sd_deg"]], range_reliable=not reasons, reasons=reasons, seed=seed, n_mc=n_mc)


def scan_from_record(rec, **knobs):
    """One scan of observations.json (tools.find_door.new_scan()['record']) -> solve_scan result."""
    boards = [(st["stop"], b[0], math.radians(b[1]), b[2]) for st in rec["stops"] for b in st["boards"]]
    door = [(st["stop"], math.radians(d[0]), d[1]) for st in rec["stops"] for d in st["door"]]
    return solve_scan(boards, len(rec["stops"]), door, **knobs)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("observations", help="observations.json saved by tools.find_door")
    ap.add_argument("--stand-off", type=float, default=2.0)
    ap.add_argument("--cam-fwd-m", type=float, default=0.0, help="lens ahead of the turning centre (m)")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    obs = json.load(open(a.observations))
    s1, s2 = (scan_from_record(obs[k], cam_fwd_m=a.cam_fwd_m) for k in ("scan1", "scan2"))
    for name, s in (("scan1", s1), ("scan2", s2)):
        print(name, json.dumps({k: s[k] for k in ("pulse_deg", "headings_deg", "heading_sd_deg", "boards", "door_bearing_deg", "door_sd_deg", "bearing_resid_rms_deg")}))
    print(json.dumps(locate_joint(s1, s2, a.stand_off, seed=a.seed), indent=1))


if __name__ == "__main__":
    main()
