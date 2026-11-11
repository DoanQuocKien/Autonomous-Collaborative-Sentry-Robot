import collections
import glob

import cv2
import numpy as np

from sentry.perception.camera import CameraGeometry
from tools.org_seg import OUT, build_model, components, predict

R = r"D:\CS532\Autonomous Collaborative Sentry Robot"
S = r"C:\Users\admin\AppData\Local\Temp\claude\7d42f4b8484190a4\68b819fd-108d-41fb-a937-45b34bdd1b82\scratchpad"
geom = CameraGeometry.from_files(R + r"\calib\camera.json", R + r"\calib\camera_pose_classroom_1015.json")
model = build_model(str(OUT / "segformer_org.pt")).cuda().eval()
files = sorted(glob.glob(R + r"\data\D1_obstacles_1015\empty_1\jetbot\*.jpg"))[::4]
dist, areas, rows = [], [], []
for k, f in enumerate(files):
    rect = geom.undistort(cv2.imread(f))
    big = cv2.resize(rect, None, fx=1.5, fy=1.5)
    p = cv2.resize(predict(model, big), (rect.shape[1], rect.shape[0]), interpolation=cv2.INTER_NEAREST)
    for x, y, w, h, a in components(p == 2, 60):
        gp = geom.ground_point(float(x + w / 2), float(y + h - 1))
        dist.append(gp.forward_m if gp else float("nan"))
        areas.append(a)
        rows.append((y + h - 1, x, w, h, a))
    if k == 3:
        ov = rect.copy()
        ov[p == 2] = (0, 0, 255)
        ov[p == 1] = (ov[p == 1] * 0.7 + np.array([0, 90, 0]) * 0.3).astype(np.uint8)
        cv2.imwrite(S + r"\fp_overlay.jpg", ov)
d = np.array(dist)
print("frames", len(files), "components", len(d))
print("forward distance of the false components: %s" % np.round(np.percentile(d[np.isfinite(d)], [0, 10, 25, 50, 75, 90, 100]), 2))
print("share beyond 2.5 m: %.0f %%, within 1.5 m: %.0f %%, within 2.0 m: %.0f %%" % (100 * np.mean(d > 2.5), 100 * np.mean(d <= 1.5), 100 * np.mean(d <= 2.0)))
print("component areas (px): median %d, 90th %d" % (np.median(areas), np.percentile(areas, 90)))
fr = collections.Counter(int(r[0] // 40) * 40 for r in rows)
print("contact row histogram:", sorted(fr.items()))
