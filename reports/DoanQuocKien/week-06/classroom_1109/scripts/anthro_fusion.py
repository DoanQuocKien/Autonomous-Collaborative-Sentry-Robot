"""Experiment A, round 8 (pre-registered): other body cues and fusion with the foot-row range. Priors (Drillis and Contini proportions, stature 1.70 m): trunk 0.49, hip-knee 0.42,
knee-ankle 0.42, shoulder-ankle 1.32 m. Gates: trunk keypoints 0.8, leg keypoints 0.6. Causal median of 10. Fusion = mean of the body-cue median and the foot-row range (offset 3.5 px)."""
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
PRIOR = {"trunk": 0.49, "hip_knee": 0.42, "knee_ankle": 0.42, "sh_ankle": 1.32}
WIN, TOL, FOOT_OFFSET = 10, 0.15, 3.5
SETS = {"1.25 m (home_4_1)": (R + r"\data\pursuit\home_4_1\frames", 10.0, 1.25),
        "1.77 m (home_6_1)": (R + r"\data\pursuit\home_6_1\frames", 8.0, 1.77),
        "1.80 m (box_1p8_1)": (R + r"\data\pursuit\box_1p8_1\frames", None, 1.80)}
NAMES = ["foot", "trunk", "hip_knee", "knee_ankle", "sh_ankle", "body_median", "fusion"]


def fwd(z, pt):
    return z * (cp - sp * ((pt[1] - K[1, 2]) / K[1, 1]))


def frame_estimates(bgr):
    r = pose(bgr, verbose=False, conf=0.3)[0]
    if r.keypoints is None or len(r.boxes) < 1:
        return None
    i = int(np.argmax(r.boxes.conf.cpu().numpy()))
    c = r.keypoints.conf[i].cpu().numpy()
    p = g.undistort_points(r.keypoints.xy[i].cpu().numpy())
    box = r.boxes.xyxy[i].cpu().numpy()
    est = {}
    # foot row (box bottom, offset)
    (uf, vf), = g.undistort_points([[(box[0] + box[2]) / 2, box[3] - FOOT_OFFSET]])
    gp = g.ground_point(float(uf), float(vf))
    if gp is not None:
        est["foot"] = gp.forward_m
    if min(c[5], c[6], c[11], c[12]) >= 0.8:
        sm, hm = (p[5] + p[6]) / 2, (p[11] + p[12]) / 2
        px = float(np.linalg.norm(sm - hm))
        if px > 8:
            est["trunk"] = fwd(K[0, 0] * PRIOR["trunk"] / px, (sm + hm) / 2)
    segs = []
    for hip, knee in ((11, 13), (12, 14)):
        if min(c[hip], c[knee]) >= 0.6:
            segs.append((float(np.linalg.norm(p[hip] - p[knee])), (p[hip] + p[knee]) / 2))
    if segs:
        est["hip_knee"] = fwd(K[0, 0] * PRIOR["hip_knee"] / np.mean([s[0] for s in segs]), segs[0][1])
    segs = []
    for knee, ank in ((13, 15), (14, 16)):
        if min(c[knee], c[ank]) >= 0.6:
            segs.append((float(np.linalg.norm(p[knee] - p[ank])), (p[knee] + p[ank]) / 2))
    if segs:
        est["knee_ankle"] = fwd(K[0, 0] * PRIOR["knee_ankle"] / np.mean([s[0] for s in segs]), segs[0][1])
    if min(c[5], c[6], c[15], c[16]) >= 0.6:
        sm, am = (p[5] + p[6]) / 2, (p[15] + p[16]) / 2
        px = float(np.linalg.norm(sm - am))
        if px > 8:
            est["sh_ankle"] = fwd(K[0, 0] * PRIOR["sh_ankle"] / px, (sm + am) / 2)
    body = [est[k] for k in ("trunk", "hip_knee", "knee_ankle", "sh_ankle") if k in est]
    if body:
        est["body_median"] = float(np.median(body))
        if "foot" in est:
            est["fusion"] = 0.5 * est["body_median"] + 0.5 * est["foot"]
    return est


res = {}
print("bias in metres (smoothed median of 10) / fraction of frames within +/- %.2f m; n = frames with the cue" % TOL)
print("%-20s" % "set" + "".join("%17s" % n for n in NAMES), flush=True)
for name, (folder, tmin, tape) in SETS.items():
    fs = sorted(glob.glob(folder + r"\*.jpg"))
    if tmin is not None:
        fs = [f for f in fs if float(f.split("\\")[-1][:-4]) >= tmin]
    series = {n: [] for n in NAMES}
    hist = {n: [] for n in NAMES}
    for f in fs:
        e = frame_estimates(cv2.imread(f))
        if not e:
            continue
        for n in NAMES:
            if n in e and math.isfinite(e[n]):
                hist[n] = (hist[n] + [e[n]])[-WIN:]
                if len(hist[n]) == WIN:
                    series[n].append(float(np.median(hist[n])))
    res[name] = {"tape": tape, "series": series}
    cells = []
    for n in NAMES:
        a = np.array(series[n])
        cells.append("%17s" % ("%+.2f / %3.0f%% n%d" % (np.median(a) - tape, 100 * np.mean(np.abs(a - tape) <= TOL), len(a)) if len(a) else "-"))
    print("%-20s" % name + "".join(cells), flush=True)
print("\nmean |bias| over the three sets, and sets within +/- 0.15 m of the tape (median):")
for n in NAMES:
    b = [abs(np.median(v["series"][n]) - v["tape"]) for v in res.values() if v["series"][n]]
    ok = sum(1 for v in res.values() if v["series"][n] and abs(np.median(v["series"][n]) - v["tape"]) <= TOL)
    print("  %-12s mean |bias| %.2f m   sets within +/-0.15: %d of %d" % (n, np.mean(b) if b else float("nan"), ok, len(b)))
json.dump(res, open(S + r"\anthro_fusion_result.json", "w"))
