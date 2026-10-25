"""Prepare a leak-aware *development-only* YOLO split from the D5 first batch.

Run from the repository root:
    python -m tools.prepare_d5_yolo_dev

This script NEVER modifies source images/annotations. It creates a separate
Ultralytics-friendly copy. A D5 holdout recorded in another session is still
required for a real T1 evaluation.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLASSES = ["leg", "footwear", "backpack", "bag", "wire", "chair", "table", "plant"]
EXPECTED_CLASS = {
    "leg": 0,
    "shoe": 1,
    "backpack": 2,
    "bag": 3,
    "wire_black": 4,
    "wire_white": 4,
    "chair": 5,
    "table": 6,
    "plant": 7,
}


def validate_label(path: Path) -> tuple[int, set[int]]:
    """Reject malformed labels, invalid classes/boxes and exact duplicates."""
    if not path.is_file():
        raise FileNotFoundError(f"Missing annotation: {path}")
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(lines) != len(set(lines)):
        raise ValueError(f"Duplicate annotations in: {path}")
    present = set()
    for number, line in enumerate(lines, 1):
        parts = line.split()
        if len(parts) != 5:
            raise ValueError(f"Invalid YOLO row {path}:{number}")
        try:
            class_id = int(parts[0])
            x, y, w, h = (float(z) for z in parts[1:])
        except ValueError as exc:
            raise ValueError(f"Invalid values {path}:{number}") from exc
        if not (0 <= class_id < len(CLASSES) and
                all(math.isfinite(v) for v in (x, y, w, h)) and
                w > 0 and h > 0 and
                x - w / 2 >= -0.000001 and x + w / 2 <= 1.000001 and
                y - h / 2 >= -0.000001 and y + h / 2 <= 1.000001):
            raise ValueError(f"Out-of-bounds YOLO box {path}:{number}")
        present.add(class_id)
    return len(lines), present


def choose_dev_split(rows: list[dict]) -> tuple[dict[str, str], dict[str, str]]:
    """Hold out one entire camera-distance group for each D5 folder.

    The 'empty' folder has only one distance group, so its last ~20% are a
    contiguous provisional dev block. All D5 frames share a capture session;
    this is not an independent benchmark and cannot establish T1 performance.
    """
    by_folder = defaultdict(list)
    for row in rows:
        by_folder[row["class"]].append(row)
    assignment, rationale = {}, {}
    for folder, group_rows in sorted(by_folder.items()):
        distances = defaultdict(list)
        for row in group_rows:
            distances[row["dist_m"]].append(row)
        if len(distances) > 1:
            goal = 0.2 * len(group_rows)
            # Prefer a whole distance block of ~20%; at equal distance
            # prefer the farther/harder target (higher metre distance).
            val_distance = min(distances, key=lambda k: (abs(len(distances[k]) - goal), -float(k)))
            val_files = {row["file"] for row in distances[val_distance]}
            rationale[folder] = f"hold out entire {val_distance}m distance block"
        else:
            by_time = sorted(group_rows, key=lambda r: (r.get("time", ""), r["file"]))
            num_val = max(1, round(len(by_time) * 0.2))
            val_files = {row["file"] for row in by_time[-num_val:]}
            rationale[folder] = f"hold out final {num_val} contiguous frames (same-session caveat)"
        for row in group_rows:
            assignment[row["file"]] = "val" if row["file"] in val_files else "train"
    return assignment, rationale


def prepare(source: Path, output: Path) -> dict:
    source, output = source.resolve(), output.resolve()
    if output == source or source in output.parents:
        raise ValueError("Output must not overwrite source annotations")
    if output.exists():
        raise FileExistsError(f"Output already exists (refusing to overwrite): {output}")
    names = (source / "classes.txt").read_text(encoding="utf-8").splitlines()
    if names != CLASSES:
        raise ValueError(f"Unexpected classes.txt; expected {CLASSES}, got {names}")
    with (source / "manifest.csv").open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("Empty manifest.csv")
    sessions = sorted({row["session"] for row in rows})
    if len(sessions) != 1:
        raise ValueError("Multiple sessions detected; select D5 training and independent T1 sessions explicitly")

    assignment, rationale = choose_dev_split(rows)
    counts = Counter()
    target_coverage = Counter()
    metadata_rows = []
    hashes = {"train": set(), "val": set()}
    copied_names = set()

    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="_d5_yolo_stage_", dir=output.parent))
    try:
        for row in rows:
            original = Path(row["file"])
            folder = row["class"]
            if (original.is_absolute() or ".." in original.parts or len(original.parts) != 2 or
                    original.parts[0] != folder or original.suffix.lower() != ".jpg"):
                raise ValueError(f"Invalid manifest path: {row['file']}")
            image = source / original
            label = source / "labels" / folder / (original.stem + ".txt")
            if not image.is_file():
                raise FileNotFoundError(f"Missing image: {image}")
            box_count, present = validate_label(label)
            if folder in EXPECTED_CLASS and EXPECTED_CLASS[folder] not in present:
                raise ValueError(f"Missing target class in {label}; finish review first")
            split = assignment[row["file"]]
            renamed = f"{folder}__{original.stem}"
            if renamed in copied_names:
                raise ValueError(f"Duplicate filename in manifest: {row['file']}")
            copied_names.add(renamed)
            image_hash = hashlib.sha256(image.read_bytes()).hexdigest()
            hashes[split].add(image_hash)
            new_img = staging / "images" / split / (renamed + ".jpg")
            new_lbl = staging / "labels" / split / (renamed + ".txt")
            new_img.parent.mkdir(parents=True, exist_ok=True)
            new_lbl.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(image, new_img)
            shutil.copy2(label, new_lbl)
            counts[split] += 1
            if folder in EXPECTED_CLASS:
                target_coverage[(split, folder)] += 1
            metadata_rows.append({
                "original": row["file"], "split": split,
                "new_image": f"images/{split}/{renamed}.jpg",
                "new_label": f"labels/{split}/{renamed}.txt",
                "session": row["session"], "distance_m": row["dist_m"],
                "boxes": box_count,
            })
        duplicates = hashes["train"] & hashes["val"]
        if duplicates:
            raise ValueError(f"Found {len(duplicates)} pixel-identical JPEG files crossing train/dev: split needs revision")
        if not counts["train"] or not counts["val"]:
            raise ValueError("Empty train or validation set")

        # Write a portable-ish data YAML whose root can include Windows spaces.
        data_yaml = ("# INTERNAL DEV ONLY. Same recording session; NOT independent D5 T1.\n"
                     f"path: {json.dumps(output.as_posix(), ensure_ascii=False)}\n"
                     "train: images/train\nval: images/val\n"
                     "names:\n" + "".join(f"  {i}: {name}\n" for i, name in enumerate(CLASSES)))
        (staging / "data.yaml").write_text(data_yaml, encoding="utf-8")
        with (staging / "split_manifest.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(metadata_rows[0]))
            writer.writeheader()
            writer.writerows(metadata_rows)
        summary = {
            "status": "DEVELOPMENT_ONLY_NOT_T1",
            "capture_sessions": sessions,
            "train_frames": counts["train"],
            "dev_val_frames": counts["val"],
            "exact_cross_split_duplicate_images": len(duplicates),
            "rule": "Hold out complete distance group per folder; empty folder uses last contiguous ~20%",
            "warning": "All frames came from one session and room. Validation may be optimistic; hold out a new D5 session for T1.",
            "per_folder_rule": rationale,
            "per_folder_frames": {
                folder: {sp: target_coverage[(sp, folder)] for sp in ("train", "val")}
                for folder in sorted(EXPECTED_CLASS)
            },
            "source": str(source), "output": str(output),
        }
        (staging / "split_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        staging.rename(output)
        return summary
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "data" / "D5")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "D5_yolo_dev")
    args = parser.parse_args()
    info = prepare(args.source, args.output)
    print(f"Created: {info['output']}")
    print(f"Train: {info['train_frames']}, internal dev-val: {info['dev_val_frames']}")
    print("Exact duplicate images across split:", info["exact_cross_split_duplicate_images"])
    print("\nFolder        train   dev-val")
    for folder, values in info["per_folder_frames"].items():
        print(f"{folder:<13} {values['train']:>5}     {values['val']:>5}")
    print("\nWARNING:", info["warning"])
    print("YAML:", Path(info["output"]) / "data.yaml")


if __name__ == "__main__":
    main()
