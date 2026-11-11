"""Experiment A, round 6: range from body-part sizes with population priors (no per-person constant, no floor, no depth model)."""
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
# adult population means (m): biacromial (shoulder) width, shoulder-to-hip trunk length, ear-to-ear head width
PRIORS = {"shoulder": 0.38, "trunk": 0.50, "head": 0.155}
SETS = {"1.25 (home_4_1)": (R + r"\data\pursuit\home_4_1\frames", 10.0, 1.25),
        "1.77 (home_6_1)": (R + r"\data\pursuit\home_6_1\frames", 8.0, 1.77),
        "1.80 (box_1p8_1)": (R + r"\data\pursuit\box_1p8_1\frames", None, 1.80)}
extra = {}   # the 2.4 m frame no longer exists: no usable person frame at 2.4 m


def person_cues(bgr):
    r = pose(bgr, verbose=False, conf=0.3)[0]
    if r.keypoints is None or len(r.boxes) < 1:
        return None
    i = int(np.argmax(r.boxes.conf.cpu().numpy()))
    k = r.keypoints.xy[i].cpu().numpy()
    c = r.keypoints.conf[i].cpu().numpy()
    pts = g.undistort_points(k) if len(k) else k
    P = {n: pts[j] for n, j in (("ear_l", 3), ("ear_r", 4), ("sh_l", 5), ("sh_r", 6), ("hip_l", 11), ("hip_r", 12))}
    ok = {n: c[j] > 0.5 for n, j in (("ear_l", 3), ("ear_r", 4), ("sh_l", 5), ("sh_r", 6), ("hip_l", 11), ("hip_r", 12))}
    out = {}
    if ok["sh_l"] and ok["sh_r"]:
        out["shoulder"] = (float(np.linalg.norm(P["sh_l"] - P["sh_r"])), (P["sh_l"] + P["sh_r"]) / 2)
    if ok["sh_l"] and ok["sh_r"] and ok["hip_l"] and ok["hip_r"]:
        sm, hm = (P["sh_l"] + P["sh_r"]) / 2, (P["hip_l"] + P["hip_r"]) / 2
        out["trunk"] = (float(np.linalg.norm(sm - hm)), (sm + hm) / 2)
    if ok["ear_l"] and ok["ear_r"]:
        out["head"] = (float(np.linalg.norm(P["ear_l"] - P["ear_r"])), (P["ear_l"] + P["ear_r"]) / 2)
    return out


def forward(zcam, pt):
    y = (pt[1] - K[1, 2]) / K[1, 1]
    return zcam * (cp - sp * y)


def analyse(files):
    per = {n: [] for n in PRIORS}
    fused = []
    for f in files:
        cues = person_cues(cv2.imread(f))
        if not cues:
            continue
        fr = []
        for n, (px, pt) in cues.items():
            z = K[0, 0] * PRIORS[n] / px        # pinhole range from the rectified pixel size (frontal body assumed)
            per[n].append(forward(z, pt))
            fr.append(per[n][-1])
        if len(fr) >= 2:
            fused.append(float(np.median(fr)))
    return per, fused


res = {}
print("ratio = range from the cue / tape (median over frames); cues: shoulder 0.38 m, trunk 0.50 m, head 0.155 m (adult priors)")
print("%-24s %5s %9s %9s %9s %9s" % ("set", "n", "shoulder", "trunk", "head", "FUSED"))
for name, (folder, tmin, tape) in SETS.items():
    fs = sorted(glob.glob(folder + r"\*.jpg"))
    if tmin is not None:
        fs = [f for f in fs if float(f.split("\\")[-1][:-4]) >= tmin]
    fs = fs[::max(1, len(fs) // 20)][:20]
    per, fused = analyse(fs)
    res[name] = {"tape": tape, "per": per, "fused": fused}
    cell = lambda v: "%9.2f" % (np.median(v) / tape) if v else "%9s" % "-"
    print("%-24s %5d %s %s %s %s" % (name, len(fused), cell(per["shoulder"]), cell(per["trunk"]), cell(per["head"]), cell(fused)), flush=True)
for name, (files, tape) in extra.items():
    per, fused = analyse(files)
    res[name] = {"tape": tape, "per": per, "fused": fused}
    cell = lambda v: "%9.2f" % (np.median(v) / tape) if v else "%9s" % "-"
    print("%-24s %5d %s %s %s %s" % (name, len(fused), cell(per["shoulder"]), cell(per["trunk"]), cell(per["head"]), cell(fused)), flush=True)
json.dump(res, open(S + r"\anthro_range_result.json", "w"))
print()
for name, v in res.items():
    if v["fused"]:
        f = np.array(v["fused"])
        print("%-24s fused forward median %.2f m (sd %.2f) vs tape %.2f: error %+.2f m" % (name, np.median(f), f.std(), v["tape"], np.median(f) - v["tape"]))
