"""Read-only D5 Week-3 audit for the geometric wire fallback.

Compare floor-line candidates on ALL internal dev-validation frames:
 - positive images: at least one ground-truth Wire (YOLO class 4)
 - negative images: no ground-truth Wire

A 'GT-region hit' is NOT object detection recall. A grout line running
through a broad wire box can count as a hit. Visual review is necessary.
"""

import argparse
import csv
import math
from pathlib import Path

import cv2

from sentry.perception.wire_fallback import WireGeometricFallback

WIRE_CLASS = 4


def ground_truth_wire_boxes(label_path, width, height):
    if not label_path.exists():
        raise FileNotFoundError(f"Missing validation label: {label_path}")
    boxes = []
    for line_no, line in enumerate(label_path.read_text(encoding="utf-8").splitlines(), 1):
        fields = line.split()
        if not fields:
            continue
        if len(fields) != 5:
            raise ValueError(f"Malformed YOLO label {label_path}:{line_no}")
        klass = int(fields[0])
        if klass != WIRE_CLASS:
            continue
        cx, cy, bw, bh = [float(v) for v in fields[1:]]
        left = max(0, int(round((cx - bw / 2) * width)))
        top = max(0, int(round((cy - bh / 2) * height)))
        right = min(width, int(round((cx + bw / 2) * width)))
        bottom = min(height, int(round((cy + bh / 2) * height)))
        if right <= left or bottom <= top:
            raise ValueError(f"Invalid wire GT box {label_path}:{line_no}")
        boxes.append((left, top, right, bottom))
    return boxes


def segment_overlap_fraction(candidate, box):
    """Fraction of a detected LSD segment falling within a GT rectangle."""
    left, top, right, bottom = box
    p1 = tuple(int(round(v)) for v in candidate.pt1)
    p2 = tuple(int(round(v)) for v in candidate.pt2)
    total = math.dist(p1, p2)
    if total <= 0.0:
        return 0.0
    ok, q1, q2 = cv2.clipLine(
        (left, top, right - left, bottom - top), p1, p2
    )
    return min(1.0, math.dist(q1, q2) / total) if ok else 0.0


