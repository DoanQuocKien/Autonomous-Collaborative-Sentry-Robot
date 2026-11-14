"""Independent chair check on the saved 2026-11-09 frames (experiment B).

Run from the repository root (local frames and weights required):
  PYTHONPATH=. python reports/DoanQuocKien/week-06/experiment_B/scripts/chair_1109_check.py --out data/org_seg/chair_1109_rerun.json

Requires a new output file and non-empty, readable images at all three marks.
The committed results/chair_1109_check.json is historical evidence, never a default output.
"""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from sentry.perception.camera import CameraGeometry
from tools.org_seg import OUT, build_model, components, predict, require_new_outputs
from tools.org_seg_judge import free_space_segments

R = Path(__file__).resolve().parents[5]
SETS = (("chair_1p2_1109", 1.2), ("chair_1p8_1109", 1.8), ("chair_2p4_1109", 2.4))


def load_frames(frames_root):
    """Validate the entire input before loading a model or writing any output."""
    frames = {}
    for tag, _ in SETS:
        folder = Path(frames_root) / tag / "frames"
        files = sorted(folder.glob("*.jpg"))
        if not files:
            raise ValueError("no chair frames in %s; all three marks are required" % folder)
        frames[tag] = []
        for path in files:
            image = cv2.imread(str(path))
            if image is None:
                raise ValueError("unreadable chair frame: %s" % path)
            frames[tag].append(image)
    return frames


def evaluate(frames, geom, model):
    out = {"note": "tape from the robot front; the lens sits about 0.2-0.26 m behind it; obstacle = obstacle-class components (the chair skid), freespace = first non-ground row of each column; lane = |left| < 0.6 m, forward <= 3.5 m"}
    for tag, tape in SETS:
        ob, fs = [], []
        for frame in frames[tag]:
            rect = geom.undistort(frame)
            p = cv2.resize(predict(model, cv2.resize(rect, None, fx=1.5, fy=1.5)), (640, 480), interpolation=cv2.INTER_NEAREST)
            near = []
            for x, y, w, h, area in components(p == 2, 25):
                gp = geom.ground_point(float(x + w / 2), float(y + h - 1))
                if gp is not None and abs(gp.left_m) < 0.6 and gp.forward_m <= 3.5:
                    near.append(gp.forward_m)
            ob.append(min(near) if near else None)
            segs = [s for s in free_space_segments(p, geom, 3.5) if abs(s[1]) < 0.6]
            fs.append(min(s[0] for s in segs) if segs else None)
        for name, values in (("obstacle", ob), ("freespace", fs)):
            got = [x for x in values if x is not None]
            out.setdefault(name, {})[str(tape)] = dict(frames=len(frames[tag]), frames_with_a_lane_prediction=len(got),
                nearest_forward_m_median=round(float(np.median(got)), 3) if got else None,
                nearest_forward_m_min=round(min(got), 3) if got else None, nearest_forward_m_max=round(max(got), 3) if got else None)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True, help="new result JSON; existing files are refused")
    ap.add_argument("--frames-root", type=Path, default=R / "data/furniture")
    ap.add_argument("--camera-pose", type=Path, default=R / "reports/DoanQuocKien/week-06/classroom_1109/pose/camera_pose_self_1109_4.json")
    ap.add_argument("--weights", type=Path, default=OUT / "segformer_org.pt")
    a = ap.parse_args(argv)
    require_new_outputs(a.out)
    frames = load_frames(a.frames_root)
    geom = CameraGeometry.from_files(R / "calib/camera.json", a.camera_pose)
    model = build_model(str(a.weights)).cuda().eval()
    out = evaluate(frames, geom, model)
    out.update(frames_root=str(a.frames_root), camera_pose_file=str(a.camera_pose), weights=str(a.weights))
    payload = json.dumps(out, indent=1, allow_nan=False)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with a.out.open("x", encoding="utf-8") as fh:  # exclusive creation also protects a file created during inference
        fh.write(payload + "\n")
    print(payload)
    return out


if __name__ == "__main__":
    main()
