import csv, sys, time, json, statistics as st
from pathlib import Path
import cv2
from sentry.net.zmq_rx import ZMQReceiver
from sentry.perception.obstacle import ObstacleDetector
label, dist = sys.argv[1], float(sys.argv[2]); n = int(sys.argv[3]) if len(sys.argv) > 3 else 20
out = Path("data/D1_small_objects_1018"); (out / "frames").mkdir(parents=True, exist_ok=True)
det = ObstacleDetector.from_config(camera_pose_path="calib/camera_pose_rugged_1018.json", floor_type="matte")
rows = []
with ZMQReceiver() as rx:
    for i in range(n):
        f = rx.read(timeout=10); img = f.frame_bgr
        if i in (0, n // 2, n - 1):
            cv2.imwrite(str(out / "frames" / ("%s_%.1f_%d.jpg" % (label.replace(" ", "_"), dist, i))), img)
        r = det(img, time.time())
        rows.append([(o.detection.class_id, round(o.detection.confidence, 2), o.detection.source, o.rejection or "",
                      round(o.ground.distance_m, 3) if o.ground else None, tuple(round(x) for x in o.detection.xyxy)) for o in r.obstacles])
hit = sum(1 for r in rows if r); valid = [o[4] for r in rows for o in r if o[4] is not None]
print("%s @ %.2f m: %d/%d frames with a detection; %d with a distance" % (label, dist, hit, n, len(valid)))
cnt = {}
for r in rows:
    for o in r: cnt[(o[0], o[3])] = cnt.get((o[0], o[3]), 0) + 1
print("classes/rejections (class_id, reason): count ->", cnt)
if valid: print("distance median %.3f m (tape %.2f, error %+.1f %%)" % (st.median(valid), dist, 100 * (st.median(valid) - dist) / dist))
if rows and rows[0]: print("example:", rows[0][:3])
new = not (out / "obstacles.csv").exists()
with (out / "obstacles.csv").open("a", newline="") as fh:
    w = csv.writer(fh)
    if new: w.writerow(["label", "tape_distance_m", "frames", "frames_with_detection", "frames_with_distance", "median_distance_m", "classes_reasons"])
    w.writerow([label, dist, n, hit, len(valid), round(st.median(valid), 3) if valid else "", json.dumps({str(k): v for k, v in cnt.items()})])
