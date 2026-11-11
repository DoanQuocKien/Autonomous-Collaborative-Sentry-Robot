import glob

import cv2
import numpy as np

from sentry.perception.camera import CameraGeometry
from tools.org_seg import OUT, build_model, predict
from tools.org_seg import components
from tools.org_seg_judge import free_space_segments

R = r"D:\CS532\Autonomous Collaborative Sentry Robot"
geom = CameraGeometry.from_files(R + r"\calib\camera.json", R + r"\calib\camera_pose_self_1109_4.json")
model = build_model(str(OUT / "segformer_org.pt")).cuda().eval()
print("metal-frame chair, tape from the robot front (the lens sits about 0.2-0.26 m behind it; the front skid read 1.46 m from the lens at the 1.2 m mark)")
meds = {}
for tag, tape in (("chair_1p2_1109", 1.2), ("chair_1p8_1109", 1.8), ("chair_2p4_1109", 2.4)):
    fs = sorted(glob.glob(R + r"\data\furniture\%s\frames\*.jpg" % tag))
    near, found = [], 0
    for f in fs:
        rect = geom.undistort(cv2.imread(f))
        p = cv2.resize(predict(model, cv2.resize(rect, None, fx=1.5, fy=1.5)), (640, 480), interpolation=cv2.INTER_NEAREST)
        segs = []
        for x, y, w, h, a_ in components(p == 2, 25):                                  # the obstacle CLASS (the chair skid), in the lane in front of the robot
            gp = geom.ground_point(float(x + w / 2), float(y + h - 1))
            if gp is not None and abs(gp.left_m) < 0.6 and gp.forward_m <= 3.5:
                segs.append((gp.forward_m, gp.left_m))
        if segs:
            found += 1
            near.append(min(s[0] for s in segs))
    meds[tape] = float(np.median(near)) if near else None
    print("tape %.1f m: lane segment in %d of %d frames, nearest boundary forward median %s (range %s)" % (tape, found, len(fs), "-" if not near else "%.2f m" % np.median(near), "-" if not near else "%.2f-%.2f" % (min(near), max(near))))
if all(v is not None for v in meds.values()):
    print("spacing of the medians (true steps 0.6 m): %+.2f, %+.2f m" % (meds[1.8] - meds[1.2], meds[2.4] - meds[1.8]))
