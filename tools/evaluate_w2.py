"""T1 distance and saved map against explicitly matched tape measurements.

Annotations CSV: obstacle_id,frame_index,detection_index,tape_distance_m,world_x_m,world_y_m
Match detection_index manually from observations.csv to avoid silently matching the wrong object.
Tape distance is planar range from directly under the lens. World coordinates refer
to the same ground contact in the map frame. At least 20 distinct obstacle IDs.
"""
import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np

from sentry.config import load
from sentry.nav.gridmap import OCCUPIED, OccupancyGrid


def evaluate(observations, annotations, map_path, config_path=None):
    limits = (load() if config_path is None else load(config_path))["w2_validation"]
    with Path(observations).open(encoding="utf-8-sig", newline="") as f:
        predictions = {}
        for row in csv.DictReader(f):
            key = (int(row["frame_index"]), int(row["detection_index"]))
            if key in predictions:
                raise ValueError("duplicate prediction key")
            predictions[key] = row
    groups, truth, matched_keys = {}, {}, set()
    with Path(annotations).open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            oid = row["obstacle_id"]
            tape, x, y = (float(row[k]) for k in ("tape_distance_m", "world_x_m", "world_y_m"))
            if (not oid or not all(math.isfinite(v) for v in (tape, x, y))
                    or not limits["min_tape_m"] <= tape <= limits["max_tape_m"]):
                raise ValueError("finite truth, nonempty ID and tape range 0.3-2.0 m required")
            if oid in truth and not np.allclose(truth[oid], (x, y), rtol=0, atol=1e-6):
                raise ValueError("one fixed world ground contact per obstacle ID required")
            truth[oid] = (x, y)
            groups.setdefault(oid, [])
            key = (int(row["frame_index"]), int(row["detection_index"]))
            if key[0] < 0 or key[1] < -1:
                raise ValueError("frame_index >=0; detection_index >=0 or -1 for a missed obstacle")
            if key[1] >= 0:
                if key in matched_keys:
                    raise ValueError("a detection can be matched to only one annotation")
                matched_keys.add(key)
            pred = predictions.get(key)
            if pred is not None and pred["distance_m"]:
                distance = float(pred["distance_m"])
                if not math.isfinite(distance) or distance <= 0:
                    raise ValueError("invalid predicted distance")
                groups[oid].append(abs(distance - tape) / tape)
    if not groups:
        raise ValueError("no measured obstacle annotations")
    errors = [float(np.median(values)) for values in groups.values() if values]
    median = float(np.median(errors)) if errors else None
    p90 = float(np.percentile(errors, 90)) if errors else None
    grid = OccupancyGrid.load(map_path)
    occupied = np.argwhere(grid.cells == OCCUPIED)
    points = np.asarray([grid.cell_to_world(tuple(cell)) for cell in occupied]).reshape(-1, 2)
    map_errors = {oid: float(np.linalg.norm(points - xy, axis=1).min()) if len(points) else None
                  for oid, xy in truth.items()}
    fraction = sum(e is not None and e <= limits["map_error_limit_m"] for e in map_errors.values()) / len(truth)
    enough = len(truth) >= limits["min_obstacles"]
    # Missing distance predictions cannot disappear from a passing score.
    distance_pass = (enough and len(errors) == len(truth)
                     and median <= limits["distance_median_relative_limit"]
                     and p90 <= limits["distance_p90_relative_limit"])
    map_pass = enough and fraction >= limits["map_fraction_min"]
    return dict(obstacle_ids=len(truth), distance_obstacle_ids=len(errors),
                missing_distance_ids=[oid for oid, values in groups.items() if not values],
                distance_median_relative_error=median, distance_p90_relative_error=p90,
                distance_pass=distance_pass, map_fraction_within_20cm=fraction, map_pass=map_pass,
                map_error_m_by_id=map_errors, passed=distance_pass and map_pass, acceptance=limits,
                protocol="distance: median per obstacle then median/p90; map: nearest occupied cell centre")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--observations", required=True)
    ap.add_argument("--annotations", required=True)
    ap.add_argument("--map", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--config")
    a = ap.parse_args()
    try:
        result = evaluate(a.observations, a.annotations, a.map, a.config)
    except (ValueError, FileNotFoundError) as e:
        ap.error(str(e))
    path = Path(a.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
