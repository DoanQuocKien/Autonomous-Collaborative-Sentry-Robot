"""Figure F15: Position error of dead reckoning with and without marker correction.

Drawn strictly from REAL physical runs (end poses & tape ground truth; no simulated/invented curves).
Reuses real physical run evidence from PR #94 (tools/plot_f15_dead_reckoning.py by DQK):
- 2026-10-24 3 m runs (reports/DoanQuocKien/week-03/t2_dead_reckoning/*/summary.json):
  Tape-measured ground truth endpoint and dead reckoning estimator endpoints.
- Error in cm against technical plan limits (<= 15 cm with correction, <= 40 cm without correction).
- 2026-10-30 deployment runs: tape offsets from sweet spot (reports/DoanQuocKien/week-05/f15/tape_offsets_1030.json).

Only endpoints and tape offsets exist for these runs (per-frame poses were not logged),
so no intermediate synthetic paths are drawn.
"""
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
W3 = ROOT / "reports" / "DoanQuocKien" / "week-03" / "t2_dead_reckoning"
OFFSETS = ROOT / "reports" / "DoanQuocKien" / "week-05" / "f15" / "tape_offsets_1030.json"
OUT = ROOT / "reports" / "kouun-rokku" / "week-05" / "F15_dead_reckoning_aruco.png"
RUNS = [("t2_1024_1", "run 1 (open loop)"), ("t2_1024_2_follow", "run 2 (closed loop)")]
HOW_COLOUR = {
    "followed board 2 to the end": "#2a7f3f",
    "lost board 2, then dead reckoning": "#c9822b",
    "dead reckoning only (provisional correction)": "#b03030",
}


def load_runs():
    out = []
    for folder, label in RUNS:
        d = json.load(open(W3 / folder / "summary.json"))
        pick = {bool(r["correction"]): r for r in d["results"] if r["scale"] == 1.0}
        out.append((label, d["true_end"], pick[False], pick[True]))
    return out


def main():
    runs = load_runs()
    fig, (a, b, c) = plt.subplots(
        1, 3, figsize=(16, 5), dpi=150, gridspec_kw={"width_ratios": [1.1, 0.9, 1.1]}
    )

    # Subplot A: Real Measured End Poses
    for k, (label, te, no, yes) in enumerate(runs):
        a.scatter(
            te["forward"], te["lateral"], marker="*", s=220, c="k", zorder=5,
            label="tape ground truth" if k == 0 else None,
        )
        for r, col, name in ((no, "#b03030", "no correction (pure DR)"), (yes, "#1f5fbf", "with ArUco markers")):
            a.scatter(r["x"], r["y"], c=col, s=60, label=name if k == 0 else None, zorder=4)
            a.plot([te["forward"], r["x"]], [te["lateral"], r["y"]], c=col, lw=1, ls=":")
        a.annotate(
            label.split(" (")[0], (te["forward"], te["lateral"]),
            textcoords="offset points", xytext=(6, 6), fontsize=8,
        )
    a.axhline(0, c="#999", lw=0.8)
    a.set_xlabel("forward from start (m)")
    a.set_ylabel("left (m)")
    a.set_title("A. End pose, tape vs estimate (2026-10-24)")
    a.set_aspect("equal")
    a.set_xlim(1.3, 3.3)
    a.set_ylim(-1.1, 1.6)
    a.legend(fontsize=8, loc="lower left")
    a.grid(alpha=0.3)

    # Subplot B: Error vs Plan Limits
    xs = range(len(runs))
    w = 0.35
    nos = [r[2]["error_m"] * 100 for r in runs]
    yess = [r[3]["error_m"] * 100 for r in runs]
    b.bar([x - w / 2 for x in xs], nos, w, color="#b03030", label="no correction")
    b.bar([x + w / 2 for x in xs], yess, w, color="#1f5fbf", label="with markers")
    for x, v in zip(xs, nos):
        b.text(x - w / 2, v + 3, "%.0f" % v, ha="center", fontsize=8)
    for x, v in zip(xs, yess):
        b.text(x + w / 2, v + 3, "%.1f" % v, ha="center", fontsize=8)
    b.axhline(40, c="#b03030", ls="--", lw=1, label="limit 40 cm (no correction)")
    b.axhline(15, c="#1f5fbf", ls="--", lw=1, label="limit 15 cm (with markers)")
    b.set_xticks(list(xs))
    b.set_xticklabels([r[0] for r in runs], fontsize=8)
    b.set_ylabel("position error at end (cm)")
    b.set_title("B. Error against plan limits (2 runs)")
    b.legend(fontsize=7, loc="upper right")

    # Subplot C: 2026-10-30 Deployment Runs
    off = json.load(open(OFFSETS))["runs"]
    for i, r in enumerate(off):
        e = math.hypot(r["dx"], r["dy"]) * 100
        c.bar(i, e, color=HOW_COLOUR[r["how"]])
        c.text(i, e + 2, "%.0f" % e, ha="center", fontsize=8)
    c.set_xticks(range(len(off)))
    c.set_xticklabels([r["run"] for r in off], fontsize=8)
    c.set_ylabel("tape offset from sweet spot (cm)")
    c.set_title("C. Deployment runs 2026-10-30")
    handles = [plt.Rectangle((0, 0), 1, 1, color=col) for col in HOW_COLOUR.values()]
    c.legend(handles, list(HOW_COLOUR), fontsize=7, loc="upper left")

    fig.suptitle(
        "F15 Dead reckoning vs marker correction: real measured runs only (tape ground truth; no synthetic curves)",
        fontsize=11,
    )
    fig.tight_layout()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT)
    plt.close()
    print("wrote", OUT)


if __name__ == "__main__":
    main()
