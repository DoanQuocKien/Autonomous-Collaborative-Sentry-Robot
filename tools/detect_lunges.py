"""Offline D4 pose/strike prediction from tools.record. Writes private JSONL.

    python -m tools.detect_lunges --recording data/D4/session --out-dir data/D4/session/pose-01

No live receiver or motor transport. Capture timestamps drive the 100 ms cue;
t_local stays in `t` for KR's label_events/false-trigger harness. This is not a
frame-to-command measurement. Multiple visible people are ambiguous here; live
callers must supply their selected target's stable track_id/epoch to the API.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path

import cv2
import numpy as np

from sentry.config import DEFAULT_PATH
from sentry.perception.pose import LungeDetector, YOLOPoseEstimator
from tools.prepare_d3_recording import audit

ROOT = DEFAULT_PATH.parent


def run(recording, out_dir, estimator, data_root=None):
    data_root = ROOT/'data' if data_root is None else Path(data_root)
    out_dir = Path(out_dir).resolve()
    if not out_dir.is_relative_to(data_root.resolve()):
        raise ValueError('private pose predictions must stay under data/')
    if out_dir.exists():
        raise FileExistsError('choose a new output directory')
    recording, metadata, epochs = audit(recording, data_root)
    if recording.is_relative_to(out_dir) or out_dir.is_relative_to(recording/'jetbot'):
        raise ValueError('output must not contain or replace raw recordings')
    original = metadata.read_text(encoding='utf-8-sig').splitlines()
    last_t = None
    for epoch in epochs:
        for row in epoch:
            local = json.loads(original[row['source_line']-1]).get('t_local')
            if isinstance(local, bool) or not isinstance(local, (int, float)) or not math.isfinite(local):
                raise ValueError('finite t_local required for label alignment')
            if last_t is not None and local <= last_t:
                raise ValueError('t_local must increase; split recordings at wall-clock resets')
            row['t_local'] = last_t = local
    out_dir.mkdir(parents=True)
    detector = LungeDetector()
    counts = dict(frames=0, strikes=0, ambiguous=0, missing=0)
    with (out_dir/'pose.jsonl').open('x', encoding='utf-8') as raw, (out_dir/'strikes.jsonl').open('x', encoding='utf-8') as strikes:
        for index, epoch in enumerate(epochs):
            detector.reset()
            for row in epoch:
                content = row['source_image'].read_bytes()
                if hashlib.sha256(content).hexdigest() != row['image_sha256']:
                    raise ValueError('image changed after recording audit')
                image = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), cv2.IMREAD_COLOR)
                if image is None:
                    raise ValueError('image became unreadable during inference')
                people = estimator.predict(image)
                person = people[0] if len(people) == 1 else None
                sample = dict(t=row['t_local'], t_cap=row['t'], epoch=index, seq=row['seq'],
                    frame_size=[row['w'], row['h']], image_sha256=row['image_sha256'],
                    people_count=len(people), bbox=None if person is None else person.xyxy,
                    keypoints_xy=None if person is None else person.keypoints_xy.tolist(),
                    keypoints_conf=None if person is None else person.keypoints_conf.tolist())
                hit = detector(sample['t'], sample)
                raw.write(json.dumps(sample, allow_nan=False)+'\n')
                strikes.write(json.dumps(dict(sample, strike=hit, lunge=asdict(detector.last_result)), allow_nan=False)+'\n')
                counts['frames'] += 1
                counts['strikes'] += int(hit)
                counts['ambiguous'] += int(len(people) > 1)
                counts['missing'] += int(not people)
    summary = dict(counts, complete=True, motor_commands_sent=0, t1_passed=False,
        metadata_sha256=hashlib.sha256(metadata.read_bytes()).hexdigest(),
        detector_settings=asdict(detector.settings),
        model_weights_sha256=hashlib.sha256(estimator.weights.read_bytes()).hexdigest(),
        device=estimator.actual_device, detector_clock='jetbot t_cap',
        label_clock='laptop t_local; receiving/recording time, not exposure or motor-command time',
        outputs={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (out_dir/'pose.jsonl', out_dir/'strikes.jsonl')})
    (out_dir/'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--recording', type=Path, required=True)
    ap.add_argument('--out-dir', type=Path, required=True)
    ap.add_argument('--weights', type=Path)
    ap.add_argument('--device', default=None)
    args = ap.parse_args()
    estimator = YOLOPoseEstimator(args.weights, device=args.device)
    print(json.dumps(run(args.recording, args.out_dir, estimator), indent=2))


if __name__ == '__main__':
    main()
