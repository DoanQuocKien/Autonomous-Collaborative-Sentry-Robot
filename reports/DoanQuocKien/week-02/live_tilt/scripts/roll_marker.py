"""Camera roll from the recorded frames: PnP roll of centred markers, per run, plus the slope of the marker's horizontal edges."""
import glob, math, os, sys
import cv2, numpy as np
from sentry.perception.camera import CameraGeometry
from sentry.perception.camera_pose import detect_corners, pose_from_corners

SP = os.path.dirname(os.path.abspath(__file__))
g = CameraGeometry.from_files("calib/camera.json", "calib/camera_pose_tilt_ref.json")
S, BOTTOM = 0.15, 0.132
runs = {"run4_v0.7": "run_rec_v07", "run5_v0.4": "run_rec", "servo1": "run_servo_1", "servo3": "run_servo_3", "servo_last": "run_servo"}
out = {}
for name, d in runs.items():
    files = sorted(glob.glob(os.path.join(SP, d, "f*.jpg")))
    rolls, slopes, bears, dists = [], [], [], []
    for f in files:
        im = cv2.imread(f)
        found = detect_corners(im)
        if not found:
            continue
        c = g.undistort_points(found[0][1])
        e = pose_from_corners(c, g.K, S, BOTTOM, g.height_m)
        if e is None or e["reproj_px"] > 1.0:
            continue
        b = math.degrees(e["bearing_rad"])
        if abs(b) > 6:                                    # centred markers only
            continue
        top = math.degrees(math.atan2(c[1][1] - c[0][1], c[1][0] - c[0][0]))
        bot = math.degrees(math.atan2(c[2][1] - c[3][1], c[2][0] - c[3][0]))
        left = math.degrees(math.atan2(c[3][0] - c[0][0], c[3][1] - c[0][1]))
        right = math.degrees(math.atan2(c[2][0] - c[1][0], c[2][1] - c[1][1]))
        rolls.append(e["roll_deg"]); slopes.append((top + bot) / 2); bears.append(b); dists.append(e["distance_m"])
        out.setdefault(name, []).append((e["roll_deg"], (top + bot) / 2, -(left + right) / 2, e["distance_m"], b))
    if rolls:
        a = np.array(out[name])
        print("%-11s %3d centred frames, dist %.2f-%.2f m | PnP roll median %+.2f (std %.2f) | horizontal edges %+.2f (std %.2f) | vertical edges %+.2f (std %.2f)" % (
            name, len(a), a[:, 3].min(), a[:, 3].max(), np.median(a[:, 0]), a[:, 0].std(), np.median(a[:, 1]), a[:, 1].std(), np.median(a[:, 2]), a[:, 2].std()))
allv = np.vstack([np.array(v) for v in out.values()])
print("ALL %d frames: PnP roll median %+.2f; horizontal-edge slope median %+.2f; vertical-edge tilt median %+.2f (deg; image y points down)" % (len(allv), np.median(allv[:, 0]), np.median(allv[:, 1]), np.median(allv[:, 2])))
near = allv[allv[:, 3] < 1.2]
print("near (<1.2 m) %d frames: PnP roll %+.2f, horizontal edges %+.2f, vertical edges %+.2f" % (len(near), np.median(near[:, 0]), np.median(near[:, 1]), np.median(near[:, 2])))
