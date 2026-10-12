"""T1 FORWARD distance against tape, reported separately on glossy/matte floor.

Annotations: obstacle_id,frame_index,detection_index,tape_forward_m,floor,
use_in_metric[,world_x_m,world_y_m,map_eligible]. World truth is optional for
forward-only checks; unconfirmed lateral data must not enter map scoring.
"""
import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np

from sentry.config import load
from sentry.nav.gridmap import OCCUPIED, OccupancyGrid


def floor_name(value):
    value = value.strip().lower()
    if 'gloss' in value:
        return 'glossy'
    if 'matte' in value:
        return 'matte'
    raise ValueError('floor must identify glossy or matte')


def stats(groups, limits):
    errors = [float(np.median(v)) for v in groups.values() if v]
    median = float(np.median(errors)) if errors else None
    p90 = float(np.percentile(errors, 90)) if errors else None
    return dict(obstacle_ids=len(groups), measured_ids=len(errors),
                missing_ids=[k for k,v in groups.items() if not v],
                median_relative_error=median, p90_relative_error=p90,
                within_error_limits=bool(groups) and len(errors)==len(groups)
                and median <= limits['distance_median_relative_limit']
                and p90 <= limits['distance_p90_relative_limit'])


def evaluate(observations, annotations, map_path=None, config_path=None):
    limits = (load() if config_path is None else load(config_path))['w2_validation']
    predictions = {}
    with Path(observations).open(encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            key = (int(row['frame_index']), int(row['detection_index']))
            if key in predictions:
                raise ValueError('duplicate prediction key')
            predictions[key] = row
    groups, truth, floors, matched_keys, excluded = {}, {}, {}, set(), set()
    with Path(annotations).open(encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            oid = row['obstacle_id']
            use = row.get('use_in_metric', 'yes').strip().lower()
            if not oid or use not in ('yes', 'no', 'check'):
                raise ValueError('nonempty obstacle ID and use_in_metric yes/no/check required')
            if use == 'no':
                excluded.add(oid)
                continue
            if oid in excluded:
                raise ValueError('inconsistent use_in_metric for obstacle ID')
            tape_text = row.get('tape_forward_m', row.get('forward_m'))
            if tape_text is None:
                raise ValueError('tape_forward_m required: tape is forward, not planar range')
            tape = float(tape_text)
            if not math.isfinite(tape) or not limits['min_tape_m'] <= tape <= limits['max_tape_m']:
                raise ValueError('finite tape forward in configured range required')
            floor = floor_name(row.get('floor', ''))
            if oid in floors and floors[oid] != floor:
                raise ValueError('use distinct obstacle IDs for different floor setups')
            floors[oid] = floor
            groups.setdefault(oid, [])
            xy_text = (row.get('world_x_m', ''), row.get('world_y_m', ''))
            eligibility = row.get('map_eligible', '').strip().lower()
            if eligibility not in ('', 'yes', 'no'):
                raise ValueError('map_eligible must be yes/no or blank')
            map_eligible = eligibility == 'yes' or (eligibility == '' and use != 'check' and all(xy_text))
            if map_eligible:
                if not all(xy_text):
                    raise ValueError('confirmed world coordinates required for map_eligible=yes')
                xy = tuple(float(q) for q in xy_text)
                if not all(math.isfinite(q) for q in xy):
                    raise ValueError('world truth must be finite')
                if oid in truth and not np.allclose(truth[oid], xy, rtol=0, atol=1e-6):
                    raise ValueError('one fixed world contact per obstacle ID required')
                truth[oid] = xy
            key = (int(row['frame_index']), int(row['detection_index']))
            if key[0] < 0 or key[1] < -1:
                raise ValueError('frame_index >=0; detection_index >=0 or -1 for a missed obstacle')
            if key[1] >= 0:
                if key in matched_keys:
                    raise ValueError('a detection can be matched to only one annotation')
                matched_keys.add(key)
            pred = predictions.get(key) if key[1] >= 0 else None
            if pred is not None and pred.get('floor_type') and pred['floor_type'] != floor:
                raise ValueError('prediction/annotation floor mismatch')
            if pred is not None and not pred.get('rejection') and pred.get('forward_m'):
                distance = float(pred['forward_m'])
                if not math.isfinite(distance) or distance <= 0:
                    raise ValueError('invalid predicted forward distance')
                groups[oid].append(abs(distance-tape)/tape)
    if not groups:
        raise ValueError('no eligible measured obstacle annotations')
    if excluded.intersection(groups):
        raise ValueError('inconsistent use_in_metric for obstacle ID')
    overall = stats(groups, limits)
    by_floor = {floor: stats({k:v for k,v in groups.items() if floors[k]==floor}, limits)
                for floor in limits['required_floor_types']}
    floor_complete = all(s['obstacle_ids'] for s in by_floor.values())
    distance_pass = (len(groups) >= limits['min_obstacles'] and overall['within_error_limits']
                     and floor_complete and all(s['within_error_limits'] for s in by_floor.values()))
    map_errors = {}
    if map_path is not None:
        grid = OccupancyGrid.load(map_path)
        occupied = np.argwhere(grid.cells == OCCUPIED)
        points = np.asarray([grid.cell_to_world(tuple(c)) for c in occupied]).reshape(-1,2)
        map_errors = {k: float(np.linalg.norm(points-xy,axis=1).min()) if len(points) else None
                      for k,xy in truth.items()}
    fraction = (sum(e is not None and e <= limits['map_error_limit_m'] for e in map_errors.values())
                / len(map_errors)) if map_errors else None
    map_pass = (map_path is not None and len(truth) >= limits['min_obstacles']
                and fraction is not None and fraction >= limits['map_fraction_min'])
    return dict(distance_definition='forward from point below lens', obstacle_ids=len(groups),
                excluded_ids=sorted(excluded), distance_obstacle_ids=overall['measured_ids'],
                missing_distance_ids=overall['missing_ids'],
                distance_median_relative_error=overall['median_relative_error'],
                distance_p90_relative_error=overall['p90_relative_error'], distance_pass=distance_pass,
                by_floor=by_floor, floor_comparison_complete=bool(floor_complete),
                missing_floor_types=[k for k,v in by_floor.items() if not v['obstacle_ids']],
                map_eligible_ids=len(truth), map_excluded_ids=[k for k in groups if k not in truth],
                map_fraction_within_20cm=fraction, map_pass=map_pass, map_error_m_by_id=map_errors,
                passed=distance_pass and map_pass, acceptance=limits,
                protocol='forward errors: median per obstacle then median/p90 per floor; map: confirmed world contacts only')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--observations', required=True)
    ap.add_argument('--annotations', required=True)
    ap.add_argument('--map')
    ap.add_argument('--out', required=True)
    ap.add_argument('--config')
    a = ap.parse_args()
    try:
        result = evaluate(a.observations, a.annotations, a.map, a.config)
    except (ValueError, FileNotFoundError) as e:
        ap.error(str(e))
    path = Path(a.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['passed'] else 1)


if __name__ == '__main__':
    main()
