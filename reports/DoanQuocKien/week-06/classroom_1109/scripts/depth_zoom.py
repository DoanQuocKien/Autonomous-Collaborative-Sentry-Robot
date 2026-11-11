"""Experiment A, pass 2 (saved data only): calibrate the virtual zoom on the 1.8 m person sets, validate on the 1.25 m set (hold-out)."""
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
MODEL = sys.argv[1] if len(sys.argv) > 1 else "depth-anything/Depth-Anything-V2-Metric-Indoor-Small-hf"
g = CameraGeometry.from_files(R + r"\calib\camera.json", R + r"\calib\camera_pose_self_1109_4.json")
K = g.K
cp, sp = math.cos(g.pitch), math.sin(g.pitch)
proc = AutoImageProcessor.from_pretrained(MODEL)
model = AutoModelForDepthEstimation.from_pretrained(MODEL).to("cuda").eval()
det = YOLO(R + r"\data\models\yolov8s.pt")
ZOOMS = [1.0, 1.4, 1.6, 1.7, 1.8, 2.0]


def person_box(rect):
    r = det(rect, verbose=False, conf=0.1)[0]
    best = None
    for c, p, b in zip(r.boxes.cls, r.boxes.conf, r.boxes.xyxy):
        if det.names[int(c)] == "person" and (best is None or float(p) > best[0]):
            best = (float(p), [float(v) for v in b])
    return best[1] if best else None


def depth_at(rect, zoom):
    h0, w0 = rect.shape[:2]
    cw, ch = int(w0 / zoom), int(h0 / zoom)
    x0, y0 = int(K[0, 2] - cw / 2), int(K[1, 2] - ch / 2)
    src = cv2.resize(rect[max(0, y0):y0 + ch, max(0, x0):x0 + cw], (w0, h0), interpolation=cv2.INTER_LINEAR) if zoom != 1.0 else rect
    inp = proc(images=Image.fromarray(cv2.cvtColor(src, cv2.COLOR_BGR2RGB)), return_tensors="pt").to("cuda")
    with torch.no_grad():
        out = model(**inp).predicted_depth
    d = torch.nn.functional.interpolate(out.unsqueeze(1), size=(h0, w0), mode="bicubic", align_corners=False)[0, 0].cpu().numpy()
    return d, (x0, y0, cw, ch)


def person_forward(d, crop, box, zoom):
    x1, y1, x2, y2 = box
    h = y2 - y1
    ya, yb, xa, xb = int(y1 + 0.35 * h), int(y1 + 0.65 * h), int(x1 + 0.25 * (x2 - x1)), int(x2 - 0.25 * (x2 - x1))
    if zoom != 1.0:
        x0, y0, cw, ch = crop                           # box coordinates -> zoomed-crop coordinates
        sx, sy = d.shape[1] / cw, d.shape[0] / ch
        ya, yb, xa, xb = int((ya - y0) * sy), int((yb - y0) * sy), int((xa - x0) * sx), int((xb - x0) * sx)
        if ya < 0 or xa < 0 or yb > d.shape[0] or xb > d.shape[1] or yb <= ya or xb <= xa:
            return None
    z = float(np.median(d[ya:yb, xa:xb]))
    u, v = (x1 + x2) / 2.0, (y1 + 0.5 * h + y1) / 2.0 + 0.0
    x, y = (u - K[0, 2]) / K[0, 0], ((y1 + 0.5 * h) - K[1, 2]) / K[1, 1]
    return z * (cp - sp * y)


def frames(folder, tmin=None, n=12):
    fs = sorted(glob.glob(folder + r"\*.jpg"))
    if tmin is not None:
        fs = [f for f in fs if float(f.split("\\")[-1][:-4]) >= tmin]
    return fs[::max(1, len(fs) // n)][:n]


SETS = {"cal 1.8 m (box_1p8_1, tape 1.80)": (R + r"\data\pursuit\box_1p8_1\frames", None, 1.80),
        "cal 1.77 m (home_6_1 hold, tape 1.77)": (R + r"\data\pursuit\home_6_1\frames", 8.0, 1.77),
        "VAL 1.25 m (home_4_1 hold, tape 1.25)": (R + r"\data\pursuit\home_4_1\frames", 10.0, 1.25)}
res = {}
for name, (folder, tmin, tape) in SETS.items():
    per_zoom = {z: [] for z in ZOOMS}
    for f in frames(folder, tmin):
        rect = g.undistort(cv2.imread(f))
        box = person_box(rect)
        if box is None:
            continue
        for z in ZOOMS:
            d, crop = depth_at(rect, z)
            fw = person_forward(d, crop, box, z)
            if fw is not None:
                per_zoom[z].append(fw)
    res[name] = (tape, per_zoom)
    print(name, "n=%d" % len(per_zoom[1.0]), flush=True)
print("\nratio = depth-model forward / tape (median over frames):")
print("%-40s" % "set" + "".join("%8s" % ("x%g" % z) for z in ZOOMS))
for name, (tape, pz) in res.items():
    print("%-40s" % name + "".join("%8.2f" % (np.median(pz[z]) / tape) if pz[z] else "%8s" % "-" for z in ZOOMS))
cal = [np.median(res[k][1][z]) / res[k][0] for k in res if k.startswith("cal") for z in [0]] if False else None
best = min(ZOOMS, key=lambda z: abs(np.mean([np.median(res[k][1][z]) / res[k][0] for k in res if k.startswith("cal") and res[k][1][z]]) - 1.0))
print("\nzoom chosen on the 1.8 m sets only: x%g" % best)
for name, (tape, pz) in res.items():
    est = np.array(pz[best])
    print("%-40s forward median %.2f m (sd %.2f), tape %.2f, error %+.2f m (%+.0f %%)" % (name, np.median(est), est.std(), tape, np.median(est) - tape, 100 * (np.median(est) / tape - 1)))
json.dump({k: {"tape": v[0], "per_zoom": {str(z): list(map(float, vals)) for z, vals in v[1].items()}} for k, v in res.items()}, open(r"C:\Users\admin\AppData\Local\Temp\claude\7d42f4b8484190a4\68b819fd-108d-41fb-a937-45b34bdd1b82\scratchpad\depth_zoom_result.json", "w"))
