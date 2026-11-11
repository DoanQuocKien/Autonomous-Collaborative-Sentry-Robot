"""Synthetic find_door runs: the on-line estimate (running-sum headings, tools.locate_door) against tools.door_pose, door range error from the FINAL spot over many seeds.

  python -m tools.door_pose_sim [--seeds 300] [--out reports/DoanQuocKien/week-06/find_door_pose/sim.json]

A run = a room (door 2.5-4.5 m away, 2 or 3 boards at 1.5-3.5 m), spin scan 1, a 1.0-1.3 m baseline roughly across the line of sight, spin scan 2. The scans go through the SAME code as the robot
(tools.find_door.new_scan / add_stop: pulse angles from the boards, filled when no board is shared, stop at 355 deg or 18 pulses), so the 'old' column is the production estimate.
Simulated: the true pulse = mean + N(0, 2 deg) (mean 25.1 deg = the prior, or 23 deg as in fd_6, or the first two pulses 4 deg larger as on 2026-11-11), boards and door seen only within
+/- 60 deg of the axis, board bearing noise 0.3 deg, board range error = a per-scan bias N(0, 0.01 r^2) + N(0, 0.005 r^2) per stop, door bearing = a per-scan bias N(0, 0.5 deg) + N(0, 1 deg) per
frame, a false door sighting at 5 % of the stops. Stress cases the estimator does NOT model: bearings compressed by 3 % (fisheye model error), the lens 0.05 m ahead of the turning centre.
It is a model: it shows what the estimator does when the noise is what we assumed, not that the real error is fixed."""
import argparse
import json
import math
from pathlib import Path

import numpy as np

from tools.door_pose import locate_joint, scan_from_record
from tools.find_door import add_stop, new_scan, summarise
from tools.locate_door import locate
from tools.scan_boards import wrap

FOV = math.radians(60)
SCENARIOS = dict(nominal=dict(), pulse_23=dict(pulse_mean_deg=23.0), first_pulses_big=dict(first_boost_deg=4.0), pulse_sd_4=dict(pulse_sd_deg=4.0),
                 bearing_scale_097=dict(bearing_scale=0.97), cam_fwd_005=dict(cam_fwd_m=0.05))


def world(rng, n_boards):
    """-> (boards {id: (x, y)}, door (x, y), second spot (x, y), second heading). The first spot is the origin, heading 0."""
    a = rng.uniform(-math.pi, math.pi)
    r = rng.uniform(2.5, 4.5)
    door = (r * math.cos(a), r * math.sin(a))
    dirs = []
    while len(dirs) < n_boards:                                       # boards at least 60 deg apart as seen from the first spot
        c = rng.uniform(-math.pi, math.pi)
        if all(abs(wrap(c - d)) > math.radians(60) for d in dirs):
            dirs.append(c)
    boards = {i: (rr * math.cos(d), rr * math.sin(d)) for i, (d, rr) in enumerate(zip(dirs, rng.uniform(1.5, 3.5, n_boards)))}
    b = a - math.pi / 2 + math.radians(rng.uniform(-20, 20))          # baseline to the right of the line of sight, veering
    L = rng.uniform(1.0, 1.3)
    return boards, door, (L * math.cos(b), L * math.sin(b)), b + math.radians(rng.uniform(-30, 30))


