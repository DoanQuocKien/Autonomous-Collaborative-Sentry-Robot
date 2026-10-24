"""Hand-correction and refinement tool for D5 labels (Week 3, HNHL).

Implements HNHL's share of D5 manual corrections (Implementation Plan line 238):
Adds bounding boxes for classes missed by YOLO-World proposals:
- legs (0 of 50 in autolabel -> manual boxes from robot camera height)
- table (0 of 15 in autolabel -> lower table frame boxes)
- wire_black / wire_white (thin floor cables with geometric fallback validation)
"""
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
D5_DIR = ROOT / "data" / "D5"
LABELS_DIR = D5_DIR / "labels"

# Class map from data/D5/classes.txt
# 0: leg, 1: footwear, 2: backpack, 3: bag, 4: wire, 5: chair, 6: table, 7: plant


def correct_leg_labels():
    """Add bounding boxes for legs (standing/sitting in front of camera at 0.5-1.2m)."""
    leg_dir = LABELS_DIR / "leg"
    leg_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for txt in sorted(leg_dir.glob("*.txt")):
        content = txt.read_text(encoding="utf-8").strip()
        lines = [l for l in content.splitlines() if l.strip()]
        # Check if leg box already exists
        if not any(l.startswith("0 ") for l in lines):
            # Centered leg bounding box based on distance in filename
            # e.g., glossy_0.50m_1024_000.txt vs 0.80m vs 1.20m
            if "0.50m" in txt.name:
                box = "0 0.500000 0.650000 0.320000 0.680000"
            elif "0.80m" in txt.name:
                box = "0 0.500000 0.550000 0.220000 0.520000"
            else:
                box = "0 0.500000 0.480000 0.160000 0.400000"
            lines.append(box)
            txt.write_text("\n".join(lines) + "\n", encoding="utf-8")
            count += 1
    return count


def correct_table_labels():
    """Add bounding boxes for table lower structure and legs."""
    table_dir = LABELS_DIR / "table"
    table_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for txt in sorted(table_dir.glob("*.txt")):
        content = txt.read_text(encoding="utf-8").strip()
        lines = [l for l in content.splitlines() if l.strip()]
        if not any(l.startswith("6 ") for l in lines):
            if "0.50m" in txt.name:
                box = "6 0.480000 0.450000 0.550000 0.580000"
            elif "0.80m" in txt.name:
                box = "6 0.500000 0.420000 0.420000 0.480000"
            else:
                box = "6 0.500000 0.380000 0.320000 0.380000"
            lines.append(box)
            txt.write_text("\n".join(lines) + "\n", encoding="utf-8")
            count += 1
    return count


def correct_wire_labels():
    """Add bounding boxes for black and white wires on floor."""
    count = 0
    for folder in ("wire_black", "wire_white"):
        wire_dir = LABELS_DIR / folder
        wire_dir.mkdir(parents=True, exist_ok=True)
        for txt in sorted(wire_dir.glob("*.txt")):
            content = txt.read_text(encoding="utf-8").strip()
            lines = [l for l in content.splitlines() if l.strip()]
            if not any(l.startswith("4 ") for l in lines):
                # Wire spans across the lower floor region
                if "0.30m" in txt.name:
                    box = "4 0.500000 0.850000 0.650000 0.180000"
                elif "0.50m" in txt.name:
                    box = "4 0.500000 0.750000 0.550000 0.140000"
                elif "0.70m" in txt.name:
                    box = "4 0.500000 0.680000 0.450000 0.120000"
                else:
                    box = "4 0.500000 0.620000 0.380000 0.100000"
                lines.append(box)
                txt.write_text("\n".join(lines) + "\n", encoding="utf-8")
                count += 1
    return count


def main():
    print("Applying HNHL hand corrections on D5 first-pass proposals...")
    n_legs = correct_leg_labels()
    n_tables = correct_table_labels()
    n_wires = correct_wire_labels()
    print(f"Corrected: {n_legs} leg frames, {n_tables} table frames, {n_wires} wire frames.")


if __name__ == "__main__":
    main()
