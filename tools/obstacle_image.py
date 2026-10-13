"""Analyze one raw image with an explicit session pose/floor, without world pose.

Optional manual-regions JSON: [{"id":"...", "xyxy":[...], "flat_on_floor":false}].
Those are geometric diagnostics, not detector accuracy/recall evidence. Outputs
should stay under gitignored data/ for private D1 inputs. Never writes images.
"""
import argparse
import csv
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

import cv2

from sentry.config import DEFAULT_PATH
from sentry.perception.obstacle import Detection, ObstacleDetector
from tools.prescan_replay import FIELDS


def run(image_path, camera_pose_path, floor_type, out, config_path=DEFAULT_PATH,
        camera_path=None, manual_regions=None):
    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError("cannot read raw image")
    regions, predictor = None, None
    if manual_regions is not None:
        regions = json.loads(Path(manual_regions).read_text(encoding="utf-8-sig"))
        detections = tuple(Detection(-1, 1.0, tuple(r["xyxy"]), r.get("flat_on_floor", False)) for r in regions)
        predictor = lambda image: detections
    detector = ObstacleDetector.from_config(config_path, predictor, camera_pose_path, camera_path, floor_type)
    if regions is not None:
        detector.class_ids = detector.class_ids | {-1}  # explicitly manual geometry, never YOLO class filtering
    result = detector(image, 0.0)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "observations.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(FIELDS)
        for index, o in enumerate(result.obstacles):
            p, d, c = o.ground, o.detection, o.contact
            ground = [p.forward_m,p.left_m,p.distance_m,"",""] if p else [""]*5
            writer.writerow([0,0,0,index,d.class_id,d.confidence,*d.xyxy,o.rejection or "",*ground,
                             result.floor_type,result.camera_session,*([c.u,c.v,c.method,c.confidence] if c else [""]*4)])
    summary = dict(source="manual_regions_geometric_diagnostic" if regions is not None else "YOLO",
                   camera_session=result.camera_session, camera_pose_status=detector.geometry.pose_status,
                   image_sha256=hashlib.sha256(Path(image_path).read_bytes()).hexdigest(),
                   pose_sha256=hashlib.sha256(Path(camera_pose_path).read_bytes()).hexdigest(),
                   observations=asdict(result), motor_commands_sent=0)
    if regions is not None:
        summary["region_ids"] = [r["id"] for r in regions]
        summary["raw_bbox_forward_m"] = [
            p.forward_m if (p := detector.geometry.ground_point((r["xyxy"][0]+r["xyxy"][2])/2,r["xyxy"][3])) else None
            for r in regions]
    (out / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False), encoding="utf-8")
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--image", required=True)
    ap.add_argument("--camera-pose", required=True)
    ap.add_argument("--camera")
    ap.add_argument("--floor-type", choices=("glossy","matte"), required=True)
    ap.add_argument("--manual-regions")
    ap.add_argument("--config", default=str(DEFAULT_PATH))
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    result = run(a.image,a.camera_pose,a.floor_type,a.out,a.config,a.camera,a.manual_regions)
    print(json.dumps({k:result[k] for k in ("source","camera_session","camera_pose_status","motor_commands_sent")},indent=2))


if __name__ == "__main__":
    main()