def spin(rng, pos, heading, boards, door, pulse_mean_deg=25.1, pulse_sd_deg=2.0, first_boost_deg=0.0, bearing_scale=1.0, cam_fwd_m=0.0, max_pulses=18):
    """One spin scan through tools.find_door.add_stop. -> the scan dict (on-line estimate and record)."""
    scan = new_scan()
    rbias = {m: rng.normal(0, 0.01) for m in boards}
    dbias = rng.normal(0, math.radians(0.5))
    for k in range(max_pulses + 1):
        cx, cy = pos[0] + cam_fwd_m * math.cos(heading), pos[1] + cam_fwd_m * math.sin(heading)

        def polar(p):
            return wrap(math.atan2(p[1] - cy, p[0] - cx) - heading), math.hypot(p[0] - cx, p[1] - cy)
        seen = {}
        for m, p in boards.items():
            b, r = polar(p)
            if abs(b) <= FOV and r <= 4.5:
                b = b * bearing_scale + rng.normal(0, math.radians(0.3))
                r = r + (rbias[m] + rng.normal(0, 0.005)) * r * r
                seen[m] = (b, r, r * math.cos(b), r * math.sin(b), 6)
        b = polar(door)[0]
        sight = [(b * bearing_scale + dbias + rng.normal(0, math.radians(1.0)), 100) for _ in range(4)] if abs(b) <= FOV else []
        if rng.random() < 0.05:
            sight.append((rng.uniform(-FOV, FOV), 28))
        if math.degrees(add_stop(scan, seen, sight, spin_s=0.2)) >= 355 or k == max_pulses:
            break
        heading += math.radians(pulse_mean_deg + (first_boost_deg if k < 2 else 0.0) + rng.normal(0, pulse_sd_deg))
    return scan


def one(seed, n_boards, **cfg):
    """-> dict(truth, old, new): the door range from the final spot (old/new None when the estimator refuses) and the new estimate's interval / reliable flag."""
    rng = np.random.default_rng(seed)
    boards, door, p2, h2 = world(rng, n_boards)
    sc1 = spin(rng, (0.0, 0.0), 0.0, boards, door, **cfg)
    sc2 = spin(rng, p2, h2, boards, door, **cfg)
    out = dict(truth=math.hypot(door[0] - p2[0], door[1] - p2[1]), old=None, new=None, reliable=False, interval=None, old_ok=False)
    try:
        r = locate(summarise(sc1["boards"], sc1["doors"]), summarise(sc2["boards"], sc2["doors"]))
        out.update(old=r["range_from_second_m"], old_ok=bool(r["baseline_m"] >= 0.5 and r["ray_angle_deg"] >= 8.0))
    except ValueError:
        pass
    try:
        r = locate_joint(scan_from_record(sc1["record"]), scan_from_record(sc2["record"]), n_mc=200, seed=seed)
        out.update(new=r["range_from_second_m"], reliable=r["range_reliable"], interval=r["range_from_second_interval_m"])
    except ValueError:
        pass
    return out


def stats(runs):
    def pct(key, ok=lambda r: True):
        e = [100 * abs(r[key] - r["truth"]) / r["truth"] for r in runs if r[key] is not None and ok(r)]
        return dict(n=len(e), median_pct=round(float(np.median(e)), 1), p90_pct=round(float(np.percentile(e, 90)), 1)) if e else dict(n=0)
    both = lambda r: r["old"] is not None and r["new"] is not None
    cov = [r["interval"][0] <= r["truth"] <= r["interval"][1] for r in runs if r["interval"]]
    return dict(runs=len(runs), old=pct("old"), new=pct("new"), old_same_runs=pct("old", both), new_same_runs=pct("new", both), old_flagged_ok=pct("old", lambda r: r["old_ok"]),
                new_reliable=pct("new", lambda r: r["reliable"]), interval_coverage_pct=round(100 * float(np.mean(cov)), 1) if cov else None)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", type=int, default=300)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    res = {}
    print("door range error from the final spot, |error| in %% of the true range: median / 90th percentile (runs that gave an answer), %d seeds" % a.seeds)
    for name, cfg in SCENARIOS.items():
        for nb in (2, 3):
            s = stats([one(seed, nb, **cfg) for seed in range(a.seeds)])
            res["%s_%d_boards" % (name, nb)] = s
            f = lambda d: "%5.1f / %5.1f (%3d)" % (d["median_pct"], d["p90_pct"], d["n"]) if d["n"] else "      none      "
            print("%-18s %d boards | old %s | new %s | old, flagged ok %s | new, reliable %s | 5-95 %% interval holds the truth in %s %%" % (
                name, nb, f(s["old"]), f(s["new"]), f(s["old_flagged_ok"]), f(s["new_reliable"]), s["interval_coverage_pct"]), flush=True)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(dict(seeds=a.seeds, scenarios=SCENARIOS, results=res), indent=1))


if __name__ == "__main__":
    main()
