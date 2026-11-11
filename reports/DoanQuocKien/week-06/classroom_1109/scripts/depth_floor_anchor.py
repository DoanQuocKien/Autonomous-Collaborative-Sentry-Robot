"""Experiment A, trial T3: relative depth + floor-plane scale anchor (known lens height 0.100 m and the pitch), per frame, no per-person constant.
For each frame: relative inverse depth D(u,v) from Depth Anything V2; known floor depth Zfloor(u,v) from H and pitch; robust fit D = a / Zfloor + b over floor pixels (person excluded);
the person's body pixels give D_p, so Z_p = a / (D_p - b)."""
import glob
import json
import math
import sys

import cv2
import numpy as np
import torch
from PIL import Image
from transformers import AutoImageProcessor, AutoModelForDepthEstimation
from ultralytics import YOLO

from sentry.perception.camera import CameraGeometry

R = r"D:\CS532\Autonomous Collaborative Sentry Robot"
S = r"C:\Users\admin\AppData\Local\Temp\claude\7d42f4b8484190a4\68b819fd-108d-41fb-a937-45b34bdd1b82\scratchpad"
MODEL = sys.argv[1] if len(sys.argv) > 1 else "depth-anything/Depth-Anything-V2-Small-hf"
g = CameraGeometry.from_files(R + r"\calib\camera.json", R + r"\calib\camera_pose_self_1109_4.json")
K, H = g.K, g.height_m
cp, sp = math.cos(g.pitch), math.sin(g.pitch)
proc = AutoImageProcessor.from_pretrained(MODEL)
model = AutoModelForDepthEstimation.from_pretrained(MODEL).to("cuda").eval()
det = YOLO(R + r"\data\models\yolov8s.pt")
SETS = {"1.80 (box_1p8_1)": (R + r"\data\pursuit\box_1p8_1\frames", None, 1.80),
        "1.77 (home_6_1)": (R + r"\data\pursuit\home_6_1\frames", 8.0, 1.77),
        "1.25 (home_4_1)": (R + r"\data\pursuit\home_4_1\frames", 10.0, 1.25)}
h0, w0 = 480, 640
vv, uu = np.mgrid[0:h0, 0:w0]
right = (uu - K[0, 2]) / K[0, 0]
down = (vv - K[1, 2]) / K[1, 1]
vertical = sp + cp * down
Zfloor = np.where(vertical > 1e-3, H / np.maximum(vertical, 1e-3), np.inf)       # camera-frame z of the floor point on each pixel's ray
FLOOR_ZMIN, FLOOR_ZMAX = float(sys.argv[2]) if len(sys.argv) > 2 else 0.4, float(sys.argv[3]) if len(sys.argv) > 3 else 3.0


def person_box(rect):
    r = det(rect, verbose=False, conf=0.1)[0]
    best = None
    for c, p, b in zip(r.boxes.cls, r.boxes.conf, r.boxes.xyxy):
        if det.names[int(c)] == "person" and (best is None or float(p) > best[0]):
            best = (float(p), [float(v) for v in b])
    return best[1] if best else None


def rel_depth(rect):
    inp = proc(images=Image.fromarray(cv2.cvtColor(rect, cv2.COLOR_BGR2RGB)), return_tensors="pt").to("cuda")
    with torch.no_grad():
        o = model(**inp).predicted_depth
    return torch.nn.functional.interpolate(o.unsqueeze(1), size=(h0, w0), mode="bicubic", align_corners=False)[0, 0].cpu().numpy()


def robust_fit(x, y, iters=60, seed=0):
    rng = np.random.default_rng(seed)
    best, best_in = None, -1
    for _ in range(iters):
        i = rng.choice(len(x), 2, replace=False)
        if abs(x[i[0]] - x[i[1]]) < 1e-6:
            continue
        a = (y[i[0]] - y[i[1]]) / (x[i[0]] - x[i[1]])
        b = y[i[0]] - a * x[i[0]]
        res = np.abs(y - (a * x + b))
        thr = 0.08 * (np.percentile(y, 95) - np.percentile(y, 5) + 1e-6)
        n_in = int((res < thr).sum())
        if n_in > best_in and a > 0:
            best, best_in = (a, b, res < thr), n_in
    if best is None:
        return None
    a, b, inl = best
    A = np.vstack([x[inl], np.ones(inl.sum())]).T
    a, b = np.linalg.lstsq(A, y[inl], rcond=None)[0]
    return a, b, int(inl.sum()), len(x)


results = {}
for name, (folder, tmin, tape) in SETS.items():
    fs = sorted(glob.glob(folder + r"\*.jpg"))
    if tmin is not None:
        fs = [f for f in fs if float(f.split("\\")[-1][:-4]) >= tmin]
    fs = fs[::max(1, len(fs) // 12)][:12]
    est, inl_frac = [], []
    for f in fs:
        rect = g.undistort(cv2.imread(f))
        box = person_box(rect)
        if box is None:
            continue
        D = rel_depth(rect)
        x1, y1, x2, y2 = box
        m = np.isfinite(Zfloor) & (Zfloor > FLOOR_ZMIN) & (Zfloor < FLOOR_ZMAX)
        m[:, :int(max(0, x1 - 20))] |= False
        excl = np.zeros_like(m)
        excl[int(max(0, y1 - 10)):int(min(h0, y2 + 40)), int(max(0, x1 - 30)):int(min(w0, x2 + 30))] = True    # the person and the floor right around it (its reflection)
        m &= ~excl
        ys, xs = np.nonzero(m)
        if len(ys) < 500:
            continue
        sel = np.random.default_rng(1).choice(len(ys), min(4000, len(ys)), replace=False)
        fit = robust_fit(1.0 / Zfloor[ys[sel], xs[sel]], D[ys[sel], xs[sel]])
        if fit is None:
            continue
        a, b, n_in, n_all = fit
        hh = y2 - y1
        ya, yb, xa, xb = int(y1 + 0.35 * hh), int(y1 + 0.65 * hh), int(x1 + 0.25 * (x2 - x1)), int(x2 - 0.25 * (x2 - x1))
        dp = float(np.median(D[ya:yb, xa:xb]))
        if dp - b <= 1e-6:
            continue
        zp = a / (dp - b)
        y = ((y1 + 0.5 * hh) - K[1, 2]) / K[1, 1]
        est.append(zp * (cp - sp * y))
        inl_frac.append(n_in / n_all)
    est = np.array(est)
    results[name] = est.tolist()
    if len(est):
        print("%-18s n=%2d tape %.2f  floor-anchored forward median %.2f (sd %.2f)  ratio %.2f  error %+.2f m  (floor inliers %.0f %%)" % (name, len(est), tape, np.median(est), est.std(), np.median(est) / tape, np.median(est) - tape, 100 * np.mean(inl_frac)), flush=True)
    else:
        print(name, "no usable frames", flush=True)
json.dump(results, open(S + r"\depth_floor_anchor_%s.json" % MODEL.split("/")[-1], "w"))
