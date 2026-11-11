"""Door position from TWO scan_boards runs taken at two spots (the door detector gives a bearing only, so the range comes from a baseline).

  python -m tools.locate_door data/scan/<first>/summary.json data/scan/<second>/summary.json

Each scan is expressed in its OWN start frame (robot at the origin facing +x, y left). The boards (ArUco, fixed in the room) seen in both scans give the rigid transform from the second
frame to the first (least squares over the common boards, at least two), hence where the robot stood the second time. The door bearing of each scan is a ray; the two rays meet at the door.
Prints the door in the FIRST scan's frame, the baseline, the angle between the rays, the board-fit residual and a range spread from +/- --bearing-sd-deg on each bearing: a short baseline or a
small ray angle means a poor range (the output says so). Bearing noise, not the board fit, dominates: the spread is the honest uncertainty. Stdlib + math only."""
import argparse
import json
import math


def rigid_fit(p, q):
    """Least-squares 2D rotation+translation with q ~ R p + t. p, q: lists of (x, y). Returns (theta, tx, ty, rms)."""
    n = len(p)
    pc = (sum(a for a, _ in p) / n, sum(b for _, b in p) / n)
    qc = (sum(a for a, _ in q) / n, sum(b for _, b in q) / n)
    s_cos = sum((a - pc[0]) * (c - qc[0]) + (b - pc[1]) * (d - qc[1]) for (a, b), (c, d) in zip(p, q))
    s_sin = sum((a - pc[0]) * (d - qc[1]) - (b - pc[1]) * (c - qc[0]) for (a, b), (c, d) in zip(p, q))
    th = math.atan2(s_sin, s_cos)
    c, s = math.cos(th), math.sin(th)
    tx, ty = qc[0] - (c * pc[0] - s * pc[1]), qc[1] - (s * pc[0] + c * pc[1])
    rms = math.sqrt(sum((c * a - s * b + tx - cc) ** 2 + (s * a + c * b + ty - dd) ** 2 for (a, b), (cc, dd) in zip(p, q)) / n)
    return th, tx, ty, rms


def intersect(o1, a1, o2, a2):
    """Rays o + r (cos a, sin a); returns (x, y, r1, r2) or None when (nearly) parallel."""
    d1, d2 = (math.cos(a1), math.sin(a1)), (math.cos(a2), math.sin(a2))
    det = d1[0] * (-d2[1]) - d1[1] * (-d2[0])
    if abs(det) < 1e-6:
        return None
    bx, by = o2[0] - o1[0], o2[1] - o1[1]
    r1 = (bx * (-d2[1]) - by * (-d2[0])) / det
    r2 = (d1[0] * by - d1[1] * bx) / det
    return o1[0] + r1 * d1[0], o1[1] + r1 * d1[1], r1, r2


def locate(first, second, bearing_sd_deg=2.0, stand_off_m=2.0):
    """first, second: scan_boards summary dicts. -> dict (door in the first frame, baseline, ray angle, board residual, range spread)."""
    common = sorted(set(first["boards"]) & set(second["boards"]))
    if len(common) < 2:
        raise ValueError("need at least 2 boards seen in both scans, got %s" % common)
    if first.get("door_bearing_deg") is None or second.get("door_bearing_deg") is None:
        raise ValueError("the door was not seen in both scans")
    p = [(second["boards"][k]["x_m"], second["boards"][k]["y_m"]) for k in common]
    q = [(first["boards"][k]["x_m"], first["boards"][k]["y_m"]) for k in common]
    th, tx, ty, rms = rigid_fit(p, q)
    b1 = math.radians(first["door_bearing_deg"])
    b2 = math.radians(second["door_bearing_deg"]) + th
    hit = intersect((0.0, 0.0), b1, (tx, ty), b2)
    if hit is None or hit[2] <= 0 or hit[3] <= 0:
        raise ValueError("the two bearing rays do not meet in front of both robots (baseline too short or a bad bearing)")
    out = dict(door_x_m=round(hit[0], 2), door_y_m=round(hit[1], 2), range_from_first_m=round(hit[2], 2), range_from_second_m=round(hit[3], 2),
               second_position_in_first_frame=[round(tx, 2), round(ty, 2)], second_heading_deg=round(math.degrees(th), 1), baseline_m=round(math.hypot(tx, ty), 2),
               ray_angle_deg=round(abs(math.degrees(math.remainder(b2 - b1, 2 * math.pi))), 1), boards_used=common, board_fit_rms_m=round(rms, 3))
    dx, dy = hit[0] - tx, hit[1] - ty
    c, s_ = math.cos(-th), math.sin(-th)
    door_b = (c * dx - s_ * dy, s_ * dx + c * dy)               # the door in the SECOND frame = where the robot stands after the baseline, facing its final heading
    k = max(0.0, 1.0 - stand_off_m / hit[3])                      # sweet spot: stand_off_m from the door on the line from the robot to it (the robot's own spot if already closer)
    out.update(door_in_second_frame=[round(door_b[0], 2), round(door_b[1], 2)], sweet_spot_in_second_frame=[round(door_b[0] * k, 2), round(door_b[1] * k, 2)], stand_off_m=stand_off_m)
    sd = math.radians(bearing_sd_deg)
    rs = []
    for d1 in (-sd, sd):
        for d2 in (-sd, sd):
            h = intersect((0.0, 0.0), b1 + d1, (tx, ty), b2 + d2)
            if h is not None and h[2] > 0:
                rs.append(h[2])
    out["range_from_first_spread_m"] = [round(min(rs), 2), round(max(rs), 2)] if rs else None
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("first")
    ap.add_argument("second")
    ap.add_argument("--bearing-sd-deg", type=float, default=2.0)
    a = ap.parse_args()
    res = locate(json.load(open(a.first)), json.load(open(a.second)), a.bearing_sd_deg)
    print(json.dumps(res, indent=1))
    if res["ray_angle_deg"] < 8 or res["baseline_m"] < 0.5:
        print("WARNING: ray angle under 8 deg or baseline under 0.5 m: the range is poor, see the spread")


if __name__ == "__main__":
    main()
