"""Read JetBot latest frames and log tracking privately; never send motor commands."""
import argparse
import json
from pathlib import Path
import time

from sentry.perception.tracker import PersonTracker


def run(ip, out, seconds, target=None):
    import math
    import numpy as np
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError('positive finite duration required')
    out = Path(out).resolve()
    if not out.is_relative_to(Path('data').resolve()):
        raise ValueError('private tracking logs must stay under data/')
    tracker = PersonTracker.from_config()
    if target:
        with np.load(target, allow_pickle=False) as d:
            tracker.set_target(d['vector'], str(d['model_id'].item()))
    from sentry.net.zmq_rx import ZMQReceiver
    start, previous_seq = time.monotonic(), None
    out.parent.mkdir(parents=True, exist_ok=True)
    with ZMQReceiver(ip=ip) as rx, out.open('w', encoding='utf-8') as log:
        while time.monotonic() - start < seconds:
            frame = rx.read(timeout=.5)
            if frame is None:
                continue
            if previous_seq is not None and frame.seq <= previous_seq:
                tracker.reset()
            previous_seq = frame.seq
            r = tracker(frame.frame_bgr, frame.t_cap)
            row = dict(seq=frame.seq, t=r.t, epoch=r.epoch, lock_state=r.lock_state,
                       target_key=r.target.key if r.target else None, model_id=r.model_id,
                       tracks=[dict(track_id=p.track_id, xyxy=p.xyxy, confidence=p.confidence) for p in r.tracks])
            log.write(json.dumps(row) + '\n')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--ip', default='auto')
    ap.add_argument('--seconds', type=float, default=60.)
    ap.add_argument('--out', required=True)
    ap.add_argument('--target')
    a = ap.parse_args()
    run(a.ip, a.out, a.seconds, a.target)


if __name__ == '__main__':
    main()
