"""Turn a D1 recording + its label CSV into a manifest of labelled frames (one row per frame), cutting each row to the stretch where the robot sat still.

    python -m tools.d1_manifest --door cafe_glass            # reads data/D1/jetbot_meta.jsonl and doorway_labels_cafe_glass.csv, writes data/D1/manifest_cafe_glass.csv
Per label row: a note containing 'exclude' drops it; 'moving' keeps every frame; otherwise only the longest still stretch is kept (carrying time and settling are cut), and at most --max-per-row frames (evenly spaced) so a 4-minute row does not outweigh a 5 s one.
"""
import argparse
import csv
import json
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

STILL_DIFF = 2.5  # mean grey-level change between consecutive 80x60 frames below which the robot counts as still
SMOOTH = 5        # frames


def longest_still(times, diffs, thr=STILL_DIFF, smooth=SMOOTH):
    """times: n frame times; diffs: n-1 differences between consecutive frames. -> (first, last) frame indices of the longest still stretch, or None."""
    if len(diffs) == 0:
        return None
    still = np.convolve(diffs, np.ones(smooth) / smooth, mode="same") < thr
    best, k = None, 0
    while k < len(still):
        if still[k]:
            j = k
            while j < len(still) and still[j]:
                j += 1
            if best is None or times[j] - times[k] > times[best[1]] - times[best[0]]:
                best = (k, j)  # frames k..j (j is the frame after the last still diff)
            k = j
        else:
            k += 1
    return best


def small(path):
    return cv2.resize(cv2.imread(str(path), cv2.IMREAD_GRAYSCALE), (80, 60), interpolation=cv2.INTER_AREA).astype(np.float32)


def epoch(s):
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S.%f").timestamp()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--door", required=True)
    ap.add_argument("--dir", default="data/D1")
    ap.add_argument("--max-per-row", type=int, default=100)
    a = ap.parse_args()
    d = Path(a.dir)
    meta = [json.loads(line) for line in (d / "jetbot_meta.jsonl").open(encoding="utf-8")]
    t = np.array([m["t_local"] for m in meta])
    out_rows, summary = [], []
    for r in csv.DictReader((d / ("doorway_labels_%s.csv" % a.door)).open(encoding="utf-8")):
        note = r["notes"].lower()
        idx = np.where((t >= epoch(r["start_time"])) & (t <= epoch(r["end_time"])))[0]
        if "exclude" in note:
            summary.append((r["position_id"], r["door_visible"], len(idx), 0, "excluded"))
            continue
        if "moving" not in note:
            if len(idx) < 10:
                summary.append((r["position_id"], r["door_visible"], len(idx), 0, "too few frames"))
                continue
            diffs = [np.abs(small(d / "jetbot" / meta[idx[k + 1]]["file"]) - small(d / "jetbot" / meta[idx[k]]["file"])).mean() for k in range(len(idx) - 1)]
            seg = longest_still(t[idx], diffs)
            if seg is None or seg[1] - seg[0] < 10:
                summary.append((r["position_id"], r["door_visible"], len(idx), 0, "no still stretch"))
                continue
            idx = idx[seg[0]:seg[1] + 1]
        if len(idx) > a.max_per_row:
            idx = idx[np.linspace(0, len(idx) - 1, a.max_per_row).astype(int)]
        for i in idx:
            out_rows.append([meta[i]["file"], "%.3f" % t[i], r["door_id"], r["position_id"], r["distance_m"], r["angle_deg"], r["door_visible"], r["notes"]])
        summary.append((r["position_id"], r["door_visible"], int(((t >= epoch(r["start_time"])) & (t <= epoch(r["end_time"]))).sum()), len(idx), "ok"))
    path = d / ("manifest_%s.csv" % a.door)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["frame_file", "t_local", "door_id", "position_id", "distance_m", "angle_deg", "door_visible", "notes"])
        w.writerows(out_rows)
    for s in summary:
        print("row %3s door %-3s: %5d frames in the row -> %4d kept (%s)" % s)
    pos = sum(1 for r in out_rows if r[6] == "yes")
    print("manifest %s: %d frames (door visible %d, not visible %d)" % (path, len(out_rows), pos, len(out_rows) - pos))


if __name__ == "__main__":
    main()
