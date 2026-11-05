"""Add the tape answers of a graded run to its summary.json, right after the run (the 2026-10-30 answers were lost because stdin was /dev/null).

  python -m tools.tape_answers data/deploy/t2b_1 --offset-x -0.18 --offset-y 0.19 --door-m 1.96 --los y --furniture y --furniture-m 0.9 --collisions 0

Axes: x forward from the START, y left of the START, metres, tape offset of the robot from the sweet spot (+ = ahead / left). A blank or missing value means "not answered" (never an error and never a zero);
`offset_m` is computed only when both coordinates are valid; invalid input (NaN/Inf, negative distance or count, bad yes/no) is refused and the file is left untouched; the file is written atomically.
"""
import argparse
import json
import math
import os
from pathlib import Path

FLOATS = ("offset_x_forward_m", "offset_y_left_m", "door_distance_m_tape", "furniture_distance_m_tape")
NONNEG = ("door_distance_m_tape", "furniture_distance_m_tape")
YESNO = ("line_of_sight_clear", "near_boundary_or_furniture")


def _blank(v):
    return v is None or (isinstance(v, str) and not v.strip())


def clean(answers):
    """-> dict of the valid answered values; raises ValueError naming the first invalid one. Blank = unanswered (dropped)."""
    if not isinstance(answers, dict):
        raise ValueError("the answers must be a JSON object, got %s" % type(answers).__name__)
    out = {}
    for k, v in answers.items():
        if _blank(v):
            continue
        if k in FLOATS:
            try:
                f = float(v)
            except (TypeError, ValueError):
                raise ValueError("%s: not a number: %r" % (k, v))
            if not math.isfinite(f) or (k in NONNEG and f < 0):
                raise ValueError("%s: must be a finite %s number, got %r" % (k, "non-negative" if k in NONNEG else "", v))
            out[k] = f
        elif k == "collisions":
            try:
                n = int(float(v))
            except (TypeError, ValueError):
                raise ValueError("collisions: not a number: %r" % (v,))
            if n != float(v) or n < 0:
                raise ValueError("collisions: must be a non-negative integer, got %r" % (v,))
            out[k] = n
        elif k in YESNO:
            if str(v).strip().lower() not in ("y", "n", "yes", "no"):
                raise ValueError("%s: must be y or n, got %r" % (k, v))
            out[k] = "y" if str(v).strip().lower().startswith("y") else "n"
        else:
            out[k] = v
    return out


def load_answers_file(path):
    """Read and validate an --answers file BEFORE the robot starts: a missing or malformed file must not cost a physical trial."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("cannot read the answers file %s: %s" % (path, exc))
    return clean(data)


def add_answers(run_dir, answers):
    path = Path(run_dir) / "summary.json"
    summary = json.loads(path.read_text())
    cur = clean(summary.get("tape_answers") or {})
    cur.update(clean(answers))
    cur.pop("offset_m", None)
    if "offset_x_forward_m" in cur and "offset_y_left_m" in cur:
        cur["offset_m"] = round(math.hypot(cur["offset_x_forward_m"], cur["offset_y_left_m"]), 3)
    summary["tape_answers"] = cur
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(summary, indent=1, allow_nan=False))
    os.replace(str(tmp), str(path))
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
    try:
        out = add_answers(a.run_dir, {"offset_x_forward_m": a.offset_x, "offset_y_left_m": a.offset_y, "door_distance_m_tape": a.door_m, "line_of_sight_clear": a.los,
                                      "near_boundary_or_furniture": a.furniture, "furniture_distance_m_tape": a.furniture_m, "collisions": a.collisions})
    except ValueError as exc:
        raise SystemExit("REFUSED, nothing written: %s" % exc)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
