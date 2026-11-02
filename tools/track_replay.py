"""Replay timestamped frames through the exact live PersonTracker API.

Input JSON: frames=[{t,image}]. Image paths relative to the manifest. Optional
target NPZ has vector (512,) and scalar model_id. Predictions contain private
person boxes/track IDs, so output must stay under gitignored data/.
"""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from sentry.perception.tracker import PersonTracker


def run(manifest, out, target=None):
    manifest, out = Path(manifest), Path(out).resolve()
    data_root = Path('data').resolve()
    if not out.is_relative_to(data_root):
        raise ValueError('private predictions must be written under data/')
    frames = json.loads(manifest.read_text(encoding='utf-8'))['frames']
    if not frames:
        raise ValueError('nonempty timestamped replay required')
    tracker = PersonTracker.from_config()
    if target:
        with np.load(target, allow_pickle=False) as d:
            tracker.set_target(d['vector'], str(d['model_id'].item()))
    rows = []
    for frame in frames:
        image = cv2.imread(str(manifest.parent / frame['image']))
        result = tracker(image, frame['t'])
        rows.append(dict(t=result.t, tracks=[dict(track_id=p.track_id, epoch=p.epoch, xyxy=p.xyxy) for p in result.tracks],
                         target_key=result.target.key if result.target else None, lock_state=result.lock_state))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(dict(frames=rows, model_id=tracker.encoder.model_id, motor_commands_sent=0)), encoding='utf-8')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--manifest', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--target')
    a = ap.parse_args()
    run(a.manifest, a.out, a.target)


if __name__ == '__main__':
    main()
