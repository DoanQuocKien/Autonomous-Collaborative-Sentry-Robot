"""D1 checkerboard photos from the JetBot camera, guided: the image is split into a 4x4 grid; the yellow box is the cell with the fewest checkerboard corners so far (counted over the photos already saved).
Put the board so it covers the yellow box, wait for FOUND, press SPACE. Only photos that put enough corners into the box are saved. n = skip this cell (unreachable), q = quit.

    python -m tools.capture_checkerboard            # saves to data/D1/checkerboard/
Needs camera_pub.py running on the robot. Calibration (fisheye, 160 deg) is poorly constrained wherever the board never appeared, so the edges and corners matter most.
"""
import argparse
from pathlib import Path

import cv2
import numpy as np
import zmq

from tools.find_jetbot import resolve
from tools.record import load_config

PATTERN = (9, 6)  # inner corners (tools/make_markers.py: 10x7 squares)
GRID = (4, 4)     # rows, cols
NEED = 40         # corners wanted per cell
MIN_IN_CELL = 6   # corners a new photo must put into the target cell
FLAGS = cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE


def find(gray, fast=False):
    found, c = cv2.findChessboardCorners(gray, PATTERN, FLAGS | (cv2.CALIB_CB_FAST_CHECK if fast else 0))
    return c.reshape(-1, 2) if found else None


def cells(corners, shape):
    """Corners per grid cell for one photo."""
    h, w = shape
    n = np.zeros(GRID, int)
    for x, y in corners:
        n[min(int(y / h * GRID[0]), GRID[0] - 1), min(int(x / w * GRID[1]), GRID[1] - 1)] += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/D1/checkerboard")
    ap.add_argument("--ip", default=None)
    a = ap.parse_args()
    cfg = load_config()
    ip = resolve(a.ip or cfg["net"]["jetbot_ip"])
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    count, n = np.zeros(GRID, int), 0
    for f in sorted(out.glob("*.jpg")):  # what is already covered
        g = cv2.imread(str(f), cv2.IMREAD_GRAYSCALE)
        c = find(g)
        if c is not None:
            count += cells(c, g.shape)
            n += 1
    print("%d photos so far; cell counts (want >= %d each):\n%s" % (n, NEED, count))
    skipped = set()
    sock = zmq.Context().socket(zmq.SUB)
    sock.setsockopt_string(zmq.SUBSCRIBE, "")
    sock.connect("tcp://%s:%d" % (ip, cfg["net"]["video_port"]))
    print("connected to %s" % ip)
    while True:
        if not sock.poll(2000):
            print("no frames from %s (is camera_pub.py running?)" % ip)
            continue
        while True:  # CONFLATE cannot do two-part messages: read everything queued, keep the newest
            jpeg = sock.recv_multipart()[1]
            if not sock.poll(0):
                break
        img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        h, w = img.shape[:2]
        todo = [(count[r, c], r, c) for r in range(GRID[0]) for c in range(GRID[1]) if count[r, c] < NEED and (r, c) not in skipped]
        view = img.copy()
        corners = find(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), fast=True)
        ok, msg = False, "coverage complete - q to quit"
        if todo:
            _, r, c = min(todo)
            x0, x1, y0, y1 = c * w // GRID[1], (c + 1) * w // GRID[1], r * h // GRID[0], (r + 1) * h // GRID[0]
            cv2.rectangle(view, (x0, y0), (x1 - 1, y1 - 1), (0, 255, 255), 3)
            have = cells(corners, (h, w))[r, c] if corners is not None else 0
            ok = have >= MIN_IN_CELL
            msg = "cell %d/%d  %d of %d corners  |  %s  |  %d left" % (r + 1, c + 1, count[r, c], NEED, "SPACE to save" if ok else "cover the yellow box", len(todo))
        if corners is not None:
            cv2.drawChessboardCorners(view, PATTERN, corners.reshape(-1, 1, 2), True)
        cv2.putText(view, "%d saved" % n, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(view, msg, (10, h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0) if ok else (0, 200, 255), 2)
        cv2.imshow("checkerboard", view)
        k = cv2.waitKey(1) & 0xFF
        if k == ord("q"):
            break
        if k == ord("n") and todo:
            skipped.add((r, c))
        if k == ord(" ") and (ok or not todo) and corners is not None:
            n += 1
            count += cells(corners, (h, w))
            (out / ("cb_%03d.jpg" % (len(list(out.glob("*.jpg"))) + 1))).write_bytes(jpeg)  # the original JPEG, not re-encoded
            print("saved", n)


if __name__ == "__main__":
    main()
