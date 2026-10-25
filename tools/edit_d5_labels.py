"""Visual review and correction of D5 YOLO labels.

Run from the repository root:
  python -m tools.edit_d5_labels --folder backpack --start 0 --limit 1
  python -m tools.edit_d5_labels --folder bag --start 0 --limit 1

No files are changed unless the user presses S. Original labels are backed up
once to data/D5_review/label_backups, outside the dataset folder.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent / "data" / "D5"
FOLDER_CLASS = {
    "leg": 0, "shoe": 1, "backpack": 2, "bag": 3,
    "wire_black": 4, "wire_white": 4, "chair": 5,
    "table": 6, "plant": 7, "empty": None,
}
HEADER = 80


def load_boxes(label_path: Path) -> list[list[float]]:
    """Read YOLO class, center x/y, width/height. Fail safely on bad labels."""
    if not label_path.exists():
        return []
    boxes = []
    for i, raw in enumerate(label_path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not raw.strip():
            continue
        parts = raw.split()
        try:
            if len(parts) != 5:
                raise ValueError("expected 5 fields")
            cls = int(parts[0])
            xc, yc, bw, bh = map(float, parts[1:])
            if not 0 <= cls < 8:
                raise ValueError("invalid class ID")
            if not all(np.isfinite([xc, yc, bw, bh])):
                raise ValueError("nonfinite coordinates")
            if not (bw > 0 and bh > 0 and
                    xc - bw / 2 >= -1e-5 and xc + bw / 2 <= 1 + 1e-5 and
                    yc - bh / 2 >= -1e-5 and yc + bh / 2 <= 1 + 1e-5):
                raise ValueError("invalid box")
        except ValueError as exc:
            raise ValueError(f"Invalid annotation {label_path}:{i}: {exc}") from exc
        boxes.append([cls, xc, yc, bw, bh])
    return boxes


def pixels(box: list[float], width: int, height: int) -> tuple[int, int, int, int]:
    _, xc, yc, bw, bh = box
    return (round((xc - bw / 2) * width), round((yc - bh / 2) * height),
            round((xc + bw / 2) * width), round((yc + bh / 2) * height))


def from_roi(cls: int, roi: tuple[int, int, int, int], width: int, height: int) -> list[float]:
    x, y, bw, bh = roi
    if not (0 <= x and 0 <= y and bw > 0 and bh > 0 and x + bw <= width and y + bh <= height):
        raise ValueError("Invalid ROI")
    return [cls, (x + bw / 2) / width, (y + bh / 2) / height, bw / width, bh / height]


def write_boxes(label_path: Path, boxes: list[list[float]], folder: str) -> Path:
    """Make a one-time backup and atomically overwrite a confirmed label file."""
    backup = ROOT.parent / "D5_review" / "label_backups" / folder / label_path.name
    backup.parent.mkdir(parents=True, exist_ok=True)
    if label_path.exists() and not backup.exists():
        shutil.copy2(label_path, backup)
    label_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = label_path.with_name(label_path.name + ".tmp")
    tmp.write_text("".join(f"{int(cls)} {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}\n"
                           for cls, xc, yc, bw, bh in boxes), encoding="utf-8")
    tmp.replace(label_path)
    return backup


def select_box(boxes: list[list[float]], mx: int, my: int, width: int, height: int) -> int | None:
    """Select the smallest box containing the clicked point."""
    hits = []
    for i, box in enumerate(boxes):
        x1, y1, x2, y2 = pixels(box, width, height)
        if x1 <= mx <= x2 and y1 <= my <= y2:
            hits.append(((x2 - x1) * (y2 - y1), i))
    return min(hits)[1] if hits else None


def edit_one(img_path: Path, label_path: Path, folder: str, default_cls: int | None,
             classes: list[str], index: int, total: int) -> bool:
    original = cv2.imread(str(img_path))
    if original is None:
        print("Cannot read image:", img_path)
        return True
    h, w = original.shape[:2]
    boxes = load_boxes(label_path)
    selected: list[int | None] = [None]
    dirty = False
    win = "D5 Label Editor"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win, w, h + HEADER)

    def mouse(event, x, y, flags, userdata):
        if event == cv2.EVENT_LBUTTONDOWN:
            selected[0] = select_box(boxes, x, y - HEADER, w, h)

    cv2.setMouseCallback(win, mouse)

    print(f"\n[{index}/{total}] {folder}/{img_path.name} | {len(boxes)} existing boxes")
    print("Click a box to select; 0-7 change class; A add; R redraw; D delete;")
    print("S save; N next; X discard current image; Q quit.")
    try:
        while True:
            canvas = np.zeros((h + HEADER, w, 3), dtype=np.uint8)
            canvas[HEADER:] = original
            info = [
                f"[{index}/{total}] {folder}/{img_path.name}",
                "Click box | 0-7 set class | A add | R redraw | D delete",
                f"S save | N next | X discard | Q quit | {'UNSAVED' if dirty else 'saved'}",
            ]
            for i, line in enumerate(info):
                cv2.putText(canvas, line, (8, 18 + i * 25),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.47, (255, 255, 255), 1, cv2.LINE_AA)
            for j, box in enumerate(boxes):
                x1, y1, x2, y2 = pixels(box, w, h)
                y1 += HEADER
                y2 += HEADER
                color = (0, 255, 255) if j == selected[0] else (0, 255, 0)
                cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 2)
                cls = int(box[0])
                cv2.putText(canvas, f"[{j}] {classes[cls]}", (max(0, x1), max(HEADER + 15, y1 - 5)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.50, color, 2, cv2.LINE_AA)
            cv2.imshow(win, canvas)
            key = cv2.waitKey(30) & 0xFF
            if key == 255:
                continue
            if ord('0') <= key <= ord('7'):
                if selected[0] is not None:
                    cls = key - ord('0')
                    if boxes[selected[0]][0] != cls:
                        boxes[selected[0]][0] = cls
                        dirty = True
                        print(f"Box {selected[0]} -> class {cls}: {classes[cls]}")
                else:
                    print("Click a box first to change its class.")
            elif key in (ord('d'), ord('D')):
                if selected[0] is not None:
                    boxes.pop(selected[0])
                    selected[0] = None
                    dirty = True
                    print("Selected box removed (not saved yet).")
            elif key in (ord('a'), ord('A'), ord('r'), ord('R')):
                redraw = key in (ord('r'), ord('R'))
                if redraw and selected[0] is None:
                    print("Click a box first to redraw it.")
                    continue
                if not redraw and default_cls is None:
                    print("This folder has no default class; select an existing box to change its class.")
                    continue
                roi_win = "Draw box - ENTER accept, C cancel"
                try:
                    roi = tuple(map(int, cv2.selectROI(roi_win, original, showCrosshair=True, fromCenter=False)))
                finally:
                    cv2.destroyWindow(roi_win)
                if roi[2] > 0 and roi[3] > 0:
                    cls = int(boxes[selected[0]][0]) if redraw else default_cls
                    new_box = from_roi(cls, roi, w, h)
                    if redraw:
                        boxes[selected[0]] = new_box
                    else:
                        boxes.append(new_box)
                        selected[0] = len(boxes) - 1
                    dirty = True
            elif key in (ord('s'), ord('S')):
                if dirty:
                    backup = write_boxes(label_path, boxes, folder)
                    dirty = False
                    print("Saved:", label_path)
                    if backup.exists():
                        print("Original backup:", backup)
                else:
                    print("No new edits to save.")
            elif key in (ord('n'), ord('N')):
                if dirty:
                    print("UNSAVED edits: press S to save, or X to discard.")
                else:
                    return True
            elif key in (ord('x'), ord('X')):
                print("Discarded unsaved edits to this image.")
                return True
            elif key in (ord('q'), ord('Q'), 27):
                if dirty:
                    print("UNSAVED edits: press S to save, or X to discard before quitting.")
                else:
                    return False
    finally:
        cv2.destroyWindow(win)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--folder", choices=FOLDER_CLASS, required=True)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--limit", type=int, default=1)
    args = ap.parse_args()
    if args.start < 0 or args.limit < 1:
        ap.error("--start must be >= 0 and --limit must be >= 1")
    classes_file = ROOT / "classes.txt"
    if not classes_file.exists():
        ap.error(f"Missing dataset file: {classes_file}. Run from the correct repository.")
    classes = classes_file.read_text(encoding="utf-8").splitlines()
    if len(classes) != 8:
        ap.error("Expected 8 class names in data/D5/classes.txt")
    imgs = sorted((ROOT / args.folder).glob("*.jpg"))
    selection = imgs[args.start: args.start + args.limit]
    if not selection:
        ap.error(f"No images in range for {args.folder}")
    for i, image in enumerate(selection, args.start + 1):
        label_path = ROOT / "labels" / args.folder / (image.stem + ".txt")
        keep_going = edit_one(image, label_path, args.folder, FOLDER_CLASS[args.folder],
                              classes, i, len(imgs))
        if not keep_going:
            break
    print("Finished reviewing selected images.")


if __name__ == "__main__":
    main()
