"""Label the D1 doorway / obstacle recording while tools.record runs (same laptop clock as the frames' t_local).

    python -m tools.d1_label --door cafe_glass --iref cafe_glass_iref.jpg
Place the robot, then type one line:   <distance_m> <angle_deg> <y|n door visible> [notes]     e.g.   2.0 -30 y backlit
Hold the robot still for about 5 s, then press Enter on an empty line: that ends the row. Pick the robot up and place it at the next position; the carrying time stays unlabelled. A new line also closes an open row; q quits.
Writes data/D1/doorway_labels_<door>.csv in the format of assets/d1/doorway_labels_template.csv (times as local 'YYYY-MM-DD HH:MM:SS.mmm').
"""
import argparse
import csv
from datetime import datetime
from pathlib import Path

COLS = ["door_id", "i_ref_file", "position_id", "distance_m", "angle_deg", "door_visible", "start_time", "end_time", "notes"]


def parse(line):
    """'2.0 -30 y backlit' -> (2.0, -30.0, 'yes', 'backlit'); raises ValueError on a bad line."""
    parts = line.split(None, 3)
    if len(parts) < 3 or parts[2].lower() not in ("y", "n"):
        raise ValueError("need: <distance_m> <angle_deg> <y|n> [notes]")
    return float(parts[0]), float(parts[1]), "yes" if parts[2].lower() == "y" else "no", parts[3] if len(parts) > 3 else ""


def stamp(t=None):
    return (t or datetime.now()).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--door", required=True, help="door id, e.g. cafe_glass")
    ap.add_argument("--iref", default="", help="file name of the reference photo of this door")
    ap.add_argument("--out", default="data/D1")
    a = ap.parse_args()
    path = Path(a.out) / ("doorway_labels_%s.csv" % a.door)
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(COLS)
            f.flush()
        pos = sum(1 for _ in path.open(encoding="utf-8")) - 1  # rows already there
        open_row = None  # [position_id, dist, angle, visible, start, notes]

        def close(end):
            if open_row:
                w.writerow([a.door, a.iref, open_row[0], open_row[1], open_row[2], open_row[3], open_row[4], end, open_row[5]])
                f.flush()

        print("type: <distance_m> <angle_deg> <y|n door visible> [notes]   (q = quit)   -> %s" % path)
        while True:
            line = input("pos %d> " % (pos + 1)).strip()
            if line == "":  # end the row NOW: pick the robot up after this, the carrying time stays unlabelled
                if open_row:
                    close(stamp())
                    open_row = None
                    print("  position ended; move the robot, then type the next line")
                continue
            if line.lower() == "q":
                close(stamp())
                break
            try:
                d, ang, vis, notes = parse(line)
            except ValueError as e:
                print(e)
                continue
            now = stamp()
            close(now)
            pos += 1
            open_row = [pos, d, ang, vis, now, notes]
            print("  position %d started %s (door %s)" % (pos, now[11:], vis))


if __name__ == "__main__":
    main()
