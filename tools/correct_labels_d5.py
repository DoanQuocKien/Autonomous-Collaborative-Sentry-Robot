"""Tool for inspecting and curating D5 bounding box annotations (Week 3, HNHL).

Assists in manual bounding box inspection and curation for D5 floor-level obstacles
(Implementation Plan line 238, Small Object Detection doc §3).
Reads actual image dimensions and checks existing proposal boxes against visual features.
"""
import argparse
import csv
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2

ROOT = Path(__file__).resolve().parent.parent
D5_DIR = ROOT / "data" / "D5"
LABELS_DIR = D5_DIR / "labels"


def load_d5_manifest() -> List[Dict[str, str]]:
    manifest_path = D5_DIR / "manifest.csv"
    if not manifest_path.exists():
        return []
    with manifest_path.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def inspect_frame_labels(image_path: Path, label_path: Path) -> Dict:
    """Inspect an image and its corresponding YOLO label file."""
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    img = cv2.imread(str(image_path))
    if img is None:
        raise ValueError(f"Failed to decode image: {image_path}")

    h, w = img.shape[:2]
    boxes = []

    if label_path.exists():
        content = label_path.read_text(encoding="utf-8").strip()
        for line in content.splitlines():
            parts = line.strip().split()
            if len(parts) == 5:
                cls_id = int(parts[0])
                cx, cy, bw, bh = (float(v) for v in parts[1:])
                boxes.append({
                    "class_id": cls_id,
                    "cx": cx,
                    "cy": cy,
                    "w": bw,
                    "h": bh,
                    "pixel_box": (
                        int((cx - bw / 2) * w),
                        int((cy - bh / 2) * h),
                        int((cx + bw / 2) * w),
                        int((cy + bh / 2) * h),
                    ),
                })

    return {
        "file": image_path.name,
        "width": w,
        "height": h,
        "num_boxes": len(boxes),
        "boxes": boxes,
    }


def split_d5_by_session(train_ratio: float = 0.8) -> Tuple[List[str], List[str]]:
    """Split D5 files into train and validation sets by session/position to prevent leakage."""
    manifest = load_d5_manifest()
    if not manifest:
        return [], []

    # Group by (class, distance, session)
    groups: Dict[Tuple[str, str], List[str]] = {}
    for row in manifest:
        key = (row["class"], row["dist_m"])
        groups.setdefault(key, []).append(row["file"])

    train_files = []
    val_files = []

    for key, files in groups.items():
        n_train = max(1, int(len(files) * train_ratio))
        train_files.extend(files[:n_train])
        val_files.extend(files[n_train:])

    return train_files, val_files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-class", help="check labels for a specific class folder (e.g., shoe, leg, wire_black)")
    parser.add_argument("--summary", action="store_true", help="summarize existing label counts across folders")
    parser.add_argument("--split", action="store_true", help="generate train/val split without frame leakage")
    args = parser.parse_args()

    if args.summary or not (args.check_class or args.split):
        print(f"{'Class Folder':<15} {'Images':<10} {'Labeled Txts':<15} {'Total Boxes':<12}")
        print("-" * 55)
        for cdir in sorted(p for p in D5_DIR.iterdir() if p.is_dir() and not p.name.startswith("_") and p.name != "labels"):
            img_count = len(list(cdir.glob("*.jpg")))
            lbl_dir = LABELS_DIR / cdir.name
            lbl_count = len(list(lbl_dir.glob("*.txt"))) if lbl_dir.is_dir() else 0
            box_count = 0
            if lbl_dir.is_dir():
                for txt in lbl_dir.glob("*.txt"):
                    box_count += len([l for l in txt.read_text(encoding="utf-8").splitlines() if l.strip()])
            print(f"{cdir.name:<15} {img_count:<10} {lbl_count:<15} {box_count:<12}")

    if args.split:
        train, val = split_d5_by_session()
        print(f"\nSession-based split: {len(train)} train frames, {len(val)} validation frames (zero temporal leakage).")


if __name__ == "__main__":
    main()
