"""Add the tape answers of a graded run to its summary.json, right after the run (the 2026-10-30 answers were lost because stdin was /dev/null).

  python -m tools.tape_answers data/deploy/t2b_1 --offset-x -0.18 --offset-y 0.19 --door-m 1.96 --los y --furniture y --furniture-m 0.9 --collisions 0

Axes: x forward from the START, y left of the START, metres, tape offset of the robot from the sweet spot (+ = ahead / left). Writes the keys that deploy_live's `tape_answers` uses and the run is then complete.
"""
import argparse
import json
import math
from pathlib import Path


def add_answers(run_dir, answers):
    path = Path(run_dir) / "summary.json"
    summary = json.loads(path.read_text())
    cur = summary.get("tape_answers") or {}
    cur.update({k: v for k, v in answers.items() if v is not None})
    if "offset_x_forward_m" in cur and "offset_y_left_m" in cur:
        cur["offset_m"] = round(math.hypot(float(cur["offset_x_forward_m"]), float(cur["offset_y_left_m"])), 3)
    summary["tape_answers"] = cur
    path.write_text(json.dumps(summary, indent=1))
    return cur


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir")
    ap.add_argument("--offset-x", type=float, help="tape offset from the sweet spot along x (forward from the start), m")
    ap.add_argument("--offset-y", type=float, help="tape offset along y (left of the start), m")
    ap.add_argument("--door-m", type=float, help="tape distance robot to door, m")
    ap.add_argument("--los", choices=("y", "n"), help="clear line of sight to the door")
    ap.add_argument("--furniture", choices=("y", "n"), help="wall or furniture within 1 m")
    ap.add_argument("--furniture-m", type=float, help="tape distance to that wall or furniture, m")
    ap.add_argument("--collisions", type=int)
    a = ap.parse_args()
    out = add_answers(a.run_dir, {"offset_x_forward_m": a.offset_x, "offset_y_left_m": a.offset_y, "door_distance_m_tape": a.door_m, "line_of_sight_clear": a.los,
                                  "near_boundary_or_furniture": a.furniture, "furniture_distance_m_tape": a.furniture_m, "collisions": a.collisions})
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
