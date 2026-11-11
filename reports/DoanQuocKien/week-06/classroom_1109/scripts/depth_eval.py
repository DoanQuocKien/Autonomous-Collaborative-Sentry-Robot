"""Experiment A, pass 1: zero-shot metric depth (Depth Anything V2 Metric Indoor) on saved frames with tape distances.
Per object: YOLOv8s box (chair or person) -> median metric depth in a band just above the box bottom (the floor-contact region) -> forward distance on the floor via the camera pitch."""
import glob
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
MODEL = sys.argv[1] if len(sys.argv) > 1 else "depth-anything/Depth-Anything-V2-Metric-Indoor-Small-hf"
BODY = len(sys.argv) > 2 and sys.argv[2] == "body"
ZOOM = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
g = CameraGeometry.from_files(R + r"\calib\camera.json", R + r"\calib\camera_pose_self_1109_4.json")
K = g.K
cp, sp = math.cos(g.pitch), math.sin(g.pitch)
t0 = time.time()
proc = AutoImageProcessor.from_pretrained(MODEL)
model = AutoModelForDepthEstimation.from_pretrained(MODEL).to("cuda").eval()
print("loaded", MODEL, "in %.0f s" % (time.time() - t0), flush=True)
det = YOLO(R + r"\data\models\yolov8s.pt")


def depth_map(bgr):
    rect = g.undistort(bgr)
    src = rect
    if ZOOM != 1.0:                                   # virtual camera: crop around the principal point and enlarge (focal length x ZOOM)
        h0, w0 = rect.shape[:2]
        cw, ch = int(w0 / ZOOM), int(h0 / ZOOM)
        x0, y0 = int(K[0, 2] - cw / 2), int(K[1, 2] - ch / 2)
        src = cv2.resize(rect[max(0, y0):y0 + ch, max(0, x0):x0 + cw], (w0, h0), interpolation=cv2.INTER_LINEAR)
    img = Image.fromarray(cv2.cvtColor(src, cv2.COLOR_BGR2RGB))
    inp = proc(images=img, return_tensors="pt").to("cuda")
    with torch.no_grad():
        out = model(**inp).predicted_depth
    d = torch.nn.functional.interpolate(out.unsqueeze(1), size=rect.shape[:2], mode="bicubic", align_corners=False)[0, 0].cpu().numpy()
    if ZOOM != 1.0:                                   # paste the zoomed depth back into rectified-image coordinates (outside the crop: NaN)
        full = np.full(rect.shape[:2], np.nan, dtype=np.float32)
        small = cv2.resize(d, (cw, ch), interpolation=cv2.INTER_LINEAR)
        ya0, xa0 = max(0, y0), max(0, x0)
        full[ya0:ya0 + small.shape[0], xa0:xa0 + small.shape[1]] = small[:full.shape[0] - ya0, :full.shape[1] - xa0]
        d = full
    return rect, d


def best_box(rect, cls_name):
    r = det(rect, verbose=False, conf=0.05)[0]
    best = None
    for c, p, b in zip(r.boxes.cls, r.boxes.conf, r.boxes.xyxy):
        if det.names[int(c)] == cls_name and (best is None or float(p) > best[0]):
            best = (float(p), [float(v) for v in b])
    return best


def forward_from_depth(d, box):
    x1, y1, x2, y2 = box
    h = y2 - y1
    if BODY:
        ya, yb = int(y1 + 0.35 * h), int(y1 + 0.65 * h)                   # the object's body, away from the floor and its reflection
    else:
        ya, yb = int(max(0, y2 - 0.12 * h)), int(min(d.shape[0] - 1, y2 - 2))
    xa, xb = int(x1 + 0.25 * (x2 - x1)), int(x2 - 0.25 * (x2 - x1))
    z = float(np.nanmedian(d[ya:yb, xa:xb]))
    u, v = (xa + xb) / 2.0, (ya + yb) / 2.0
    x, y = (u - K[0, 2]) / K[0, 0], (v - K[1, 2]) / K[1, 1]
    return z * (cp - sp * y), z


SETS = [("chair 1.2 (front)", "chair", R + r"\data\furniture\chair_1p2_1109\frames", 1.2),
        ("chair 1.8 (front)", "chair", R + r"\data\furniture\chair_1p8_1109\frames", 1.8),
        ("chair 2.4 (front)", "chair", R + r"\data\furniture\chair_2p4_1109\frames", 2.4),
        ("person 1.8 (lens)", "person", R + r"\data\pursuit\box_1p8_1\frames", 1.8),
        ("person hold 1.77 (lens)", "person", R + r"\data\pursuit\home_6_1\frames", 1.77)]
out = {}
for name, cls, folder, tape in SETS:
    files = sorted(glob.glob(folder + r"\*.jpg"))
    files = files[len(files) // 2:][::max(1, len(files) // 24)][:12] if "person" in cls else files
    est = []
    for f in files:
        rect, d = depth_map(cv2.imread(f))
        b = best_box(rect, cls)
        if b is None or b[0] < 0.1:
            continue
        fw, z = forward_from_depth(d, b[1])
        est.append(fw)
    est = np.array(est)
    out[name] = est.tolist()
    if len(est):
        print("%-24s n=%2d  tape %.2f  depth-model forward median %.2f (sd %.2f, range %.2f-%.2f)  error %+.2f" % (name, len(est), tape, np.median(est), est.std(), est.min(), est.max(), np.median(est) - tape), flush=True)
    else:
        print("%-24s no detection" % name, flush=True)
chairs = [np.median(out[k]) for k in ("chair 1.2 (front)", "chair 1.8 (front)", "chair 2.4 (front)") if out.get(k)]
if len(chairs) == 3:
    print("chair steps (true 0.6, 0.6 m): %+.2f, %+.2f m ; front-to-lens offset implied by the 1.2 m chair: %.2f m" % (chairs[1] - chairs[0], chairs[2] - chairs[1], chairs[0] - 1.2))
json.dump(out, open(r"C:\Users\admin\AppData\Local\Temp\claude\7d42f4b8484190a4\68b819fd-108d-41fb-a937-45b34bdd1b82\scratchpad\depth_eval_%s_%s.json" % (MODEL.split("/")[-1], ("body" if BODY else "floor") + "_zoom%g" % ZOOM), "w"))
