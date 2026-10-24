"""First-pass labels for D5 with the open-vocabulary detector (YOLO-World): proposals to correct by hand, not ground truth.

  python -m tools.autolabel_d5                 # data/D5/<folder>/*.jpg -> data/D5/labels/<folder>/*.txt (YOLO format) + data/D5/autolabel.csv

Classes (data/D5/classes.txt): leg (legs and bare feet), footwear, backpack, bag, wire, chair, table, plant. Boxes below --conf are dropped from the txt
files (kept in the CSV with their confidence). The report per folder says in how many frames the folder's own class was found: that is the
auto-labeller's hit rate (each frame of a folder contains its class), not the detector's accuracy. Known weakness from the 2026-10-18 baseline: thin wires.
Correct every txt by hand (labelling rules in reports/DoanQuocKien/week-03/d5_first_batch/README.md): every visible object of the 8 classes gets a box.
"""
import argparse
import csv
from pathlib import Path

import cv2

CLASSES = ["leg", "footwear", "backpack", "bag", "wire", "chair", "table", "plant"]
PROMPTS = {"human leg": 0, "bare foot": 0, "shoe": 1, "slipper": 1, "backpack": 2, "bag": 3, "electrical cable": 4, "power cable": 4,
           "chair": 5, "table": 6, "potted plant": 7}
FOLDER_CLASS = {"leg": 0, "shoe": 1, "backpack": 2, "bag": 3, "wire_black": 4, "wire_white": 4, "chair": 5, "table": 6, "plant": 7}


def yolo_line(cls, xyxy, w, h):
    x1, y1, x2, y2 = xyxy
    return "%d %.6f %.6f %.6f %.6f" % (cls, (x1 + x2) / 2 / w, (y1 + y2) / 2 / h, (x2 - x1) / w, (y2 - y1) / h)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--conf", type=float, default=0.2, help="boxes below this are not written to the txt files")
    ap.add_argument("--floor-conf", type=float, default=0.05, help="detector threshold (everything above goes to the CSV)")
    ap.add_argument("--weights", default="data/models/yolov8s-worldv2.pt")
    ap.add_argument("--imgsz", type=int, default=640)
    a = ap.parse_args()
    from ultralytics import YOLOWorld
    model = YOLOWorld(a.weights)
    prompts = list(PROMPTS)
    model.set_classes(prompts)
    root = Path("data/D5")
    (root / "classes.txt").write_text("\n".join(CLASSES) + "\n")
    rows, hits, total = [], {}, {}
    for cdir in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("_") and p.name != "labels"):
        for f in sorted(cdir.glob("*.jpg")):
            img = cv2.imread(str(f))
            h, w = img.shape[:2]
            r = model.predict(img, imgsz=a.imgsz, conf=a.floor_conf, verbose=False)[0]
            lines, found = [], set()
            for b, c, k in zip(r.boxes.xyxy.tolist(), r.boxes.conf.tolist(), r.boxes.cls.tolist()):
                cls = PROMPTS[prompts[int(k)]]
                rows.append((cdir.name, f.name, CLASSES[cls], round(c, 3), *[round(v) for v in b]))
                if c >= a.conf:
                    lines.append(yolo_line(cls, b, w, h))
                    found.add(cls)
            out = root / "labels" / cdir.name / (f.stem + ".txt")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text("\n".join(lines) + ("\n" if lines else ""))
            total[cdir.name] = total.get(cdir.name, 0) + 1
            if FOLDER_CLASS.get(cdir.name) in found:
                hits[cdir.name] = hits.get(cdir.name, 0) + 1
    with (root / "autolabel.csv").open("w", newline="") as fh:
        csv.writer(fh).writerows([("folder", "file", "class", "conf", "x1", "y1", "x2", "y2")] + rows)
    for name in sorted(total):
        if name in FOLDER_CLASS:
            print("%-11s own class found in %3d of %3d frames (conf >= %.2f)" % (name, hits.get(name, 0), total[name], a.conf))
        else:
            print("%-11s %3d frames (negatives: boxes are false alarms to delete or real background objects to keep)" % (name, total[name]))


if __name__ == "__main__":
    main()
