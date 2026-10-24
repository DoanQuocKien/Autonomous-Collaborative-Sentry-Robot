"""Paint over the head of every person in the D5 frames (no faces in the dataset, Implementation Plan section 4.2).

  python -m tools.mask_faces                # data/D5/<class>/*.jpg, originals copied to data/D5_unmasked/ first (never overwritten)

A COCO person box (YOLOv8n) gives the body; the top HEAD_FRAC of it, widened a little, is filled with grey. Boxes that touch the top image border are
skipped (the head is out of frame: the leg close-ups). Every run starts again from the originals in data/D5_unmasked/, so it can be re-run after new recordings or a tuning change.
Check the result by eye: a person the detector misses keeps the face, and the tool prints the number of masked frames per class.
"""
import shutil
from pathlib import Path

import cv2

HEAD_FRAC = 0.42    # from the box top down: the YOLO box sits about 30 px above the head of a 140 px person, so the patch must reach well below it (legs start at about 0.5)
WIDEN = 0.15        # fraction of the box width added on each side of the head patch
MIN_TOP_PX = 6      # a box starting above this row is cut by the image border: no head to mask
MIN_H_PX = 30       # smaller boxes are shoes or bags, not people


def head_box(xyxy, w, h):
    x1, y1, x2, y2 = xyxy
    bw, bh = x2 - x1, y2 - y1
    if y1 < MIN_TOP_PX or bh < MIN_H_PX or bw > bh:      # cut by the border, too small, or lying / sitting (the box top is a leg, not a head)
        return None
    return (max(0, int(x1 - WIDEN * bw)), int(y1), min(w, int(x2 + WIDEN * bw)), int(y1 + HEAD_FRAC * bh))


def main():
    from ultralytics import YOLO
    model = YOLO("data/models/yolov8n.pt")
    root = Path("data/D5")
    backup = Path("data/D5_unmasked")
    for cdir in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("_")):
        masked = done = 0
        for f in sorted(cdir.glob("*.jpg")):
            copy = backup / cdir.name / f.name
            if not copy.exists():                           # first time: keep the original; later runs start again from it, so the tool can be tuned and re-run
                copy.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, copy)
            img = cv2.imread(str(copy))
            r = model.predict(img, classes=[0], conf=0.1, imgsz=640, verbose=False)[0]
            hit = False
            for b in r.boxes.xyxy.tolist():
                hb = head_box(b, img.shape[1], img.shape[0])
                if hb:
                    img[hb[1]:hb[3], hb[0]:hb[2]] = 128
                    hit = True
            cv2.imwrite(str(f), img, [cv2.IMWRITE_JPEG_QUALITY, 95])
            masked += hit
            done += 1
        print("%-11s %3d frames processed, %3d masked" % (cdir.name, done, masked))


if __name__ == "__main__":
    main()
