"""Quick obstacle-detector check on live video: the robot stands still, a piece of furniture is at a TAPE distance in front of it, ~12 frames are run through the detector.

  python -m tools.furniture_check --label chair_1m --tape 1.0 --camera-pose calib/camera_pose_self_1030_2.json --floor glossy
Tape = distance from the camera (the robot's front) to the NEAREST point of the piece on the floor, along the heading. Prints what the detector found per frame (class, distance or the reason it has none)
and saves data/furniture/<label>/{frames/,result.json}. Recall = frames with a detection that has a distance; error = detector distance minus tape. Frames may show people: data/ stays local.
"""
import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--label", required=True)
    ap.add_argument("--tape", type=float, required=True, help="camera to the nearest point of the furniture on the floor (m)")
    ap.add_argument("--camera-pose", required=True)
    ap.add_argument("--floor", default="glossy", choices=("glossy", "matte"))
    ap.add_argument("--frames", type=int, default=12)
    ap.add_argument("--ip", default="auto")
    a = ap.parse_args()
    from sentry.net.discover import resolve
    from sentry.net.zmq_rx import ZMQReceiver
    from sentry.perception.obstacle import ObstacleDetector
    det = ObstacleDetector.from_config(camera_pose_path=a.camera_pose, floor_type=a.floor)
    out = Path("data/furniture") / a.label
    (out / "frames").mkdir(parents=True, exist_ok=True)
    rows, t_last = [], 0.0
    with ZMQReceiver(ip=resolve(a.ip)) as rx:
        while len(rows) < a.frames:
            f = rx.read(timeout=2)
            if f is None or time.time() - t_last < 0.3:
                continue
            t_last = time.time()
            cv2.imwrite(str(out / "frames" / ("%02d.jpg" % len(rows))), f.frame_bgr)
            res = det(f.frame_bgr, t_last, mode="explore", floor_type=a.floor)
            found = [dict(cls=o.detection.class_id, conf=round(o.detection.confidence, 2), xyxy=[round(v) for v in o.detection.xyxy],
                          distance_m=round(o.ground.distance_m, 2) if o.ground else None, forward_m=round(o.ground.forward_m, 2) if o.ground else None, rejection=o.rejection) for o in res.obstacles]
            rows.append(found)
            print("frame %2d: %s" % (len(rows), found if found else "nothing detected"), flush=True)
    dist = [o["distance_m"] for r in rows for o in r if o["distance_m"] is not None]
    summary = dict(label=a.label, tape_m=a.tape, camera_pose=a.camera_pose, floor=a.floor, frames=len(rows), frames_with_detection=sum(1 for r in rows if r),
                   frames_with_distance=sum(1 for r in rows if any(o["distance_m"] is not None for o in r)), median_distance_m=round(float(np.median(dist)), 2) if dist else None,
                   error_m=round(float(np.median(dist)) - a.tape, 2) if dist else None, rows=rows)
    (out / "result.json").write_text(json.dumps(summary, indent=1))
    print("%s: tape %.2f m | detected in %d/%d frames, with a distance in %d | median detector distance %s (error %s)" % (
        a.label, a.tape, summary["frames_with_detection"], len(rows), summary["frames_with_distance"], summary["median_distance_m"], summary["error_m"]))


if __name__ == "__main__":
    main()
