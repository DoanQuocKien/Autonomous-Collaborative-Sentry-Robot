"""Read-only visualization of D5 wire ground truth versus YOLO predictions.

Expected input paths relative to repository root:
 data/D5_yolo_dev/images/val/wire_*.jpg
 data/D5_yolo_dev/labels/val/*.txt
 runs/detect/runs/d5_wire_audit/416_lowconf/labels/*.txt

Usage from repo root:
    python -m tools.visualize_d5_wire_iou
"""
from __future__ import annotations

import argparse
from pathlib import Path
import cv2

WIRE_CLASS = 4


def read_yolo_boxes(path: Path, w: int, h: int, is_pred: bool):
    boxes = []
    if not path.is_file():
        return boxes
    for lineno, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        a = line.split()
        if len(a) < (6 if is_pred else 5):
            raise ValueError(f"Invalid YOLO record: {path}:{lineno}")
        cls = int(float(a[0]))
        if cls != WIRE_CLASS:
            continue
        cx, cy, bw, bh = map(float, a[1:5])
        score = float(a[5]) if is_pred else 1.0
        x1 = max(0.0, (cx - bw / 2) * w)
        y1 = max(0.0, (cy - bh / 2) * h)
        x2 = min(float(w), (cx + bw / 2) * w)
        y2 = min(float(h), (cy + bh / 2) * h)
        boxes.append((x1, y1, x2, y2, score))
    return boxes


def iou(a, b):
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    ar1 = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    ar2 = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    return inter / (ar1 + ar2 - inter) if (ar1 + ar2 - inter) > 0 else 0.0


def box_draw(img, box, color, text):
    x1, y1, x2, y2 = map(lambda x: int(round(x)), box[:4])
    cv2.rectangle(img, (x1, y1), (x2, y2), color, 3)
    fs = max(0.55, min(img.shape[:2]) / 650)
    thick = 2
    size, _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, fs, thick)
    baseline_y = max(size[1] + 8, y1)
    cv2.rectangle(img, (x1, baseline_y - size[1] - 6),
                  (min(img.shape[1] - 1, x1 + size[0] + 6), baseline_y + 4), color, -1)
    cv2.putText(img, text, (x1 + 3, baseline_y - 3),
                cv2.FONT_HERSHEY_SIMPLEX, fs, (255, 255, 255), thick, cv2.LINE_AA)


def contact_sheet(rows, path: Path):
    if not rows:
        return
    tiles = []
    for best, name, image in rows:
        tile_w, tile_h = 640, 410
        ih, iw = image.shape[:2]
        scale = min(tile_w / iw, (tile_h - 40) / ih)
        nw, nh = int(iw * scale), int(ih * scale)
        scaled = cv2.resize(image, (nw, nh), interpolation=cv2.INTER_AREA)
        tile = cv2.copyMakeBorder(scaled, 0, tile_h - 40 - nh, 0, tile_w - nw,
                                  cv2.BORDER_CONSTANT, value=(25, 25, 25))
        tile = cv2.copyMakeBorder(tile, 40, 0, 0, 0, cv2.BORDER_CONSTANT, value=(25, 25, 25))
        title = f"{name} | best IoU={best:.3f}"
        cv2.putText(tile, title, (9, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.53,
                    (245, 245, 245), 1, cv2.LINE_AA)
        tiles.append(tile)
    if len(tiles) % 2:
        tiles.append(255 * (tiles[0] * 0).astype('uint8'))
    combined_rows = [cv2.hconcat(tiles[i:i+2]) for i in range(0, len(tiles), 2)]
    cv2.imwrite(str(path), cv2.vconcat(combined_rows))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--images', type=Path, default=Path('data/D5_yolo_dev/images/val'))
    parser.add_argument('--gt', type=Path, default=Path('data/D5_yolo_dev/labels/val'))
    parser.add_argument('--pred', type=Path, default=Path('runs/detect/runs/d5_wire_audit/416_lowconf/labels'))
    parser.add_argument('--out', type=Path, default=Path('data/D5_wire_iou_review'))
    parser.add_argument('--conf', type=float, default=0.05)
    args = parser.parse_args()
    images = sorted(args.images.glob('wire_*.jpg'))
    if not images:
        raise SystemExit(f'No wire images found in {args.images}')
    if not args.pred.is_dir():
        raise SystemExit(f'Prediction label directory does not exist: {args.pred}')
    args.out.mkdir(parents=True, exist_ok=True)
    ranked = []
    for path in images:
        img = cv2.imread(str(path))
        if img is None:
            raise ValueError(f'Cannot open: {path}')
        h, w = img.shape[:2]
        gt = read_yolo_boxes(args.gt / (path.stem + '.txt'), w, h, False)
        predfile = args.pred / (path.stem + '.txt')
        if not predfile.is_file():
            raise SystemExit(f'Missing prediction file: {predfile}')
        pred = [b for b in read_yolo_boxes(predfile, w, h, True) if b[4] >= args.conf]
        best = max((iou(a, b) for a in gt for b in pred), default=0.0)
        for b in gt:
            box_draw(img, b, (35, 180, 35), 'GT WIRE')
        for b in pred:
            box_draw(img, b, (30, 30, 245), f'PRED WIRE {b[4]:.2f}')
        cv2.imwrite(str(args.out / path.name), img)
        ranked.append((best, path.stem, img))
    ranked.sort(key=lambda x: x[0])
    contact_sheet(ranked[:6], args.out / 'preview_lowest_iou.jpg')
    contact_sheet(ranked[-6:][::-1], args.out / 'preview_highest_iou.jpg')
    print(f'Processed: {len(ranked)} images')
    print(f'Output: {args.out.resolve()}')
    print('Green = ground truth. Red = predicted wire box; number is confidence.')
    print('Preview the 6 lowest-IoU examples: preview_lowest_iou.jpg')
    print('Preview the 6 highest-IoU examples: preview_highest_iou.jpg')
    print('Lowest 6 IoUs:')
    for best, name, _ in ranked[:6]:
        print(f'  {name}: {best:.3f}')


if __name__ == '__main__':
    main()