def make_review_grid(rows, output_file, caption, limit=6):
    if not rows:
        return
    tile_w, tile_h = 480, 360
    cols = 2
    chosen = rows[:limit]
    full_rows = math.ceil(len(chosen) / cols)
    import numpy as np
    canvas = np.full((full_rows * (tile_h + 30), cols * tile_w, 3), 24, dtype=np.uint8)
    for idx, rec in enumerate(chosen):
        src = rec["image"]
        img = cv2.imread(str(src))
        if img is None:
            continue
        h, w = img.shape[:2]
        gt = rec["boxes"]
        for x1, y1, x2, y2 in gt:
            cv2.rectangle(img, (x1, y1), (x2, y2), (255, 255, 0), 2)

        # Draw the strongest candidates for legibility, but keep some matched
        # candidates in the visual overview.
        selected = sorted(
            rec["candidates"],
            key=lambda c: (any(segment_overlap_fraction(c, b) >= 0.4 for b in gt),
                           c.length_px * c.contrast),
            reverse=True,
        )[:40]
        for c in selected:
            matched = any(segment_overlap_fraction(c, b) >= 0.4 for b in gt)
            color = (0, 210, 0) if matched else (0, 90, 255)  # BGR
            pt1 = tuple(int(round(v)) for v in c.pt1)
            pt2 = tuple(int(round(v)) for v in c.pt2)
            cv2.line(img, pt1, pt2, color, 2, cv2.LINE_AA)

        resized = cv2.resize(img, (tile_w, tile_h), interpolation=cv2.INTER_AREA)
        r, c = divmod(idx, cols)
        top, left = r * (tile_h + 30), c * tile_w
        canvas[top+30:top+30+tile_h, left:left+tile_w] = resized
        title = f"{src.stem[:31]} | segments={len(rec['candidates'])} | inside_GT={rec['matched']}"
        cv2.putText(canvas, title, (left+5, top+21),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.49, (235, 235, 235), 1, cv2.LINE_AA)
    cv2.imwrite(str(output_file), canvas)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("data/D5_yolo_dev"))
    parser.add_argument("--out", type=Path, default=Path("data/D5_fallback_audit"))
    parser.add_argument("--contrast", type=float, default=18.0)
    parser.add_argument("--min-length", type=float, default=35.0)
    parser.add_argument("--floor-fraction", type=float, default=0.5)
    args = parser.parse_args()
    image_dir = args.dataset / "images" / "val"
    label_dir = args.dataset / "labels" / "val"
    images = sorted(p for p in image_dir.iterdir()
                    if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    if not images:
        raise RuntimeError(f"No validation images in {image_dir}")

    detector = WireGeometricFallback(
        camera=None,
        min_length_px=args.min_length,
        contrast_threshold=args.contrast,
        floor_crop_fraction=args.floor_fraction,
    )
    args.out.mkdir(parents=True, exist_ok=True)
    positives = []
    negatives = []
    summaries = []
    for path in images:
        frame = cv2.imread(str(path))
        if frame is None:
            raise RuntimeError(f"Unreadable image: {path}")
        height, width = frame.shape[:2]
        gt = ground_truth_wire_boxes(label_dir / (path.stem + ".txt"), width, height)
        candidates = detector.detect(frame)
        matched = sum(
            any(segment_overlap_fraction(c, box) >= 0.4 for box in gt)
            for c in candidates
        )
        gt_boxes_with_segment = sum(
            any(segment_overlap_fraction(c, box) >= 0.4 for c in candidates)
            for box in gt
        )
        row = {
            "image": path.name,
            "has_gt_wire": int(bool(gt)),
            "gt_wire_boxes": len(gt),
            "candidates_total": len(candidates),
            "segments_in_gt_region": matched,
            "gt_boxes_with_segment": gt_boxes_with_segment,
            "flagged_image": int(bool(candidates)),
        }
        summaries.append(row)
        review_record = dict(image=path, boxes=gt, candidates=candidates,
                             matched=matched)
        (positives if gt else negatives).append(review_record)

    positive_hits = sum(int(r["matched"] > 0) for r in positives)
    negative_flags = sum(int(bool(r["candidates"])) for r in negatives)
    pos_total = len(positives)
    neg_total = len(negatives)
    print(f"Images: {len(images)} | GT-Wire positive images: {pos_total} | no-GT-Wire controls: {neg_total}")
    print(f"Params: min_length={args.min_length:g}px; contrast={args.contrast:g}; floor_fraction={args.floor_fraction:g}")
    print(f"Positive images with >=1 segment >=40% inside a GT-Wire box: {positive_hits}/{pos_total}")
    print(f"Negative images with >=1 floor-line candidate: {negative_flags}/{neg_total}")
    print(f"Segment count positive images: {sum(len(x['candidates']) for x in positives)} total")
    print(f"Segment count negative images: {sum(len(x['candidates']) for x in negatives)} total")
    print("CAVEAT: GT-region overlap is NOT wire recall; grout lines can intersect wire boxes.")
    print("CAVEAT: Any segment on a control is a candidate, NOT automatically a false alarm.")

    report = args.out / "per_image.csv"
    with report.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)

    # Distinguish the hardest GT positives from the most cluttered controls.
    positives.sort(key=lambda x: (x["matched"], len(x["candidates"]), x["image"].name))
    negatives.sort(key=lambda x: (-len(x["candidates"]), x["image"].name))
    make_review_grid(positives, args.out / "positives_review.jpg", "wire-positive")
    make_review_grid(negatives, args.out / "controls_review.jpg", "no-wire")
    print(f"CSV: {report}")
    print(f"Preview GT positives: {args.out / 'positives_review.jpg'}")
    print(f"Preview no-GT controls: {args.out / 'controls_review.jpg'}")
    print("Top 5 control images with the most segments:")
    for x in negatives[:5]:
        print(f"  {x['image'].name}: {len(x['candidates'])}")
    print("Top 5 wire-positive images with fewest GT-overlapping segments:")
    for x in positives[:5]:
        print(f"  {x['image'].name}: overlapping {x['matched']} of {len(x['candidates'])} total")


if __name__ == "__main__":
    main()
