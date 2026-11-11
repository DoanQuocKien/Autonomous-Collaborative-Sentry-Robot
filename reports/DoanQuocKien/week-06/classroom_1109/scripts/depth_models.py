"""Experiment A, trial loop: several metric depth models, zero-shot, on the saved person sets with tape distances (no tuning)."""
import glob
import gc
import json
import math
import sys
import time

import cv2
import numpy as np
import torch
from PIL import Image
from transformers import AutoImageProcessor, AutoModelForDepthEstimation
from ultralytics import YOLO

from sentry.perception.camera import CameraGeometry

R = r"D:\CS532\Autonomous Collaborative Sentry Robot"
S = r"C:\Users\admin\AppData\Local\Temp\claude\7d42f4b8484190a4\68b819fd-108d-41fb-a937-45b34bdd1b82\scratchpad"
g = CameraGeometry.from_files(R + r"\calib\camera.json", R + r"\calib\camera_pose_self_1109_4.json")
K = g.K
cp, sp = math.cos(g.pitch), math.sin(g.pitch)
det = YOLO(R + r"\data\models\yolov8s.pt")
ZOOMS = [1.0, 1.4]
SETS = {"1.80 (box_1p8_1)": (R + r"\data\pursuit\box_1p8_1\frames", None, 1.80),
        "1.77 (home_6_1)": (R + r"\data\pursuit\home_6_1\frames", 8.0, 1.77),
        "1.25 (home_4_1)": (R + r"\data\pursuit\home_4_1\frames", 10.0, 1.25)}


def frames(folder, tmin, n=10):
    fs = sorted(glob.glob(folder + r"\*.jpg"))
    if tmin is not None:
        fs = [f for f in fs if float(f.split("\\")[-1][:-4]) >= tmin]
    return fs[::max(1, len(fs) // n)][:n]


def person_box(rect):
    r = det(rect, verbose=False, conf=0.1)[0]
    best = None
    for c, p, b in zip(r.boxes.cls, r.boxes.conf, r.boxes.xyxy):
        if det.names[int(c)] == "person" and (best is None or float(p) > best[0]):
            best = (float(p), [float(v) for v in b])
    return best[1] if best else None


# frames and boxes are prepared once
data = {}
for name, (folder, tmin, tape) in SETS.items():
    items = []
    for f in frames(folder, tmin):
        rect = g.undistort(cv2.imread(f))
        b = person_box(rect)
        if b:
            items.append((rect, b))
    data[name] = (tape, items)
    print(name, "frames with a person:", len(items), flush=True)


def run_model(mid):
    t0 = time.time()
    proc = AutoImageProcessor.from_pretrained(mid)
    model = AutoModelForDepthEstimation.from_pretrained(mid, torch_dtype=torch.float16).to("cuda").eval()
    print("== %s loaded in %.0f s" % (mid, time.time() - t0), flush=True)
    out = {}
    for name, (tape, items) in data.items():
        for z in ZOOMS:
            vals = []
            for rect, box in items:
                h0, w0 = rect.shape[:2]
                cw, ch = int(w0 / z), int(h0 / z)
                x0, y0 = int(K[0, 2] - cw / 2), int(K[1, 2] - ch / 2)
                src = cv2.resize(rect[max(0, y0):y0 + ch, max(0, x0):x0 + cw], (w0, h0)) if z != 1.0 else rect
                inp = proc(images=Image.fromarray(cv2.cvtColor(src, cv2.COLOR_BGR2RGB)), return_tensors="pt")
                inp = {k: (v.to("cuda").half() if v.dtype == torch.float32 else v.to("cuda")) for k, v in inp.items()}
                with torch.no_grad():
                    o = model(**inp)
                try:
                    d = proc.post_process_depth_estimation(o, target_sizes=[(h0, w0)])[0]["predicted_depth"].float().cpu().numpy()
                except Exception:
                    d = torch.nn.functional.interpolate(o.predicted_depth.float().unsqueeze(1), size=(h0, w0), mode="bicubic", align_corners=False)[0, 0].cpu().numpy()
                x1, y1, x2, y2 = box
                hh = y2 - y1
                ya, yb, xa, xb = int(y1 + 0.35 * hh), int(y1 + 0.65 * hh), int(x1 + 0.25 * (x2 - x1)), int(x2 - 0.25 * (x2 - x1))
                if z != 1.0:
                    sx, sy = w0 / cw, h0 / ch
                    ya, yb, xa, xb = int((ya - y0) * sy), int((yb - y0) * sy), int((xa - x0) * sx), int((xb - x0) * sx)
                    if ya < 0 or xa < 0 or yb > h0 or xb > w0 or yb <= ya or xb <= xa:
                        continue
                zc = float(np.median(d[ya:yb, xa:xb]))
                y = ((box[1] + 0.5 * hh) - K[1, 2]) / K[1, 1]
                vals.append(zc * (cp - sp * y))
            out[(name, z)] = vals
    del model
    gc.collect()
    torch.cuda.empty_cache()
    print("  ratio = model forward / tape (median):       " + "".join("%14s" % ("x%g" % z) for z in ZOOMS), flush=True)
    res = {}
    for name, (tape, _) in data.items():
        row = []
        for z in ZOOMS:
            v = out[(name, z)]
            row.append((np.median(v) / tape) if v else float("nan"))
        res[name] = row
        print("  %-18s tape %.2f " % (name, tape) + "".join("%14.2f" % r for r in row), flush=True)
    return {k[0] + "|x%g" % k[1]: v for k, v in out.items()}


models = sys.argv[1:] or ["depth-anything/Depth-Anything-V2-Metric-Indoor-Base-hf", "depth-anything/Depth-Anything-V2-Metric-Indoor-Large-hf", "apple/DepthPro-hf", "Intel/zoedepth-nyu"]
allres = {}
for m in models:
    try:
        allres[m] = run_model(m)
    except Exception as e:
        print("== %s FAILED: %s: %s" % (m, type(e).__name__, str(e)[:160]), flush=True)
json.dump(allres, open(S + r"\depth_models_result.json", "w"))
