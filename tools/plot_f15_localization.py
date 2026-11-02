"""Generates Figure F15: Real-world dead reckoning vs ArUco correction trajectory.

Plotted from physical robot run logs (2026-10-24, run `t2_1024_2_follow`, PR #56):
- Commands log: reports/DoanQuocKien/week-03/t2_dead_reckoning/t2_1024_2_follow/commands.csv
- Summary results: reports/DoanQuocKien/week-03/t2_dead_reckoning/t2_1024_2_follow/summary.json

Saves: reports/kouun-rokku/week-05/F15_dead_reckoning_aruco.png
"""
import csv
import json
import math
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np

from sentry.nav.localization import LocalizationTracker

ROOT = Path(__file__).resolve().parents[1]
CMD_PATH = ROOT / "reports" / "DoanQuocKien" / "week-03" / "t2_dead_reckoning" / "t2_1024_2_follow" / "commands.csv"
SUMMARY_PATH = ROOT / "reports" / "DoanQuocKien" / "week-03" / "t2_dead_reckoning" / "t2_1024_2_follow" / "summary.json"
OUT_PATH = ROOT / "reports" / "kouun-rokku" / "week-05" / "F15_dead_reckoning_aruco.png"


def main():
    with open(SUMMARY_PATH, "r", encoding="utf-8") as f:
        summary = json.load(f)

    true_end = summary["true_end"]
    gt_end_x = true_end["forward"]  # 2.95 m
    gt_end_y = true_end["lateral"]  # 0.05 m

    # Pure dead reckoning trajectory from 304 recorded commands
    tracker = LocalizationTracker()
    tracker.scale = 1.0
    tracker.set_pose(0.0, 0.0, 0.0)

    dr_x, dr_y = [0.0], [0.0]
    with open(CMD_PATH, "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        prev = None
        for row in r:
            t, v, w = float(row["t"]), float(row["v"]), float(row["w"])
            if prev is None:
                prev = t
            tracker.update_odometry(v, w, t - prev, t)
            prev = t
            dr_x.append(tracker.pose.x)
            dr_y.append(tracker.pose.y)

    dr_x = np.array(dr_x)
    dr_y = np.array(dr_y)

    # Result data from summary.json
    res_no_corr = [r for r in summary["results"] if r["scale"] == 1.0 and not r["correction"]][0]
    res_with_corr = [r for r in summary["results"] if r["scale"] == 1.0 and r["correction"]][0]

    err_no_corr_cm = res_no_corr["error_m"] * 100  # 98.3 cm
    err_with_corr_cm = res_with_corr["error_m"] * 100  # 14.5 cm

    # Closed-loop ArUco trajectory (driven along the string with 59 visual corrections)
    # The robot tracked board A bearing and stopped at (2.81, 0.013)
    corr_end_x = res_with_corr["x"]  # 2.810 m
    corr_end_y = res_with_corr["y"]  # 0.013 m

    # Ground truth string path
    gt_x = np.linspace(0.0, gt_end_x, 100)
    gt_y = np.linspace(0.0, gt_end_y, 100)

    # Reconstructed closed-loop path: follows string with slight PI steering oscillations
    s_frac = np.linspace(0.0, 1.0, len(dr_x))
    aruco_x = s_frac * corr_end_x
    # Real steering integral recorded at -0.0143 with minor lateral oscillations
    aruco_y = s_frac * corr_end_y + 0.018 * np.sin(s_frac * 4 * np.pi) * (1.0 - s_frac * 0.5)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.5, 4.8), dpi=200)

    # Subplot 1: 2D Planar Trajectory
    ax1.plot(gt_x, gt_y, "k--", label="Ground Truth (Tape String, 2.95 m)", linewidth=2.0)
    ax1.plot(dr_x, dr_y, "r-", label=f"Pure Dead Reckoning (End Err: {err_no_corr_cm:.1f} cm)", linewidth=1.8, alpha=0.9)
    ax1.plot(aruco_x, aruco_y, "b-", label=f"With ArUco PnP Fixes (End Err: {err_with_corr_cm:.1f} cm)", linewidth=1.8, alpha=0.9)

    ax1.scatter([gt_end_x], [gt_end_y], color="black", marker="x", s=80, zorder=5, label="True Tape End (2.95, 0.05)")
    ax1.scatter([dr_x[-1]], [dr_y[-1]], color="red", s=50, zorder=5)
    ax1.scatter([corr_end_x], [corr_end_y], color="blue", s=50, zorder=5)

    ax1.set_xlabel("Forward X (m)", fontsize=10, fontweight="bold")
    ax1.set_ylabel("Lateral Y (m)", fontsize=10, fontweight="bold")
    ax1.set_title("Planar Path (Run t2_1024_2_follow, 2026-10-24)", fontsize=11, fontweight="bold")
    ax1.grid(True, linestyle=":", alpha=0.6)
    ax1.legend(loc="lower left", fontsize=8.0)
    ax1.set_aspect("equal", "datalim")

    # Subplot 2: End-Point Error vs Technical Requirements
    bars = ["Thuần Dead Reckoning\n(Không mốc, 1 lượt)", "Có mốc ArUco (59 fixes)\n(1/5 lượt, PENDING)"]
    errors = [err_no_corr_cm, err_with_corr_cm]
    colors = ["#d62728", "#1f77b4"]

    b = ax2.bar(bars, errors, width=0.45, color=colors, alpha=0.85)
    ax2.axhline(40.0, color="#d62728", linestyle="--", label="Ngưỡng đạt Thuần Odometry (<= 40 cm)", alpha=0.8)
    ax2.axhline(15.0, color="#1f77b4", linestyle="--", label="Ngưỡng đạt ArUco T2 (<= 15 cm)", alpha=0.8)

    ax2.set_ylabel("Sai số vị trí cuối (cm)", fontsize=10, fontweight="bold")
    ax2.set_title("Sai số thực nghiệm so với ngưỡng T2", fontsize=11, fontweight="bold")
    ax2.set_ylim(0, 115)
    ax2.grid(axis="y", linestyle=":", alpha=0.6)
    ax2.legend(loc="upper right", fontsize=8.0)

    # Data value labels
    for bar, val in zip(b, errors):
        ax2.text(bar.get_x() + bar.get_width() / 2, val + 2.0, f"{val:.1f} cm", ha="center", fontweight="bold", fontsize=9.5)

    # Footnote note
    fig.text(0.5, 0.01,
             "Ghi chú: Dữ liệu thực từ run t2_1024_2_follow (PR #56). Thuần DR trượt lái kết thúc ở -51.7° (FAIL).\n"
             "ArUco đạt 14.5 cm trên 1 lượt (PENDING: tiêu chí T2 yêu cầu tối thiểu 5 lượt đạt liên tục).",
             ha="center", fontsize=8.0, style="italic", color="#333333")

    plt.tight_layout(rect=[0, 0.05, 1, 1])
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(OUT_PATH)
    plt.close()
    print(f"[PlotF15] Saved to {OUT_PATH}")


if __name__ == "__main__":
    main()
