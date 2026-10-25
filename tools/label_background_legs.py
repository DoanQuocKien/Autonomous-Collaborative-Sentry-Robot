"""Add `leg` boxes for the person standing in the background of D5 frames (labelling rule of 2026-10-24: every visible leg is labelled).

  python -m tools.label_background_legs --originals data/D5_unmasked

A COCO person box (YOLOv8s, run on the unmasked originals: the committed frames have the head painted over) of a STANDING person (height >= 1.8 x width)
gives the legs as its lower part (from LEG_FROM of the box height down to the feet). Sitting people (legs hidden behind a chair or a desk), boxes cut by the
image border (the close-up legs of the `leg` folder, already labelled by hand) and legs that already have a box are skipped. Appends to data/D5/labels/<folder>/<frame>.txt.
These are proposals made by a detector: look at the result (tools/preview_d5_labels.py) before training on it.
"""
import argparse
from pathlib import Path

import cv2

LEG_CLASS = 0
LEG_FROM = 0.55      # the shorts end at about half of the person box; legs and feet are the rest
MIN_ASPECT = 1.8     # standing person: box height / width
MIN_H_PX = 40
BORDER_PX = 6


def leg_box(xyxy, w, h):
    x1, y1, x2, y2 = xyxy
    bw, bh = x2 - x1, y2 - y1
    if bh < MIN_H_PX or bh < MIN_ASPECT * bw or y1 < BORDER_PX or y2 > h - BORDER_PX:
        return None
    return (x1, y1 + LEG_FROM * bh, x2, y2)


def iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def yolo_to_xyxy(cx, cy, bw, bh, w, h):
    return ((cx - bw / 2) * w, (cy - bh / 2) * h, (cx + bw / 2) * w, (cy + bh / 2) * h)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--originals", default="data/D5_unmasked")
    ap.add_argument("--labels", default="data/D5/labels")
    ap.add_argument("--weights", default="data/models/yolov8s.pt")
    ap.add_argument("--conf", type=float, default=0.3)
    a = ap.parse_args()
    from ultralytics import YOLO
    model = YOLO(a.weights)
    added = frames = 0
    for txt in sorted(Path(a.labels).glob("*/*.txt")):
        folder = txt.parent.name
        if folder == "leg":
            continue
        img_path = Path(a.originals) / folder / (txt.stem + ".jpg")
        if not img_path.exists():
            continue
        img = cv2.imread(str(img_path))
        h, w = img.shape[:2]
        lines = [l for l in txt.read_text().splitlines() if l.strip()]
        legs = [yolo_to_xyxy(*map(float, l.split()[1:5]), w, h) for l in lines if l.split()[0] == str(LEG_CLASS)]
        new = []
        for b in model.predict(img, classes=[0], conf=a.conf, imgsz=640, verbose=False)[0].boxes.xyxy.tolist():
            lb = leg_box(b, w, h)
            if lb and not any(iou(lb, g) > 0.5 for g in legs):
                new.append("%d %.6f %.6f %.6f %.6f" % (LEG_CLASS, (lb[0] + lb[2]) / 2 / w, (lb[1] + lb[3]) / 2 / h, (lb[2] - lb[0]) / w, (lb[3] - lb[1]) / h))
        if new:
            txt.write_text("\n".join(lines + new) + "\n")
            added += len(new)
            frames += 1
    print("added %d leg boxes in %d frames" % (added, frames))


if __name__ == "__main__":
    main()
