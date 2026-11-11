"""Re-judge an obstacle model on SAVED classroom data with tape distances (experiment B): the D1 glossy-tile sets of 2026-10-15 (`data/D1_obstacles_1015`, 24 objects at tape distances 0.32-1.98 m and lateral
offsets from the spot under the lens, camera pose `calib/camera_pose_classroom_1015.json`) and `empty_1` (contains a real chair; not a verified empty-floor control).

  python -m tools.org_seg_judge --model seg --weights data/org_seg/segformer_org.pt --tag org_ft
  python -m tools.org_seg_judge --model configured --tag configured          # the configured YOLOv8n + glossy-floor logic of sentry.perception.obstacle, same ruler

Segmentation models: the frame is rectified, the predicted obstacle mask is split into connected components, and each component's floor contact (its lowest row, at the median column of its bottom rows)
is turned into a forward/left position on the floor with the camera pose. A tape object is FOUND in a frame when some component lies within the gates (|forward - tape| < 0.5 m, |left - lateral| < 0.4 m) of its tape
position; its distance error is forward - tape. Nonmatching components are unmatched predictions, not proven false positives without exhaustive labels. Nothing is tuned on these sets: the model never saw them.
The result JSON has per-object numbers and the exact settings; the frames stay local (data/).
"""
import argparse
import csv
import json
import math
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
D1 = ROOT / "data" / "D1_obstacles_1015"
GATE_FWD, GATE_LEFT = 0.5, 0.4


def load_objects():
    sets = {}
    for r in csv.DictReader(open(D1 / "obstacles_1015.csv", encoding="utf-8")):
        s = r["robot_pose_note"].split(":")[0].split(" ")[0]
        sets.setdefault(s, []).append(dict(id=int(r["obstacle_id"]), label=r["label"], tape=float(r["tape_distance_m"]), lateral=float(r["lateral_offset_m"])))
    return sets


def seg_components(model_pred, geom, frame, min_area):
    """-> [(forward_m, left_m)] of the obstacle components of one raw frame."""
    from tools.org_seg import components
    rect = geom.undistort(frame)
    pred = model_pred(rect)
    out = []
    for x, y, w, h, area in components(pred == 2, min_area):
        sub = np.nonzero((pred[y:y + h, x:x + w] == 2)[-3:].any(0))[0] if h >= 3 else np.arange(w)
        u = x + (float(np.median(sub)) if len(sub) else w / 2.0)
        v = y + h - 1
        gp = geom.ground_point(float(u), float(v))
        if gp is not None:
            out.append((gp.forward_m, gp.left_m))
    return out


def free_space_segments(pred, geom, max_range=2.5, min_cols=6):
    """Free-space boundary: from the bottom of each column go up while the model says GROUND; the first non-ground row is the contact of whatever stands there (a chair, a bag, a wall; a mirror image
    of it is ground and does not count). Runs of at least min_cols neighbouring columns whose boundary lies within max_range form one segment, represented by the point nearest to the robot.
    -> [(forward_m, left_m)]. Needs no obstacle class: this is the reflection-robust output of the ground mask."""
    h, w = pred.shape
    ground = pred == 1
    pts = []
    for u in range(0, w, 2):
        col = ground[:, u]
        if not col[h - 1]:
            pts.append(None)
            continue
        v = h - 1
        while v > 0 and col[v - 1]:
            v -= 1
        gp = geom.ground_point(float(u), float(v)) if v > 4 else None
        pts.append((gp.forward_m, gp.left_m) if gp is not None and gp.forward_m <= max_range else None)
    segs, run = [], []
    for p in pts + [None]:
        if p is not None:
            run.append(p)
        else:
            if len(run) >= min_cols:
                segs.append(min(run, key=lambda q: q[0]))
            run = []
    return segs


def configured_components(det, frame, floor):
    res = det(frame, time.time(), mode="explore", floor_type=floor)
    return [(o.ground.forward_m, o.ground.left_m) for o in res.obstacles if o.ground is not None]


