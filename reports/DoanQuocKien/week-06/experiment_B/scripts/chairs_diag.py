import glob

import cv2
import numpy as np

from sentry.perception.camera import CameraGeometry
from tools.org_seg import OUT, build_model, components, predict
from tools.org_seg_judge import load_objects

R = r"D:\CS532\Autonomous Collaborative Sentry Robot"
S = r"C:\Users\admin\AppData\Local\Temp\claude\7d42f4b8484190a4\68b819fd-108d-41fb-a937-45b34bdd1b82\scratchpad"
geom = CameraGeometry.from_files(R + r"\calib\camera.json", R + r"\calib\camera_pose_classroom_1015.json")
model = build_model(str(OUT / "segformer_org.pt")).cuda().eval()
sets = load_objects()
for name in ("chairs_a", "set2"):
    files = sorted(glob.glob(R + r"\data\D1_obstacles_1015\%s\jetbot\*.jpg" % name))
    f = files[len(files) // 2]
    rect = geom.undistort(cv2.imread(f))
    p = cv2.resize(predict(model, cv2.resize(rect, None, fx=1.5, fy=1.5)), (640, 480), interpolation=cv2.INTER_NEAREST)
    print("==", name, "tape objects (forward, lateral):", [(o["label"], o["tape"], o["lateral"]) for o in sets[name]])
    for x, y, w, h, a in components(p == 2, 60):
        gp = geom.ground_point(float(x + w / 2), float(y + h - 1))
        print("   component box (%d,%d,%d,%d) area %d -> contact forward/left: %s" % (x, y, w, h, a, "none" if gp is None else "%.2f / %+.2f" % (gp.forward_m, gp.left_m)))
    ov = rect.copy()
    ov[p == 2] = (0, 0, 255)
    ov[p == 1] = (ov[p == 1] * 0.7 + np.array([0, 90, 0]) * 0.3).astype(np.uint8)
    cv2.imwrite(S + r"\diag_%s.jpg" % name, np.hstack([rect, ov]))
