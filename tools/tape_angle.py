"""Correct a camera-pose run for a tape that was not laid exactly along the optical axis.

  python -m tools.tape_angle --image calib/camera_pose_nowedge.jpg --run calib/camera_pose_nowedge.json
Click the START (near end) and the END (far end) of the tape in the UNDISTORTED picture, then Enter. The tape's vanishing point gives its angle to the
optical axis (yaw); marks at tape distance s are then s*cos(yaw) ahead of the lens. Refits H and pitch and writes <run>_yawfix.json.
"""
import argparse
import json
import math

import numpy as np

from tools.measure_camera_pose import fit_pose


def tape_yaw_deg(p0, p1, cx, fx, horizon_row):
    """p0, p1: two points (x, y) on the tape in the undistorted image; horizon_row: row of the horizon. -> angle of the tape to the optical axis, degrees."""
    (x0, y0), (x1, y1) = p0, p1
    if y0 == y1:
        raise ValueError("start and end of the tape are on the same row")
    x_vp = x0 + (x1 - x0) * (horizon_row - y0) / (y1 - y0)   # where the line reaches the horizon
    return math.degrees(math.atan((x_vp - cx) / fx))


def main():
    import cv2
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--run", required=True, help="the camera_pose_<tag>.json of that photo")
    ap.add_argument("--camera", default="calib/camera.json")
    a = ap.parse_args()
    cam, run = json.load(open(a.camera)), json.load(open(a.run))
    fx, fy, cx, cy = cam["K"][0][0], cam["K"][1][1], cam["K"][0][2], cam["K"][1][2]
    img, pts = cv2.imread(a.image), []

    def on(ev, x, y, *_):
        if ev == cv2.EVENT_LBUTTONDOWN and len(pts) < 2:
            pts.append((x, y))
            cv2.circle(img, (x, y), 4, (0, 0, 255), -1)

    cv2.namedWindow("tape")
    cv2.setMouseCallback("tape", on)
    print("click the near end, then the far end of the tape; Enter = done, q = abort")
    while True:
        cv2.imshow("tape", img)
        k = cv2.waitKey(30) & 0xFF
        if k == ord("q"):
            raise SystemExit("aborted")
        if k in (13, 32) and len(pts) == 2:
            break
    cv2.destroyAllWindows()
    horizon = cy - fy * math.tan(math.radians(run["pitch_down_deg"]))   # level camera: horizon at cy; pitched down: above it
    yaw = tape_yaw_deg(pts[0], pts[1], cx, fx, horizon)
    d = [m * math.cos(math.radians(yaw)) for m in run["marks_m"]]
    H, pitch, rms, res = fit_pose(run["rows_px"], d, fy, cy)
    out = dict(run, tape_yaw_deg=round(yaw, 2), H_cam_m=round(H, 4), pitch_down_deg=round(pitch, 2), rms_m=round(rms, 4), forward_m=[round(x, 3) for x in d],
               residuals_m=np.round(res, 4).tolist(), tape_clicks=pts)
    p = a.run.replace(".json", "_yawfix.json")
    open(p, "w").write(json.dumps(out, indent=2))
    print("tape yaw %.2f deg: H %.4f m (tape %.3f), pitch %.2f deg down, rms %.1f cm -> %s" % (yaw, H, run["H_tape_m"], pitch, 100 * rms, p))


if __name__ == "__main__":
    main()
