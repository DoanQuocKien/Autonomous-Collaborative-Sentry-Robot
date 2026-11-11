import glob

import cv2
import numpy as np

from sentry.perception.camera import CameraGeometry
from tools.org_seg import OUT, build_model, predict

R = r"D:\CS532\Autonomous Collaborative Sentry Robot"
S = r"C:\Users\admin\AppData\Local\Temp\claude\7d42f4b8484190a4\68b819fd-108d-41fb-a937-45b34bdd1b82\scratchpad"
geom = CameraGeometry.from_files(R + r"\calib\camera.json", R + r"\calib\camera_pose_self_1109_4.json")
model = build_model(str(OUT / "segformer_org.pt")).cuda().eval()
tiles = []
for tag in ("chair_1p2_1109", "chair_1p8_1109"):
    f = sorted(glob.glob(R + r"\data\furniture\%s\frames\*.jpg" % tag))[6]
    rect = geom.undistort(cv2.imread(f))
    p = cv2.resize(predict(model, cv2.resize(rect, None, fx=1.5, fy=1.5)), (640, 480), interpolation=cv2.INTER_NEAREST)
    ov = rect.copy()
    ov[p == 2] = (0, 0, 255)
    ov[p == 1] = (ov[p == 1] * 0.7 + np.array([0, 90, 0]) * 0.3).astype(np.uint8)
    ov[p == 0] = (ov[p == 0] * 0.8 + np.array([90, 0, 0]) * 0.2).astype(np.uint8)
    tiles.append(np.hstack([rect, ov]))
cv2.imwrite(S + r"\overlay1109.jpg", np.vstack(tiles))
