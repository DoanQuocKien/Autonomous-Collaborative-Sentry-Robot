"""Audit YOLOv8 Wire (class 4) predictions against local dev-val ground truth.

Runs read-only; creates a CSV report (outside the source label directories).
Usage:
  python tools/audit_d5_wire_predictions.py
"""

import argparse
import csv
from pathlib import Path
from statistics import median

WIRE_CLASS = 4


def load_yolo_labels(path: Path, *, is_prediction: bool):
    if not path.exists():
        return []
    records = []
    for line_number, line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
        columns = line.split()
        if not columns:
            continue
        if len(columns) < 5:
            raise ValueError(f'Bad YOLO line {path}:{line_number}: {line!r}')
        if int(float(columns[0])) != WIRE_CLASS:
            continue
        coords = tuple(map(float, columns[1:5]))
        score = float(columns[5]) if len(columns) >= 6 and is_prediction else 1.0
        x, y, w, h = coords
        records.append((x-w/2, y-h/2, x+w/2, y+h/2, score))
    return records


def box_iou(a, b):
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    intersection = max(0, ix1-ix0) * max(0, iy1-iy0)
    area_a = max(0, a[2]-a[0]) * max(0, a[3]-a[1])
    area_b = max(0, b[2]-b[0]) * max(0, b[3]-b[1])
    union = area_a + area_b - intersection
    return intersection / union if union > 0 else 0.0


def matched_count(gt, preds, *, conf, min_iou):
    # One-to-one greedy IoU matching. Suitable for object-level recall audit.
    remaining = [(j, p) for j, p in enumerate(preds) if p[4] >= conf]
    pairs = sorted(
        [(box_iou(g, p), i, j) for i, g in enumerate(gt) for j, p in remaining],
        reverse=True,
    )
    matched_gt, matched_preds = set(), set()
    for iou, gi, pj in pairs:
        if iou < min_iou:
            break
        if gi not in matched_gt and pj not in matched_preds:
            matched_gt.add(gi)
            matched_preds.add(pj)
    return len(matched_gt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gt-dir', type=Path, default=Path('data/D5_yolo_dev/labels/val'))
    parser.add_argument('--pred-dir', type=Path, default=Path('runs/detect/runs/d5_wire_audit/416_lowconf/labels'))
    parser.add_argument('--output', type=Path, default=Path('data/D5_wire_val_audit.csv'))
    args = parser.parse_args()
    if not args.gt_dir.is_dir():
        parser.error(f'GT directory not found: {args.gt_dir}')
    if not args.pred_dir.is_dir():
        parser.error(f'Prediction directory not found: {args.pred_dir}')
    paths = sorted(args.gt_dir.glob('wire_*.txt'))
    if not paths:
        parser.error(f'No wire_*.txt files in {args.gt_dir}')

    thresholds = [(0.05, .25), (0.05, .50), (0.25, .25), (0.25, .50)]
    totals = {t: 0 for t in thresholds}
    rows = []
    gt_total = 0
    n_pred = 0
    n_pred025 = 0
    found_wire = 0
    all_best_ious = []
    all_max_conf = []
    for path in paths:
        gt = load_yolo_labels(path, is_prediction=False)
        pred_path = args.pred_dir / path.name
        pred = load_yolo_labels(pred_path, is_prediction=True)
        gt_total += len(gt)
        n_pred += len(pred)
        n_pred025 += sum(1 for p in pred if p[4] >= .25)
        found_wire += bool(pred)
        max_conf = max((p[4] for p in pred), default=0)
        all_max_conf.append(max_conf)
        scored = [(box_iou(g, p), p[4]) for g in gt for p in pred]
        best_iou, conf_at_best_iou = max(scored, default=(0., 0.))
        all_best_ious.append(best_iou)
        row = {
            'image_stem': path.stem,
            'gt_wire_boxes': len(gt),
            'pred_wire_boxes_conf005': len(pred),
            'pred_wire_boxes_conf025': sum(p[4] >= .25 for p in pred),
            'max_wire_conf': round(max_conf, 5),
            'best_wire_iou_conf005': round(best_iou, 5),
            'conf_of_best_iou_box': round(conf_at_best_iou, 5),
            'pred_label_file_present': pred_path.exists(),
        }
        for t in thresholds:
            count = matched_count(gt, pred, conf=t[0], min_iou=t[1])
            totals[t] += count
            row[f'matched_conf{t[0]:.2f}_iou{t[1]:.2f}'] = count
        rows.append(row)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f'Images: {len(paths)} | GT wire boxes: {gt_total}')
    print(f'Images with >=1 wire prediction (conf>=0.05): {found_wire}/{len(paths)}')
    print(f'Wire predictions: {n_pred} at conf>=0.05; {n_pred025} at conf>=0.25')
    print('Matched ground-truth Wire boxes (1:1 matches):')
    for t in thresholds:
        count = totals[t]
        print(f'  conf>={t[0]:.2f}, IoU>={t[1]:.2f}: {count}/{gt_total} ({count/gt_total:.1%})' if gt_total else '  No GT wire')
    print(f'Median best IoU at conf>=0.05: {median(all_best_ious):.3f}')
    print(f'Median max wire confidence: {median(all_max_conf):.3f}')
    print('Lowest best-IoU images (inspect predicted boxes vs ground truth):')
    for row in sorted(rows, key=lambda r: r['best_wire_iou_conf005'])[:6]:
        print(f"  {row['image_stem']}: best IoU={row['best_wire_iou_conf005']:.3f}, max conf={row['max_wire_conf']:.3f}")
    print(f'CSV: {args.output.resolve()}')
    print('NOTE: Diagnostic subset and thresholds; NOT Ultralytics AP/recall evaluation.')


if __name__ == '__main__':
    main()
