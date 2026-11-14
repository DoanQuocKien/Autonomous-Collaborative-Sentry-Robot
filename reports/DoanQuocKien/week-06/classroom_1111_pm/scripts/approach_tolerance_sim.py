"""Why `approach_door` hunted in run ap_1 and which centring window fixes it (2026-11-11). Reads data/approach_ap_1_log.csv (committed copy), measures the size of the turn pulses and of the drive veer,
then simulates the controller with those numbers (fixed seeds) for several tolerance windows and aim offsets. Descriptive: one run, one floor; the simulation shares the model it was fitted from.
  PYTHONPATH=. python reports/DoanQuocKien/week-06/classroom_1111_pm/scripts/approach_tolerance_sim.py"""
import csv
from pathlib import Path

import numpy as np

LOG = Path(__file__).resolve().parents[1] / "data/approach_ap_1_log.csv"
rows = list(csv.DictReader(open(LOG)))
small, big, drive = [], [], []
for a, b in zip(rows, rows[1:]):
    if a["bearing_deg"] == "" or b["bearing_deg"] == "":
        continue
    ba, bb = float(a["bearing_deg"]), float(b["bearing_deg"])
    if a["action"] in ("turn_left", "turn_right"):
        turned = (ba - bb) * (1 if a["action"] == "turn_left" else -1)            # degrees turned in the commanded direction
        (big if abs(ba) > 12 else small).append(turned)
    elif a["action"] == "drive":
        drive.append(bb - ba)
SMALL, BIG, VEER = float(np.median(small)), float(np.median(big)), float(np.mean(drive))
print("0.12 s pulse: median %.1f deg (n=%d, sd %.1f); 0.2 s pulse: median %.1f deg (n=%d); drive burst 0.6 s: bearing change %.1f deg (sd %.1f, n=%d)" % (SMALL, len(small), np.std(small), BIG, len(big), VEER, np.std(drive), len(drive)))


def run(tol, offset, bursts=10, seed=0):
    r, b, steps, turns, maxb, d = np.random.default_rng(seed), -36.0, 0, 0, 0.0, 0
    while d < bursts and steps < 200:
        meas = b + r.normal(0, 1.2) - offset
        steps += 1
        if meas > tol:
            b -= (BIG if meas > 16 else SMALL) + r.normal(0, 2.5)
            turns += 1
        elif meas < -tol:
            b += (BIG if meas < -16 else SMALL) + r.normal(0, 2.5)
            turns += 1
        else:
            b += VEER + r.normal(0, 2.0)
            d += 1
            maxb = max(maxb, abs(b))
    return steps, turns, maxb


print("tolerance offset | median steps  median turns  p90 |bearing| while driving (300 seeds)")
for tol, off in ((4, 0), (6, 0), (8, 0), (10, 0), (8, 2.75), (10, 2.75)):
    res = np.array([run(tol, off, seed=s) for s in range(300)])
    print("%6d %6.2f | %8.0f %8.0f %8.1f" % (tol, off, np.median(res[:, 0]), np.median(res[:, 1]), np.percentile(res[:, 2], 90)))
