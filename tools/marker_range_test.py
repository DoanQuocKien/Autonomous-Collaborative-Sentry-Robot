"""How far and at what viewing angle is the 150 mm ArUco marker reliably detected, and how accurate is its range? (decides how many anchors a room needs and where)

  python -m tools.marker_range_test 1.0                 # robot still, board at 1.0 m by tape (lens to board): 3 s of frames
  python -m tools.marker_range_test 1.5 --yaw 30        # the board turned 30 deg away from facing the robot (label only)
Prints the detection rate (frames with the marker / frames), the median PnP range and its error against the tape, the marker's apparent side in pixels, and appends a row to data/marker_range_test.csv.
No motors, no arming.
"""
import argparse
import csv
import math
import os
import statistics
import time

import numpy as np

from sentry.config import load
from sentry.net.zmq_rx import ZMQReceiver
from sentry.perception.camera import CameraGeometry
from sentry.perception.camera_pose import detect_corners
from tools.speed_trial import marker_range


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tape_m", type=float, help="tape distance from the point under the lens to the board (m)")
    ap.add_argument("--yaw", type=float, default=0.0, help="how far the board is turned away from facing the robot (deg), for the record")
    ap.add_argument("--seconds", type=float, default=3.0)
    ap.add_argument("--camera", default="calib/camera.json")
    ap.add_argument("--pose", default="calib/camera_pose_nowedge.json", help="only K and D are used here")
    ap.add_argument("--out", default="data/marker_range_test.csv")
    a = ap.parse_args()
    S = load()["calibration"]["aruco_marker_m"] / 2
    g = CameraGeometry.from_files(a.camera, a.pose)
    obj = np.array([[-S, S, 0], [S, S, 0], [S, -S, 0], [-S, -S, 0]], np.float64)
    n = hit = 0
    ranges, sides, bears = [], [], []
    with ZMQReceiver() as rx:
        t0 = time.time()
        while time.time() - t0 < a.seconds:
            f = rx.read(timeout=5)
            if f is None:
                continue
            n += 1
            found = detect_corners(f.frame_bgr)
            mr = marker_range(g, obj, f.frame_bgr) if found else None
            if mr is not None:
                hit += 1
                ranges.append(mr[0])
                bears.append(mr[1])
                c = found[0][1]
                sides.append(float(np.mean([np.linalg.norm(c[i] - c[(i + 1) % 4]) for i in range(4)])))
    rate = hit / max(n, 1)
    med = statistics.median(ranges) if ranges else float("nan")
    err = med - a.tape_m if ranges else float("nan")
    print("TAPE %.2f m, board yaw %.0f deg: marker found in %d of %d frames (%.0f %%) | median range %.3f m (error %+.3f m = %+.1f %%) | side %.0f px | bearing %+.1f deg" % (
        a.tape_m, a.yaw, hit, n, 100 * rate, med, err, 100 * err / a.tape_m if ranges else float("nan"), statistics.median(sides) if sides else float("nan"), statistics.median(bears) if bears else float("nan")))
    new = not os.path.exists(a.out)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "a", newline="") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["tape_m", "board_yaw_deg", "frames", "found", "rate", "median_range_m", "range_error_m", "side_px", "bearing_deg"])
        w.writerow([a.tape_m, a.yaw, n, hit, "%.3f" % rate, "%.3f" % med, "%.3f" % err, "%.1f" % (statistics.median(sides) if sides else float("nan")), "%.1f" % (statistics.median(bears) if bears else float("nan"))])


if __name__ == "__main__":
    main()
