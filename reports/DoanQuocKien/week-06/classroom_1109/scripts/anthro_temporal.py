"""Experiment A, round 7: temporal version of the trunk-length range. Fixed in advance: prior 0.50 m, keypoint confidence gate 0.8, causal median over the last 10 valid frames."""
import glob
import json
import math

import cv2
import numpy as np
from ultralytics import YOLO

from sentry.perception.camera import CameraGeometry

R = r"D:\CS532\Autonomous Collaborative Sentry Robot"
S = r"C:\Users\admin\AppData\Local\Temp\claude\7d42f4b8484190a4\68b819fd-108d-41fb-a937-45b34bdd1b82\scratchpad"
g = CameraGeometry.from_files(R + r"\calib\camera.json", R + r"\calib\camera_pose_self_1109_4.json")
K = g.K
cp, sp = math.cos(g.pitch), math.sin(g.pitch)
pose = YOLO(R + r"\yolov8n-pose.pt")
TRUNK_M, CONF, WIN, TOL = 0.50, 0.8, 10, 0.15
SETS = {"1.25 m (home_4_1)": (R + r"\data\pursuit\home_4_1\frames", 10.0, 1.25),
        "1.77 m (home_6_1)": (R + r"\data\pursuit\home_6_1\frames", 8.0, 1.77),
        "1.80 m (box_1p8_1)": (R + r"\data\pursuit\box_1p8_1\frames", None, 1.80)}


def trunk_range(bgr):
    r = pose(bgr, verbose=False, conf=0.3)[0]
    if r.keypoints is None or len(r.boxes) < 1:
        return None
    i = int(np.argmax(r.boxes.conf.cpu().numpy()))
    c = r.keypoints.conf[i].cpu().numpy()
    if min(c[5], c[6], c[11], c[12]) < CONF:
        return None
    pts = g.undistort_points(r.keypoints.xy[i].cpu().numpy())
    sm, hm = (pts[5] + pts[6]) / 2, (pts[11] + pts[12]) / 2
    px = float(np.linalg.norm(sm - hm))
    if px < 5:
        return None
    mid = (sm + hm) / 2
    y = (mid[1] - K[1, 2]) / K[1, 1]
    return K[0, 0] * TRUNK_M / px * (cp - sp * y)


out = {}
print("%-20s %6s %6s | %-34s | %-34s" % ("set", "frames", "gated", "raw: median err, within +/-0.15 m", "smoothed (median of 10): median err, within"), flush=True)
for name, (folder, tmin, tape) in SETS.items():
    fs = sorted(glob.glob(folder + r"\*.jpg"))
    if tmin is not None:
        fs = [f for f in fs if float(f.split("\\")[-1][:-4]) >= tmin]
    raw, sm = [], []
    window = []
    for f in fs:
        v = trunk_range(cv2.imread(f))
        if v is None or not math.isfinite(v):
            continue
        raw.append(v)
        window = (window + [v])[-WIN:]
        sm.append(float(np.median(window)))
    raw, sm = np.array(raw), np.array(sm)
    smv = sm[WIN - 1:]                                   # only once the window is full
    fr = lambda a: 100 * np.mean(np.abs(a - tape) <= TOL)
    print("%-20s %6d %6d | %+.2f m   %3.0f %%   (sd %.2f)        | %+.2f m   %3.0f %%   (sd %.2f)" % (name, len(fs), len(raw), np.median(raw) - tape, fr(raw), raw.std(), np.median(smv) - tape, fr(smv), smv.std()), flush=True)
    out[name] = {"tape": tape, "frames": len(fs), "gated": len(raw), "raw": raw.tolist(), "smoothed": sm.tolist()}
json.dump(out, open(S + r"\anthro_temporal_result.json", "w"))