def judge_set(frames, objects, comp_fn):
    per = {o["id"]: [] for o in objects}
    fp = []
    for f in frames:
        comps = comp_fn(f)
        used = set()
        for o in objects:
            best = None
            for i, (fw, lf) in enumerate(comps):
                if abs(fw - o["tape"]) < GATE_FWD and abs(lf - o["lateral"]) < GATE_LEFT and i not in used:
                    d = math.hypot(fw - o["tape"], lf - o["lateral"])
                    if best is None or d < best[0]:
                        best = (d, i, fw - o["tape"])
            if best is not None:
                used.add(best[1])
                per[o["id"]].append(best[2])
            else:
                per[o["id"]].append(None)
        fp.append(len(comps) - len(used))
    return per, fp


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", choices=("seg", "configured"), required=True)
    ap.add_argument("--output", choices=("obstacle", "freespace"), default="obstacle", help="seg: the obstacle class (small objects) or the free-space boundary of the ground mask (any object, reflection-robust)")
    ap.add_argument("--max-range", type=float, default=2.5, help="freespace: boundary points farther than this are not obstacles for the stop")
    ap.add_argument("--weights", default=None)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--min-area", type=int, default=60, help="smallest obstacle component, pixels at the model input (rectified 640x480)")
    ap.add_argument("--scale", type=float, default=1.5, help="seg: upscale the rectified frame before the model (ORG objects are larger in pixels than ours)")
    ap.add_argument("--every", type=int, default=2, help="use every n-th frame of each set")
    a = ap.parse_args()
    from tools.org_seg import require_new_outputs
    out = ROOT / "data" / "org_seg" / ("judge_%s.json" % a.tag)
    require_new_outputs(out)
    if a.every < 1 or a.min_area < 1 or not math.isfinite(a.scale) or a.scale <= 0:
        raise ValueError("every/min-area and finite scale must be positive")
    from sentry.perception.camera import CameraGeometry
    geom = CameraGeometry.from_files(ROOT / "calib" / "camera.json", ROOT / "calib" / "camera_pose_classroom_1015.json")
    sets = load_objects()
    if a.model == "seg":
        import torch
        from tools.org_seg import OUT, build_model, predict
        model = build_model(a.weights or str(OUT / "segformer_org.pt")).cuda().eval()

        def mp(rect):
            big = cv2.resize(rect, None, fx=a.scale, fy=a.scale, interpolation=cv2.INTER_LINEAR) if a.scale != 1.0 else rect
            p = predict(model, big)
            return cv2.resize(p, (rect.shape[1], rect.shape[0]), interpolation=cv2.INTER_NEAREST) if a.scale != 1.0 else p
        if a.output == "freespace":
            comp_fn = lambda f: free_space_segments(mp(geom.undistort(f)), geom, a.max_range)
        else:
            comp_fn = lambda f: seg_components(mp, geom, f, a.min_area)
    else:
        from sentry.perception.obstacle import ObstacleDetector
        det = ObstacleDetector.from_config(camera_pose_path=str(ROOT / "calib" / "camera_pose_classroom_1015.json"), floor_type="glossy")
        comp_fn = lambda f: configured_components(det, f, "glossy")
    results, rows = {}, []
    for name, objs in sets.items():
        files = sorted((D1 / name / "jetbot").glob("*.jpg"))[::a.every]
        frames = [cv2.imread(str(p)) for p in files]
        per, fp = judge_set(frames, objs, comp_fn)
        results[name] = dict(frames=len(frames), false_components_per_frame=round(float(np.mean(fp)), 3), objects={})
        for o in objs:
            v = per[o["id"]]
            found = [x for x in v if x is not None]
            results[name]["objects"][str(o["id"])] = dict(label=o["label"], tape_m=o["tape"], lateral_m=o["lateral"], found_fraction=round(len(found) / float(len(v)), 3),
                                                         median_error_m=round(float(np.median(found)), 3) if found else None)
            rows.append((name, o, len(found) / float(len(v)), float(np.median(found)) if found else None))
        print("%-9s frames %3d  false components per frame %.2f" % (name, len(frames), float(np.mean(fp))), flush=True)
    empty = sorted((D1 / "empty_1" / "jetbot").glob("*.jpg"))[::a.every]
    counts = [len(comp_fn(cv2.imread(str(p)))) for p in empty]
    results["empty_1"] = dict(frames=len(empty), frames_with_a_component=int(sum(1 for c in counts if c > 0)), components_per_frame=round(float(np.mean(counts)), 3))
    print("empty_1 (not an empty-floor control): frames %3d with a component: %d (%.1f %%)" % (len(empty), results["empty_1"]["frames_with_a_component"], 100.0 * results["empty_1"]["frames_with_a_component"] / max(1, len(empty))))
    f50 = [r for r in rows if r[2] >= 0.5]
    err = [abs(r[3]) for r in f50 if r[3] is not None]
    chairs = [r for r in rows if r[1]["label"] == "chair"]
    summary = dict(model=a.model, output=a.output, max_range=a.max_range, weights=a.weights, objects=len(rows), found_in_half_the_frames=len(f50), found_fraction_overall=round(float(np.mean([r[2] for r in rows])), 3),
                   median_abs_error_m_of_found=round(float(np.median(err)), 3) if err else None, within_0p15=sum(1 for e in err if e <= 0.15), within_0p30=sum(1 for e in err if e <= 0.30),
                   chairs=len(chairs), chairs_found_in_half_the_frames=sum(1 for r in chairs if r[2] >= 0.5), gates=dict(forward_m=GATE_FWD, left_m=GATE_LEFT), min_area=a.min_area, scale=a.scale, every=a.every,
                   date=time.strftime("%Y-%m-%d %H:%M"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(dict(summary=summary, sets=results), indent=1))
    print(json.dumps(summary, indent=1))
    print("saved", out)


if __name__ == "__main__":
    main()
