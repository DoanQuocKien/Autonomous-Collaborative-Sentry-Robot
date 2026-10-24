"""Enrol the entrance of one room for sentry/perception/entrance.py and check it on recorded D1 data (T1).

  python -m tools.enroll_entrance --room class_door --robot-ref data/D1/class_door_iref_robot.jpg --select \
        --manifest data/D1/manifest_class_door.csv --out data/entrance/class_door
  python -m tools.enroll_entrance --room cafe --robot-ref ref.jpg --roi 178 0 410 250 --phone-ref phone.jpg --policy and --negatives-dir sweep_frames/ --out data/entrance/cafe

* --robot-ref: a frame from the robot's own camera with the door in view (2 m, straight on works; keep that position out of every evaluation).
* --select / --roi: the door box in the reference; WITHOUT it the bearing is the centroid of the matched points (biased by whatever else matched). With it: about +-6 deg at 1.5-3 m on D1.
* Negatives (the threshold calibration): --negatives-dir (jpgs of the room without the door, e.g. a slow sweep) or --manifest (D1: the first two negative positions).
* --manifest also evaluates the rest of the D1 positions: TPR on door-in-view frames, FPR on the others, per distance and angle, and the time per frame.
One door per room is assumed (plan section 7). The enrolment folder (reference images + thresholds) is what the robot loads at run time: EntranceDetector.load().
"""
import argparse
import csv
import math
import time
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

from sentry.perception.entrance import Camera, EntranceConfig, EntranceDetector


def split_manifest(rows, skip_position=2, n_calib_neg=2):
    """D1 manifest rows -> (calibration rows, test rows). The reference position is dropped; the first `n_calib_neg` negative positions calibrate the thresholds; the rest tests."""
    rows = [r for r in rows if int(r["position_id"]) != skip_position]
    neg_pos = sorted({int(r["position_id"]) for r in rows if r["door_visible"] == "no"})
    calib = set(neg_pos[:n_calib_neg])
    return [r for r in rows if int(r["position_id"]) in calib], [r for r in rows if int(r["position_id"]) not in calib]


def build_parser():
    ap = argparse.ArgumentParser()
    ap.add_argument("--room", required=True)
    ap.add_argument("--robot-ref", nargs="+", required=True)
    ap.add_argument("--phone-ref", nargs="*", default=[])
    ap.add_argument("--roi", nargs=4, type=int, metavar=("X0", "Y0", "X1", "Y1"))
    ap.add_argument("--select", action="store_true", help="draw the door box on the first reference")
    ap.add_argument("--policy", default="auto", choices=["auto", "xfeat", "dino", "and", "or"])
    ap.add_argument("--dino-size", default="b", choices=["s", "b"])
    ap.add_argument("--negatives-dir")
    ap.add_argument("--manifest")
    ap.add_argument("--step", type=int, default=5, help="use every Nth manifest frame")
    ap.add_argument("--calib-positions", type=int, default=2, help="manifest: how many negative positions calibrate the thresholds (the rest of the negatives test them)")
    ap.add_argument("--camera", default="calib/camera.json", help="fisheye camera JSON, or 'none' for ESP32-CAM enrolment")
    ap.add_argument("--out")
    return ap


def resolve_camera(camera_path):
    return None if not camera_path or camera_path.lower() == "none" else Camera.from_json(camera_path)


def main(argv=None):
    ap = build_parser()
    a = ap.parse_args(argv)
    refs = [cv2.imread(p) for p in a.robot_ref]
    roi = tuple(a.roi) if a.roi else None
    if a.select:
        x, y, w, h = cv2.selectROI("door box (Enter = ok)", refs[0], showCrosshair=False)
        cv2.destroyAllWindows()
        roi = (int(x), int(y), int(x + w), int(y + h))
    cam = resolve_camera(a.camera)
    det = EntranceDetector(cam, EntranceConfig(policy=a.policy, dino_size=a.dino_size))
    det.enroll_robot(refs, [roi] + [None] * (len(refs) - 1) if roi else None)
    if a.phone_ref:
        det.enroll_phone([cv2.imread(p) for p in a.phone_ref])
    test_rows, read = [], lambda r: cv2.imread("data/D1/jetbot/" + r["frame_file"])
    if a.manifest:
        calib_rows, test_rows = split_manifest(list(csv.DictReader(open(a.manifest, encoding="utf-8"))), n_calib_neg=a.calib_positions)
        negatives = [read(r) for r in calib_rows[::a.step] if r["door_visible"] == "no"]
    else:
        negatives = [cv2.imread(str(p)) for p in sorted(Path(a.negatives_dir).glob("*.jpg"))]
    if not negatives:
        raise SystemExit("no negatives: give --negatives-dir (frames without the door) or --manifest")
    print("room %s: %d robot refs, roi %s, %d negatives -> thresholds (xfeat inliers, dino cosine) = %s" % (a.room, len(refs), roi, len(negatives), det.calibrate(negatives)))
    if a.out:
        det.save(a.out)
        print("saved", a.out)
    if test_rows:
        groups, t0 = defaultdict(list), time.perf_counter()
        sub = test_rows[::a.step]
        for r in sub:
            groups[(r["door_visible"], r["distance_m"], r["angle_deg"])].append(det.detect(read(r)))
        ms = 1000 * (time.perf_counter() - t0) / len(sub)
        pos = [x.in_view for k, v in groups.items() if k[0] == "yes" for x in v]
        neg = [x.in_view for k, v in groups.items() if k[0] == "no" for x in v]
        print("TPR %.3f (n=%d)  FPR %.3f (n=%d)  %.0f ms/frame" % (np.mean(pos), len(pos), np.mean(neg), len(neg), ms))
        for k, v in sorted(groups.items()):
            if k[0] == "yes":
                b = [math.degrees(x.bearing_rad) for x in v if x.bearing_rad is not None]
                print("  %sm %4s deg: TPR %.2f%s" % (k[1], k[2], np.mean([x.in_view for x in v]), "  bearing median %+.1f deg" % np.median(b) if b else ""))


if __name__ == "__main__":
    main()
