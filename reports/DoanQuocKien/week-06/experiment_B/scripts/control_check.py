"""Experiment B control sets (nothing, or a named object, at known marks): both outputs of the fine-tuned model on saved furniture_check frames.
For each label: in how many frames a prediction lies in the lane in front of the robot (|left| < 0.6 m, forward <= 3.5 m) and where the nearest one is.
  PYTHONPATH=. python reports/DoanQuocKien/week-06/experiment_B/scripts/control_check.py --pose calib/camera_pose_self_1111_2.json --out empty_floor_1111 empty_floor_1111_a [more labels]
Needs the local frames data/furniture/<label>/frames and the weights data/org_seg/segformer_org.pt. Writes results/<out>.json (refuses to overwrite)."""
import argparse
import glob
import json
from pathlib import Path

import cv2
import numpy as np

from sentry.perception.camera import CameraGeometry
from tools.org_seg import OUT, build_model, components, predict
from tools.org_seg_judge import free_space_segments

R = Path(__file__).resolve().parents[5]
ap = argparse.ArgumentParser()
ap.add_argument("labels", nargs="+")
ap.add_argument("--pose", required=True)
ap.add_argument("--out", required=True)
a = ap.parse_args()
dest = R / "reports/DoanQuocKien/week-06/experiment_B/results" / (a.out + ".json")
if dest.exists():
    raise SystemExit("refusing to overwrite %s" % dest)
geom = CameraGeometry.from_files(R / "calib/camera.json", R / a.pose)
model = build_model(str(OUT / "segformer_org.pt")).cuda().eval()
out = {"pose": a.pose, "note": "obstacle = obstacle-class components, freespace = first non-ground row of each column; lane = |left| < 0.6 m, forward <= 3.5 m; a prediction in an empty-floor set is a false stop"}
for tag in a.labels:
    files = sorted(glob.glob(str(R / "data/furniture" / tag / "frames/*.jpg")))
    if not files:
        raise SystemExit("no frames for %s" % tag)
    ob, fs = [], []
    for f in files:
        rect = geom.undistort(cv2.imread(f))
        p = cv2.resize(predict(model, cv2.resize(rect, None, fx=1.5, fy=1.5)), (640, 480), interpolation=cv2.INTER_NEAREST)
        near = []
        for x, y, w, h, ar in components(p == 2, 25):
            gp = geom.ground_point(float(x + w / 2), float(y + h - 1))
            if gp is not None and abs(gp.left_m) < 0.6 and gp.forward_m <= 3.5:
                near.append(gp.forward_m)
        ob.append(min(near) if near else None)
        segs = [s for s in free_space_segments(p, geom, 3.5) if abs(s[1]) < 0.6]
        fs.append(min(s[0] for s in segs) if segs else None)
    for name, v in (("obstacle", ob), ("freespace", fs)):
        got = [x for x in v if x is not None]
        out.setdefault(name, {})[tag] = dict(frames=len(files), frames_with_a_lane_prediction=len(got), nearest_forward_m_median=round(float(np.median(got)), 3) if got else None,
                                             nearest_forward_m_min=round(min(got), 3) if got else None, nearest_forward_m_max=round(max(got), 3) if got else None)
dest.write_text(json.dumps(out, indent=1, allow_nan=False))
print(json.dumps(out, indent=1))
