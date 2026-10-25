
"""Manually annotate a table in one D5 image."""

import argparse
from pathlib import Path

import cv2


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    args = parser.parse_args()

    image_path = Path(args.image)
    table_dir = Path("data/D5/table").resolve()

    try:
        image_path.resolve().relative_to(table_dir)
    except ValueError:
        raise SystemExit("Only images in data/D5/table are supported")

    image = cv2.imread(str(image_path))
    if image is None:
        raise SystemExit(f"Cannot open image: {image_path}")

    height, width = image.shape[:2]

    x, y, box_w, box_h = map(
        int,
        cv2.selectROI(
            "D5 TABLE - Draw box, press ENTER",
            image,
            showCrosshair=True,
            fromCenter=False,
        ),
    )
    cv2.destroyAllWindows()

    if box_w <= 0 or box_h <= 0:
        print("Cancelled. No changes made.")
        return

    label = (
        f"6 {(x + box_w / 2) / width:.6f} "
        f"{(y + box_h / 2) / height:.6f} "
        f"{box_w / width:.6f} "
        f"{box_h / height:.6f}"
    )

    print("Proposed YOLO label:", label)

    if input("Save this box? [y/N]: ").strip().lower() != "y":
        print("Not saved.")
        return

    label_path = (
        Path("data/D5/labels/table")
        / f"{image_path.stem}.txt"
    )
    label_path.parent.mkdir(parents=True, exist_ok=True)

    existing = (
        label_path.read_text(encoding="utf-8").splitlines()
        if label_path.exists()
        else []
    )
    if label in existing:
        print("This exact box already exists. Not duplicated.")
        return

    with label_path.open("a", encoding="utf-8") as f:
        f.write(label + "\n")

    print("Saved:", label_path)


if __name__ == "__main__":
    main()
