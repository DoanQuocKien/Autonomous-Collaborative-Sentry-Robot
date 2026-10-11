"""Camera height H_cam and down-tilt from floor marks at known distances (Week 2, Implementation Plan: "measure H_cam").

  1. Robot on a level floor, camera as it will be used (wedge on or off: do both, one --tag each). Lay tape strips across the floor straight ahead
     of the lens at the distances in --marks, measured from the point on the floor directly UNDER THE LENS (plumb line: a weight on a string).
  2. python -m tools.measure_camera_pose --marks 0.3 0.5 0.75 1.0 1.5 2.0 --h-tape 0.105 --tag nowedge
     It grabs a frame from the robot (or --image file), undistorts it with calib/camera.json, and you click the two ENDS of the near edge of each strip (left, right) in the
     order of --marks (u = undo, Enter = done). It fits H_cam and the pitch of  d = H / tan(pitch + atan((v - cy) / fy)).
  3. --h-tape is the lens height measured with a tape: the fit must agree within 1.5 cm (a tape cannot find a fisheye lens's optical centre better than that), otherwise a mark or a distance is wrong.
Writes calib/camera_pose_<tag>.json and an annotated picture next to it (evidence: copy to reports/<handle>/week-NN/).
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np


def fit_pose(v_px, d_m, fy, cy):
    """v_px: image rows (undistorted) of marks at ground distances d_m (from the point under the lens). -> (H_m, pitch_deg, rms_m, residuals_m)."""
    from scipy.optimize import least_squares
    v, d = np.asarray(v_px, float), np.asarray(d_m, float)
    beta = np.arctan((v - cy) / fy)

    def resid(p):
        a = p[1] + beta
        return p[0] / np.tan(np.clip(a, 1e-3, math.pi / 2 - 1e-3)) - d

    best = min((least_squares(resid, [h0, math.radians(p0)]) for h0 in (0.08, 0.15) for p0 in (0, 15)), key=lambda s: s.cost)
    r = resid(best.x)
    return float(best.x[0]), math.degrees(best.x[1]), float(np.sqrt(np.mean(r ** 2))), r


def undistorted(img, cam):
    import cv2
    K, D = np.array(cam["K"]), np.array(cam["D"])
    h, w = img.shape[:2]
    m1, m2 = cv2.fisheye.initUndistortRectifyMap(K, D, np.eye(3), K, (w, h), cv2.CV_16SC2)  # same K: fy, cy stay valid
    return cv2.remap(img, m1, m2, cv2.INTER_LINEAR)


def centre_rows(pts, cx, cy=None):
    """pts: 2 clicks per strip (one at each end). -> rows at x = cx, slopes (deg), roll (deg).
    The median slope is taken as camera roll and the clicks are rotated about (cx, cy) by -roll first; a strip that still deviates from it is a badly laid strip."""
    pts = [q for a, b in zip(pts[0::2], pts[1::2]) for q in sorted([a, b])]   # left end first, whichever end was clicked first
    slopes = [math.degrees(math.atan2(y2 - y1, x2 - x1)) for (x1, y1), (x2, y2) in zip(pts[0::2], pts[1::2])]
    roll = float(np.median(slopes)) if cy is not None else 0.0
    if roll:
        c, s_ = math.cos(math.radians(-roll)), math.sin(math.radians(-roll))
        pts = [(cx + c * (x - cx) - s_ * (y - cy), cy + s_ * (x - cx) + c * (y - cy)) for x, y in pts]
    rows = []
    for (x1, y1), (x2, y2) in zip(pts[0::2], pts[1::2]):
        if x1 == x2:
            raise ValueError("click the two ends of a strip at different x")
        rows.append(y1 + (y2 - y1) * (cx - x1) / (x2 - x1))
    return rows, slopes, roll


def click_rows(img, n):
    import cv2
    pts, shown = [], img.copy()
    cv2.line(shown, (int(img.shape[1] / 2), 0), (int(img.shape[1] / 2), img.shape[0]), (255, 0, 0), 1)

    def draw():
        shown[:] = img
        for i, (x, y) in enumerate(pts):
            cv2.circle(shown, (x, y), 3, (0, 255, 0), -1)
            if i % 2:
                cv2.line(shown, pts[i - 1], (x, y), (0, 255, 0), 1)
                cv2.putText(shown, str(i // 2 + 1), (x + 4, y - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    def on(ev, x, y, *_):
        if ev == cv2.EVENT_LBUTTONDOWN and len(pts) < 2 * n:
            pts.append((x, y))
            draw()

    cv2.namedWindow("marks")
    cv2.setMouseCallback("marks", on)
    while True:
        cv2.imshow("marks", shown)
        k = cv2.waitKey(30) & 0xFF
        if k == ord("u") and pts:
            pts.pop()
            draw()
        elif k in (13, 32) and len(pts) == 2 * n:
            break
        elif k == ord("q"):
            raise SystemExit("aborted")
    cv2.destroyAllWindows()
    return pts, shown


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--marks", type=float, nargs="+", required=True, help="ground distances (m) from the point under the lens, near to far")
    ap.add_argument("--h-tape", type=float, required=True, help="lens height above the floor, measured with a tape (m)")
    ap.add_argument("--tag", default="nowedge")
    ap.add_argument("--image", help="use this photo instead of grabbing a frame from the robot")
    ap.add_argument("--camera", default="calib/camera.json")
    ap.add_argument("--max-rms-m", type=float, default=0.03)
    a = ap.parse_args()
    import cv2
    cam = json.load(open(a.camera))
    if a.image:
        img = cv2.imread(a.image)
    else:
        from sentry.net.zmq_rx import ZMQReceiver
        with ZMQReceiver() as rx:
            f = rx.read(timeout=10)
        img = f.frame_bgr
    und = undistorted(img, cam)
    Path("calib").mkdir(exist_ok=True)
    cv2.imwrite("calib/camera_pose_%s_raw.jpg" % a.tag, img)   # the untouched frame, so a run can be redone with --image
    pts, shown = click_rows(und, len(a.marks))
    fy, cx, cy = cam["K"][1][1], cam["K"][0][2], cam["K"][1][2]
    rows, slopes, roll = centre_rows(pts, cx, cy)
    H, pitch, rms, res = fit_pose(rows, a.marks, fy, cy)
    problems = []
    if max(slopes) - min(slopes) > 6:   # strips are only ~30 px wide in the image: 1 px of click error = 2 deg
        problems.append("the strips slope by different angles (%.1f to %.1f deg): not laid parallel, or marks not square to the camera" % (min(slopes), max(slopes)))
    if abs(H - a.h_tape) > 0.015:
        problems.append("fitted H %.3f m differs from the tape %.3f m by more than 1.5 cm" % (H, a.h_tape))
    if rms > a.max_rms_m:
        problems.append("rms %.1f cm > %.0f cm: a mark or a distance is off (residuals %s cm)" % (100 * rms, 100 * a.max_rms_m, np.round(100 * res, 1).tolist()))
    out = {"tag": a.tag, "H_cam_m": round(H, 4), "H_tape_m": a.h_tape, "pitch_down_deg": round(pitch, 2), "rms_m": round(rms, 4),
           "marks_m": a.marks, "clicks_px": [list(q) for q in pts], "rows_px": [round(r, 1) for r in rows], "camera_roll_deg": round(roll, 2), "strip_slopes_deg": [round(x, 2) for x in slopes], "residuals_m": np.round(res, 4).tolist(), "passed": not problems, "problems": problems}
    p = Path("calib") / ("camera_pose_%s.json" % a.tag)
    p.write_text(json.dumps(out, indent=2), encoding="utf-8")
    cv2.imwrite(str(p.with_suffix(".jpg")), shown)
    print(json.dumps(out, indent=2))
    print("PASS" if not problems else "FAIL: " + "; ".join(problems))
    print("wrote", p)


if __name__ == "__main__":
    main()
