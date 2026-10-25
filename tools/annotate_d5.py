
"""Interactive D5 annotation without overwriting existing boxes."""

import argparse
from pathlib import Path
import cv2

ROOT = Path("data/D5")
FOLDER_CLASS = {
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", choices=FOLDER_CLASS, required=True)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--class-id", type=int, choices=range(8))
    args = parser.parse_args()

    cls = (
        args.class_id
        if args.class_id is not None
        else FOLDER_CLASS[args.folder]
    )

    names = (ROOT / "classes.txt").read_text().splitlines()
    images = sorted((ROOT / args.folder).glob("*.jpg"))
    selected = images[args.start:args.start + args.limit]

    for image_path in selected:
        image = cv2.imread(str(image_path))
        if image is None:
            print("Cannot read:", image_path)
            continue

        h, w = image.shape[:2]
        label_path = ROOT / "labels" / args.folder / (
            image_path.stem + ".txt"
        )
        label_path.parent.mkdir(parents=True, exist_ok=True)

        print(f"\nImage: {image_path.name}")
        print(f"Target: {names[cls]} (class {cls})")

        while True:
            preview = image.copy()

            # Show boxes already present in the annotation file.
            if label_path.exists():
                for line in label_path.read_text().splitlines():
                    parts = line.split()
                    if len(parts) != 5:
                        continue
                    try:
                        old_cls = int(parts[0])
                        xc, yc, bw, bh = map(float, parts[1:])
                    except ValueError:
                        continue

                    x1 = int((xc - bw / 2) * w)
                    y1 = int((yc - bh / 2) * h)
                    x2 = int((xc + bw / 2) * w)
                    y2 = int((yc + bh / 2) * h)

                    cv2.rectangle(
                        preview, (x1, y1), (x2, y2),
                        (0, 255, 0), 2
                    )
                    cv2.putText(
                        preview, str(old_cls),
                        (max(0, x1), max(15, y1)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5, (0, 255, 0), 1
                    )

            x, y, bw, bh = map(
                int,
                cv2.selectROI(
                    f"D5: {names[cls]} - {image_path.name}",
                    preview,
                    showCrosshair=True,
                    fromCenter=False,
                ),
            )
            cv2.destroyAllWindows()

            if bw <= 0 or bh <= 0:
                print("Skipped remaining boxes in this image.")
                break

            line = (
                f"{cls} "
                f"{(x + bw / 2) / w:.6f} "
                f"{(y + bh / 2) / h:.6f} "
                f"{bw / w:.6f} "
                f"{bh / h:.6f}"
            )

            answer = input(
                "Save box? [y] yes / [n] redraw / "
                "[s] next image / [q] quit: "
            ).strip().lower()

            if answer == "q":
                return
            if answer == "s":
                break
            if answer != "y":
                continue

            with label_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")

            print("Saved:", line)

            another = input(
                "Another box in this image? [y/N]: "
            ).strip().lower()
            if another != "y":
                break

    print("\nAnnotation batch finished.")


if __name__ == "__main__":
    main()
