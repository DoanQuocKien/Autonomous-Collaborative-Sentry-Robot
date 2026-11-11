"""Experiment A validation, 2026-11-11 evening: three people (A = DQK, B = HNHL, C = KR) at 1.2 / 1.8 / 2.4 m on the glossy tile, 12 frames per set, pose calib/camera_pose_self_1111_3.json.
Per set: the foot-row range (YOLOv8s person box bottom -> floor point, no offset) and the trunk range (YOLOv8n-pose shoulder-to-hip length, prior 0.50 m), against the tape (measured from the robot FRONT:
the lens sits about 0.2-0.26 m behind it, unmeasured, so a constant about +0.2 m is expected in every row). Writes person_ranges_1111.json next to this script's results folder.
  PYTHONPATH=. python reports/DoanQuocKien/week-06/classroom_1111_pm/scripts/person_ranges.py      (needs data/furniture/person_*_1111/frames, data/models/yolov8s.pt, yolov8n-pose.pt)"""
import glob
import json
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

from sentry.perception.body_range import trunk_range
from sentry.perception.camera import CameraGeometry

R = Path(__file__).resolve().parents[5]
geom = CameraGeometry.from_files(R / "calib/camera.json", R / "calib/camera_pose_self_1111_3.json")
det, pose = YOLO(str(R / "data/models/yolov8s.pt")), YOLO(str(R / "yolov8n-pose.pt"))
dest = R / "reports/DoanQuocKien/week-06/classroom_1111_pm/data/person_ranges_1111.json"
if dest.exists():
    raise SystemExit("refusing to overwrite %s" % dest)
OFFS = (0.0, 3.5, 5.0)
out, sets = {"note": "tape from the robot front (lens about 0.2-0.26 m behind, unmeasured); frames local; foot = box bottom on the floor, trunk prior 0.50 m; bystander in frame for A_1p8 and B_1p2"}, {}
for d in sorted(glob.glob(str(R / "data/furniture/person_*_1111"))):
    tag = Path(d).name
    tape = json.load(open(Path(d) / "result.json"))["tape_m"]
    foot, trunk, n_det = {o: [] for o in OFFS}, [], 0
    for f in sorted(glob.glob(d + "/frames/*.jpg")):
        img = cv2.imread(f)
        boxes = [b.xyxy[0].tolist() for b in det(img, classes=[0], conf=0.25, verbose=False)[0].boxes]
        if not boxes:
            continue
        n_det += 1
        b = max(boxes, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))                          # the largest person (the one on the mark)
        for o in OFFS:                                                                      # the box bottom sits 3-7 px below the feet: shift the row up by o px
            gp = geom.ground_point(float((b[0] + b[2]) / 2), float(b[3]) - o)
            foot[o].append(None if gp is None else gp.forward_m)
        pr = pose(img, conf=0.25, verbose=False)[0]
        if pr.keypoints is not None and len(pr.boxes):
            i = int(np.argmax([(x[2] - x[0]) * (x[3] - x[1]) for x in pr.boxes.xyxy.cpu().numpy()]))
            t = trunk_range(pr.keypoints.xy[i].cpu().numpy(), pr.keypoints.conf[i].cpu().numpy(), geom.undistort_points, geom.K, geom.pitch)
            trunk.append(None if t is None else t[0])
        else:
            trunk.append(None)

    def stat(v):
        g = [x for x in v if x is not None]
        return dict(n=len(g), median=round(float(np.median(g)), 2) if g else None, min=round(min(g), 2) if g else None, max=round(max(g), 2) if g else None,
                    median_error_vs_tape=round(float(np.median(g)) - tape, 2) if g else None)
    sets[tag] = dict(tape_m=tape, frames=len(glob.glob(d + "/frames/*.jpg")), frames_with_person=n_det, foot_row={str(o): stat(foot[o]) for o in OFFS}, trunk=stat(trunk))
    print(tag, "tape", tape, "| foot(0/3.5/5 px)", [sets[tag]["foot_row"][str(o)]["median"] for o in OFFS], "| trunk", sets[tag]["trunk"]["median"], "| n", n_det)
out["sets"] = sets
dest.write_text(json.dumps(out, indent=1, allow_nan=False))
