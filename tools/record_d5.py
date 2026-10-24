"""Record D5 (floor-level objects from the robot's own camera): N frames of one class at one distance.

  python -m tools.record_d5 shoe --floor glossy --dist 0.5 --n 10

Frames are the raw JPEGs from the robot (no undistortion), one every --gap seconds so they are not near-duplicates, saved to
data/D5/<class>/<floor>_<dist>m_<session>_<NNN>.jpg and listed in data/D5/manifest.csv (class, file, floor, dist_m, session, time).
Move or change the object between calls (position, angle, lighting): 50 near-identical frames count as one. No labels here: they come later.
"""
import argparse
import csv
import time
from pathlib import Path

from sentry.net.zmq_rx import ZMQReceiver


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cls", help="leg, wire_black, wire_white, shoe, slipper, backpack, bag, furniture, empty")
    ap.add_argument("--floor", required=True, choices=["glossy", "matte"])
    ap.add_argument("--dist", type=float, required=True, help="tape distance from the lens to the object, m")
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--gap", type=float, default=0.7, help="seconds between saved frames")
    ap.add_argument("--session", default=time.strftime("%m%d"), help="held-out units for the T1 are whole sessions: change it per day or room")
    a = ap.parse_args()
    root = Path("data/D5")
    (root / a.cls).mkdir(parents=True, exist_ok=True)
    manifest = root / "manifest.csv"
    new = not manifest.exists()
    k = max([int(f.stem.split("_")[-1]) for f in (root / a.cls).glob("*.jpg")], default=-1) + 1   # never reuse a number: files moved out of the class would make a count collide
    saved, last = 0, 0.0
    with ZMQReceiver() as rx, manifest.open("a", newline="") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["class", "file", "floor", "dist_m", "session", "time"])
        while saved < a.n:
            f = rx.read(timeout=10)
            if f is None:
                raise SystemExit("no frames from the robot")
            if time.perf_counter() - last < a.gap:
                continue
            last = time.perf_counter()
            name = "%s_%.2fm_%s_%03d.jpg" % (a.floor, a.dist, a.session, k)
            (root / a.cls / name).write_bytes(f.jpeg)
            w.writerow([a.cls, "%s/%s" % (a.cls, name), a.floor, a.dist, a.session, time.strftime("%Y-%m-%d %H:%M:%S")])
            k += 1
            saved += 1
    print("saved %d %s frames (%s, %.2f m); %d in total for the class" % (saved, a.cls, a.floor, a.dist, k))


if __name__ == "__main__":
    main()
