"""Record a chair at taped distances from the robot's own camera (robot standing still, no commands sent), to fit a box-size range curve.

    python -m tools.record_chair_ranges --label chair_1113 --distances 0.6 0.9 1.2 1.5 1.8 2.4

For each distance: TWO beeps, then 10 s (--adjust-s) to put the chair on the mark, then N frames (default 12, 0.25 s apart). One long low tone = finished.
Frames go to data/furniture/<label>/d<dist>/NN.jpg (data/ is git-ignored). The distance is what YOU measured (lens to the chair's front legs along the camera axis)."""
import argparse
import time
from pathlib import Path

import cv2

from sentry.net.zmq_rx import ZMQReceiver


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--distances", type=float, nargs="+", required=True)
    ap.add_argument("--frames", type=int, default=12)
    ap.add_argument("--adjust-s", type=float, default=10.0)
    ap.add_argument("--start-delay-s", type=float, default=0.0)
    ap.add_argument("--ip", default="auto")
    ap.add_argument("--out", default="data/furniture")
    a = ap.parse_args()
    import winsound
    rx = ZMQReceiver(ip=a.ip).start()
    try:
        if rx.read(timeout=10.0) is None:
            raise SystemExit("no video from the robot")
        time.sleep(a.start_delay_s)
        for d in a.distances:
            print("next: %.2f m, adjust now" % d, flush=True)
            for _ in range(2):
                winsound.Beep(1000, 200)
                time.sleep(0.2)
            time.sleep(a.adjust_s)
            folder = Path(a.out) / a.label / ("d%.2f" % d)
            folder.mkdir(parents=True, exist_ok=True)
            n = 0
            while n < a.frames:
                f = rx.read(timeout=2.0)
                if f is None:
                    raise SystemExit("video stopped at %.2f m (%d frames)" % (d, n))
                cv2.imwrite(str(folder / ("%02d.jpg" % n)), f.frame_bgr)
                n += 1
                time.sleep(0.25)
            print("saved %d frames at %.2f m" % (n, d), flush=True)
        winsound.Beep(500, 1500)
    finally:
        rx.close()


if __name__ == "__main__":
    main()
