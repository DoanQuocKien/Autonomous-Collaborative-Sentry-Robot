"""Independent check of experiment B on a different day: the metal-frame chair of 2026-11-09 (36 saved frames at the 1.2 / 1.8 / 2.4 m marks, tape from the robot front), pose calib/camera_pose_self_1109_4.json.
Writes results/chair_1109_check.json: for both outputs of the fine-tuned model, in how many frames a prediction lies in the lane in front of the robot (|left| < 0.6 m, forward <= 3.5 m) and where the nearest one is.
Run from the repository root:  PYTHONPATH=. python reports/DoanQuocKien/week-06/experiment_B/scripts/chair_1109_check.py   (needs the local frames in data/furniture/ and the weights data/org_seg/segformer_org.pt)."""
import glob
import json
from pathlib import Path

import cv2
import numpy as np

from sentry.perception.camera import CameraGeometry
from tools.org_seg import OUT, build_model, components, predict
from tools.org_seg_judge import free_space_segments

R = Path(__file__).resolve().parents[5]
geom = CameraGeometry.from_files(R / "calib/camera.json", R / "reports/DoanQuocKien/week-06/classroom_1109/pose/camera_pose_self_1109_4.json")
model = build_model(str(OUT / "segformer_org.pt")).cuda().eval()
out = {"note": "tape from the robot front; the lens sits about 0.2-0.26 m behind it; obstacle = obstacle-class components (the chair skid), freespace = first non-ground row of each column; lane = |left| < 0.6 m, forward <= 3.5 m"}
for tag, tape in (("chair_1p2_1109", 1.2), ("chair_1p8_1109", 1.8), ("chair_2p4_1109", 2.4)):
    files = sorted(glob.glob(str(R / "data/furniture" / tag / "frames/*.jpg")))
    ob, fs = [], []
    for f in files:
        rect = geom.undistort(cv2.imread(f))
        p = cv2.resize(predict(model, cv2.resize(rect, None, fx=1.5, fy=1.5)), (640, 480), interpolation=cv2.INTER_NEAREST)
        near = []
        for x, y, w, h, a in components(p == 2, 25):
            gp = geom.ground_point(float(x + w / 2), float(y + h - 1))
            if gp is not None and abs(gp.left_m) < 0.6 and gp.forward_m <= 3.5:
                near.append(gp.forward_m)
        ob.append(min(near) if near else None)
        segs = [s for s in free_space_segments(p, geom, 3.5) if abs(s[1]) < 0.6]
        fs.append(min(s[0] for s in segs) if segs else None)
    for name, v in (("obstacle", ob), ("freespace", fs)):
        got = [x for x in v if x is not None]
        out.setdefault(name, {})[str(tape)] = dict(frames=len(files), frames_with_a_lane_prediction=len(got), nearest_forward_m_median=round(float(np.median(got)), 3) if got else None,
                                                   nearest_forward_m_min=round(min(got), 3) if got else None, nearest_forward_m_max=round(max(got), 3) if got else None)
(R / "reports/DoanQuocKien/week-06/experiment_B/results/chair_1109_check.json").write_text(json.dumps(out, indent=1, allow_nan=False))
print(json.dumps(out, indent=1))
