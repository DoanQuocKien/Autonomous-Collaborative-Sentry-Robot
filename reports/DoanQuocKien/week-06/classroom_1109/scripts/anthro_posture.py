import glob
import math

import cv2
import numpy as np
from ultralytics import YOLO

from sentry.perception.camera import CameraGeometry

R = r"D:\CS532\Autonomous Collaborative Sentry Robot"
g = CameraGeometry.from_files(R + r"\calib\camera.json", R + r"\calib\camera_pose_self_1109_4.json")
K = g.K
pose = YOLO(R + r"\yolov8n-pose.pt")
SETS = {"1.25 m (home_4_1)": (R + r"\data\pursuit\home_4_1\frames", 10.0, 1.25, +0.16),
        "1.77 m (home_6_1)": (R + r"\data\pursuit\home_6_1\frames", 8.0, 1.77, -0.02),
        "1.80 m (box_1p8_1)": (R + r"\data\pursuit\box_1p8_1\frames", None, 1.80, +0.16)}
print("%-20s %6s | %8s %8s %7s | %10s %10s %9s | %8s %8s" % ("set", "bias m", "trunk px", "shld px", "box h", "trunk/h", "shld/trunk", "head/trunk", "tilt deg", "ear-hip"))
for name, (folder, tmin, tape, bias) in SETS.items():
    fs = sorted(glob.glob(folder + r"\*.jpg"))
    if tmin is not None:
        fs = [f for f in fs if float(f.split("\\")[-1][:-4]) >= tmin]
    fs = fs[::max(1, len(fs) // 40)][:40]
    rows = []
    for f in fs:
        r = pose(cv2.imread(f), verbose=False, conf=0.3)[0]
        if r.keypoints is None or len(r.boxes) < 1:
            continue
        i = int(np.argmax(r.boxes.conf.cpu().numpy()))
        c = r.keypoints.conf[i].cpu().numpy()
        if min(c[5], c[6], c[11], c[12]) < 0.8:
            continue
        p = g.undistort_points(r.keypoints.xy[i].cpu().numpy())
        b = r.boxes.xyxy[i].cpu().numpy()
        sm, hm = (p[5] + p[6]) / 2, (p[11] + p[12]) / 2
        trunk = float(np.linalg.norm(sm - hm))
        sh = float(np.linalg.norm(p[5] - p[6]))
        h = float(b[3] - b[1])
        tilt = math.degrees(math.atan2(sm[0] - hm[0], hm[1] - sm[1]))            # trunk lean in the image plane
        head = float(np.linalg.norm(p[3] - p[4])) if min(c[3], c[4]) > 0.5 else float("nan")
        rows.append((trunk, sh, h, trunk / h, sh / trunk, head / trunk, tilt, abs(p[0][1] - hm[1]) if c[0] > 0.5 else float("nan")))
    a = np.array(rows)
    med = np.nanmedian(a, axis=0)
    print("%-20s %+6.2f | %8.1f %8.1f %7.0f | %10.3f %10.3f %9.3f | %8.1f %8.1f" % (name, bias, med[0], med[1], med[2], med[3], med[4], med[5], med[6], med[7]))
