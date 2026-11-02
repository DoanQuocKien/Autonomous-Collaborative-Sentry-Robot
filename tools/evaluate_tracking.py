"""D3 tracking evaluation with explicit misses, false positives and ID switches.

Truth JSON: kind=D3_TRACKING, reviewed=true, frames=[{t, objects:[{id,xyxy}]}].
Predictions: frames=[{t,tracks:[{track_id,epoch,xyxy}]}]. Every decoded frame,
including empty frames, must be represented with an exactly matched timestamp.
No images/vectors or person IDs are copied to the aggregate report.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment
from sentry.config import load


def box(value):
    b = np.asarray(value, np.float64)
    if b.shape != (4,) or not np.isfinite(b).all() or b[2] <= b[0] or b[3] <= b[1]:
        raise ValueError('finite positive xyxy required')
    return b


def iou(a, b):
    x1, y1 = np.maximum(a[:2], b[:2])
    x2, y2 = np.minimum(a[2:], b[2:])
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    union = np.prod(a[2:] - a[:2]) + np.prod(b[2:] - b[:2]) - intersection
    return float(intersection / union)


def evaluate(truth, predictions, min_iou=None, max_switches_per_minute=None, min_duration_s=None):
    settings = load()['tracking_validation']
    min_iou = settings['iou_min'] if min_iou is None else min_iou
    max_switches_per_minute = settings['max_id_switches_per_minute'] if max_switches_per_minute is None else max_switches_per_minute
    min_duration_s = settings['min_duration_s'] if min_duration_s is None else min_duration_s
    if not 0 < min_iou <= 1 or min_duration_s <= 0 or max_switches_per_minute < 0:
        raise ValueError('valid evaluation thresholds required')
    gt, pred = truth['frames'], predictions['frames']
    if len(gt) < 2 or len(gt) != len(pred):
        raise ValueError('at least two frames, including empty frames, required on both sides')
    last_t, previous, identities = None, {}, set()
    matches = misses = false_positives = switches = two_person_frames = 0
    for a, b in zip(gt, pred):
        t = a['t']
        if not math.isfinite(t) or t != b['t'] or (last_t is not None and t <= last_t):
            raise ValueError('finite increasing, exactly aligned frame timestamps required')
        last_t = t
        objects, tracks = a['objects'], b['tracks']
        ids = [str(o['id']) for o in objects]
        keys = [(int(p.get('epoch', 0)), int(p['track_id'])) for p in tracks]
        if len(ids) != len(set(ids)) or len(keys) != len(set(keys)):
            raise ValueError('duplicate truth identity or predicted track key in frame')
        identities.update(ids)
        two_person_frames += len(ids) >= 2
        gboxes, pboxes = [box(o['xyxy']) for o in objects], [box(p['xyxy']) for p in tracks]
        pairs = []
        if gboxes and pboxes:
            scores = np.array([[iou(g, p) for p in pboxes] for g in gboxes])
            rows, cols = linear_sum_assignment(np.where(scores >= min_iou, 1 - scores, 1e6))
            pairs = [(r, c) for r, c in zip(rows, cols) if scores[r, c] >= min_iou]
        matches += len(pairs)
        misses += len(objects) - len(pairs)
        false_positives += len(tracks) - len(pairs)
        for r, c in pairs:
            if ids[r] in previous and previous[ids[r]] != keys[c]:
                switches += 1
            previous[ids[r]] = keys[c]
    duration = gt[-1]['t'] - gt[0]['t']
    rate = switches * 60 / duration
    protocol = (truth.get('kind') == 'D3_TRACKING' and truth.get('reviewed') is True
                and truth.get('camera') == 'jetbot' and duration >= min_duration_s
                and len(identities) >= 2 and two_person_frames > 0)
    # No detections would have zero switches. Report the switch criterion
    # separately and never turn an empty/partial tracking result into T1 PASS.
    return dict(frames=len(gt), duration_s=duration, identities=len(identities),
                two_person_frames=int(two_person_frames), matched_instances=matches,
                missed_instances=misses, false_positive_instances=false_positives,
                detection_recall=matches / (matches + misses) if matches + misses else None,
                id_switches=switches, id_switches_per_minute=rate,
                switch_limit_met=rate <= max_switches_per_minute,
                protocol_complete=protocol,
                t1_passed=protocol and rate <= max_switches_per_minute and matches > 0 and misses == 0 and false_positives == 0,
                note='Conservative pass requires complete matches; plan switch limit is reported separately. '
                     'Switches count changes from each identity last matched key, including across gaps. '
                     'No-target-lock accuracy claim; ground truth visibility and IDs require manual review.',
                motor_commands_sent=0)


def run(truth_path, predictions_path, out):
    truth_path, predictions_path = Path(truth_path), Path(predictions_path)
    result = evaluate(json.loads(truth_path.read_text(encoding='utf-8')), json.loads(predictions_path.read_text(encoding='utf-8')))
    result['truth_sha256'] = hashlib.sha256(truth_path.read_bytes()).hexdigest()
    result['predictions_sha256'] = hashlib.sha256(predictions_path.read_bytes()).hexdigest()
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--truth', required=True)
    ap.add_argument('--predictions', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    result = run(a.truth, a.predictions, a.out)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['t1_passed'] else 1)


if __name__ == '__main__':
    main()
