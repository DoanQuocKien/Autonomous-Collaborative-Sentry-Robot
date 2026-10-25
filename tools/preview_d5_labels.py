
from pathlib import Path
import cv2
import numpy as np

root = Path("data/D5")
out = Path("data/D5_review")
out.mkdir(parents=True, exist_ok=True)

classes = (root / "classes.txt").read_text().splitlines()

folders = [
    "backpack", "bag", "shoe", "leg",
    "wire_black", "wire_white", "table", "empty",
]

for folder in folders:
    images = sorted((root / folder).glob("*.jpg"))
    if not images:
        continue

    indices = sorted(set(
        i * (len(images) - 1) // 5 for i in range(6)
    ))

    tiles = []

    for idx in indices:
        path = images[idx]
        img = cv2.imread(str(path))
        if img is None:
            continue

        h, w = img.shape[:2]
        label_path = root / "labels" / folder / (path.stem + ".txt")

        if label_path.exists():
            for line in label_path.read_text().splitlines():
                parts = line.split()
                if len(parts) != 5:
                    continue

                cls = int(parts[0])
                xc, yc, bw, bh = map(float, parts[1:])

                x1 = round((xc - bw / 2) * w)
                y1 = round((yc - bh / 2) * h)
                x2 = round((xc + bw / 2) * w)
                y2 = round((yc + bh / 2) * h)

                cv2.rectangle(
                    img, (x1, y1), (x2, y2),
                    (0, 255, 0), 2
                )
                cv2.putText(
                    img, classes[cls], (max(x1, 0), max(y1 - 5, 15)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, (0, 255, 0), 1
                )

        img = cv2.resize(img, (480, 360))
        img = cv2.copyMakeBorder(
            img, 28, 0, 0, 0,
            cv2.BORDER_CONSTANT, value=(30, 30, 30)
        )

        cv2.putText(
            img, path.name, (8, 19),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42, (255, 255, 255), 1
        )
        tiles.append(img)

    if len(tiles) != 6:
        print("Skipped incomplete preview:", folder)
        continue

    sheet = np.vstack([
        np.hstack(tiles[:3]),
        np.hstack(tiles[3:]),
    ])

    target = out / f"{folder}.jpg"
    cv2.imwrite(str(target), sheet)
    print("Created:", target)

print("Preview generation finished.")
