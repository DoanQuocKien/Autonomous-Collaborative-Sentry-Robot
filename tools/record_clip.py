"""Record a timed clip of the JetBot camera (no ESP32, no motors) and print the start and end clock times for the D1 CSVs.

  python -m tools.record_clip D1_obstacles_1015/set2 6        # 6 s into data/D1_obstacles_1015/set2/jetbot (frames + jetbot_meta.jsonl)
The robot stays still; no arming is needed (nothing is sent to the motors).
"""
import argparse
import threading
import time
from datetime import datetime
from pathlib import Path

from sentry.config import load as load_config
from tools.find_jetbot import resolve
from tools.record import record_jetbot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir", help="directory name inside data/")
    ap.add_argument("seconds", type=float)
    a = ap.parse_args()
    cfg = load_config()
    ip = resolve(cfg["net"]["jetbot_ip"])
    out = Path(__file__).parent.parent / "data" / a.out_dir
    stop = threading.Event()
    errors = []

    def worker():
        try:
            record_jetbot(ip, cfg["net"]["video_port"], out, stop)
        except BaseException as exc:
            errors.append(exc)

    t = threading.Thread(target=worker, daemon=True)
    t0 = datetime.now()
    t.start()
    time.sleep(a.seconds)
    t1 = datetime.now()
    stop.set()
    t.join(cfg["telemetry"]["frame_timeout_s"] + cfg["net"]["video_join_timeout_s"])
    n = len(list((out / "jetbot").glob("*.jpg")))
    print("RECORDED %s: %d frames | start %s end %s%s" % (out, n, t0.strftime("%H:%M:%S"), t1.strftime("%H:%M:%S"), " | ERROR %s" % errors[0] if errors else ""))


if __name__ == "__main__":
    main()
