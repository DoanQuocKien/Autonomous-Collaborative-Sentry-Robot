"""Back-test of tools.door_pose on the 2026-11-11 data that exists (run from the repo root: python reports/DoanQuocKien/week-06/find_door_pose/backtest.py > .../backtest.txt).

1. Loop closure on the two full-circle scans with per-stop rows (data/t2_1111_scan*_stops.csv, copies of data/scan/<run>/stops.csv). Board 0 is seen at the first and at the last stop, so
   the true last heading is 360 + (first bearing - last bearing) if the robot did not translate (assumed). Compared: the running sum (the CSV's heading_deg), solve_scan, and solve_scan
   with the closing sightings given another marker id (the pulses stay measured but the loop is not closed: what the estimator does on a scan that has no closure).
2. fd_4 / fd_5 / fd_6 (find_door results, ../classroom_1111_pm/data): the per-stop observations were NOT saved, so the headings cannot be re-estimated. What can be redone: the pose fit and
   the uncertainty. Each scan summary (board medians in the running-sum frame, door bearing) is turned into a pseudo solve_scan result with an ASSUMED sd of each board's direction relative
   to the door (3 and 5 deg, the size of the running-sum error found in 1.) and locate_joint is run on it. Tape truth: fd_4 1.8 m at -65 deg, fd_6 3.42 m at -130 deg from the final spot."""
import csv
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.getcwd())
from tools.door_pose import locate_joint, solve_scan  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

print("1. loop closure, real scans")
for name in ("t2_1111_scan_1", "t2_1111_scan2_1"):
    rows = list(csv.DictReader(open(os.path.join(HERE, "data", name + "_stops.csv"))))
    obs = [(int(r["stop"]), int(r["marker_id"]), math.radians(float(r["bearing_deg"])), float(r["range_m"])) for r in rows]
    n = max(o[0] for o in obs) + 1
    legacy = float(rows[-1]["heading_deg"])
    b0 = {o[0]: o[2] for o in obs if o[1] == 0}
    truth = 360 + math.degrees(b0[0] - b0[n - 1])
    s = solve_scan(obs, n)
    open_ = solve_scan([(o[0], 100, o[2], o[3]) if (o[1] == 0 and o[0] > n // 2) else o for o in obs], n)
    measured = sum(1 for k in range(1, n) if {o[1] for o in obs if o[0] == k} & {o[1] for o in obs if o[0] == k - 1})
    print(" %s: %d pulses, %d with a shared board | last heading by closure %.1f | running sum %.1f (%+.1f) | solve_scan %.1f +/- %.1f (%+.1f), mean pulse %.1f, bearing residual rms %.2f deg"
          " | solve_scan without the closure %.1f +/- %.1f (%+.1f)" % (name, n - 1, measured, truth, legacy, legacy - truth, s["headings_deg"][-1], s["heading_sd_deg"][-1], s["headings_deg"][-1] - truth,
                                                                      s["pulse_deg"], s["bearing_resid_rms_deg"], open_["headings_deg"][-1], open_["heading_sd_deg"][-1], open_["headings_deg"][-1] - truth))
    print("   pulses (deg):", np.round(np.diff(s["headings_deg"]), 1).tolist())


def pseudo(summary, sd_deg):
    keys = sorted(summary["boards"])
    xy = [(summary["boards"][k]["x_m"], summary["boards"][k]["y_m"]) for k in keys]
    return dict(boards={k: dict(range_m=math.hypot(*p)) for k, p in zip(keys, xy)}, door_bearing_deg=summary["door_bearing_deg"], door_sd_deg=None, dir_keys=keys + ["door"],
                dir_rad=[math.atan2(p[1], p[0]) for p in xy] + [math.radians(summary["door_bearing_deg"])], dir_cov=np.diag([math.radians(sd_deg) ** 2] * len(keys) + [0.0]).tolist())


print("2. find_door runs from their saved summaries (headings NOT re-estimated)")
for run, tape in (("fd_4", 1.8), ("fd_5", None), ("fd_6", 3.42)):
    d = json.load(open(os.path.join(HERE, "..", "classroom_1111_pm", "data", "find_door_%s_result.json" % run)))
    old = d["located"]
    print(" %s: tape %s m | saved tool output %.2f m, spread of the range from the first spot %s, range_reliable %s, board fit rms %.2f m" % (
        run, tape, old["range_from_second_m"], old["range_from_first_spread_m"], old["range_reliable"], old["board_fit_rms_m"]))
    for sd in (3.0, 5.0):
        try:
            r = locate_joint(pseudo(d["scan1"], sd), pseudo(d["scan2"], sd))
            inside = "" if tape is None else (" -> tape inside" if r["range_from_second_interval_m"] and r["range_from_second_interval_m"][0] <= tape <= r["range_from_second_interval_m"][1] else " -> tape OUTSIDE")
            print("   assumed direction sd %.0f deg: range %.2f m, 5-95 %% interval %s%s, ray angle %.1f deg, fit chi2 %.1f on %d dof, valid %.0f %%, range_reliable %s %s" % (
                sd, r["range_from_second_m"], r["range_from_second_interval_m"], inside, r["ray_angle_deg"], r["fit_chi2"], r["fit_dof"], 100 * r["mc_valid_frac"], r["range_reliable"], r["reasons"]))
        except ValueError as e:
            print("   assumed direction sd %.0f deg: refused (%s)" % (sd, e))
