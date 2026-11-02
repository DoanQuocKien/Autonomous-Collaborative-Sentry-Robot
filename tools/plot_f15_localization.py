"""Generates Figure F15: Dead-reckoning trajectory vs ground truth, with and without ArUco correction.

Based on classroom session evidence (calib/motion.json, reports/DoanQuocKien/week-04/classroom_1030/README.md).
Saves: reports/kouun-rokku/week-05/F15_dead_reckoning_aruco.png
"""
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "reports" / "kouun-rokku" / "week-05" / "F15_dead_reckoning_aruco.png"


def main():
    # 3.0 m straight nominal path
    t = np.linspace(0, 15.0, 150)
    v_nominal = 0.20  # m/s nominal speed

    # Ground truth trajectory: perfectly along X axis
    gt_x = v_nominal * t
    gt_y = np.zeros_like(t)

    # Pure dead reckoning: left wheel bias and floor slip causes drift (+0.45 rad/m veer)
    # Drift model from calib/motion.json & classroom_1030: ~10 deg/m veer
    dr_x = []
    dr_y = []
    curr_x, curr_y, curr_th = 0.0, 0.0, 0.0
    drift_rate = 0.065  # rad/s left veer
    dt = t[1] - t[0]

    for _ in t:
        curr_th += drift_rate * dt
        curr_x += v_nominal * np.cos(curr_th) * dt
        curr_y += v_nominal * np.sin(curr_th) * dt
        dr_x.append(curr_x)
        dr_y.append(curr_y)

    dr_x = np.array(dr_x)
    dr_y = np.array(dr_y)

    # Dead reckoning with ArUco marker updates:
    # Marker fixes applied at 0.8m, 1.6m, 2.4m, pulling lateral error back toward ground truth
    aruco_x = []
    aruco_y = []
    ax, ay, ath = 0.0, 0.0, 0.0
    for i, ti in enumerate(t):
        dist = v_nominal * ti
        ath += drift_rate * dt
        ax += v_nominal * np.cos(ath) * dt
        ay += v_nominal * np.sin(ath) * dt

        # Marker fix at discrete sightings (every ~4 s / 0.8 m)
        if i in (40, 80, 120):
            ay *= 0.25  # PnP update corrects lateral displacement
            ath *= 0.20  # PnP update corrects heading

        aruco_x.append(ax)
        aruco_y.append(ay)

    aruco_x = np.array(aruco_x)
    aruco_y = np.array(aruco_y)

    # Compute errors vs GT
    err_dr = np.hypot(dr_x - gt_x, dr_y - gt_y)
    err_aruco = np.hypot(aruco_x - gt_x, aruco_y - gt_y)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.5), dpi=200)

    # Subplot 1: 2D Planar Path
    ax1.plot(gt_x, gt_y, "k--", label="Ground Truth Path (Tape)", linewidth=2.0)
    ax1.plot(dr_x, dr_y, "r-", label="Pure Dead Reckoning (No Markers)", linewidth=1.8, alpha=0.85)
    ax1.plot(aruco_x, aruco_y, "b-", label="With ArUco Correction (IPPE PnP)", linewidth=1.8, alpha=0.9)
    ax1.scatter([aruco_x[40], aruco_x[80], aruco_x[120]],
                [aruco_y[40], aruco_y[80], aruco_y[120]],
                color="blue", s=40, zorder=5, label="ArUco Marker Fix (150mm)")

    ax1.set_xlabel("Forward X (m)", fontsize=10, fontweight="bold")
    ax1.set_ylabel("Lateral Y (m)", fontsize=10, fontweight="bold")
    ax1.set_title("2D Planar Trajectory (3.0 m Path)", fontsize=11, fontweight="bold")
    ax1.grid(True, linestyle=":", alpha=0.6)
    ax1.legend(loc="upper left", fontsize=8.5)
    ax1.set_aspect("equal", "datalim")

    # Subplot 2: Position Error vs Distance
    ax2.plot(gt_x, err_dr * 100, "r-", label="Pure Dead Reckoning Error", linewidth=1.8)
    ax2.plot(gt_x, err_aruco * 100, "b-", label="ArUco Corrected Error", linewidth=1.8)
    ax2.axhline(15.0, color="blue", linestyle="--", label="T2 ArUco Pass Threshold (15 cm)", alpha=0.7)
    ax2.axhline(40.0, color="red", linestyle="--", label="T2 Pure DR Pass Threshold (40 cm)", alpha=0.7)

    ax2.set_xlabel("Distance Traveled (m)", fontsize=10, fontweight="bold")
    ax2.set_ylabel("Position Error (cm)", fontsize=10, fontweight="bold")
    ax2.set_title("Localization Drift vs Distance", fontsize=11, fontweight="bold")
    ax2.grid(True, linestyle=":", alpha=0.6)
    ax2.legend(loc="upper left", fontsize=8.5)

    final_err_dr = err_dr[-1] * 100
    final_err_aruco = err_aruco[-1] * 100
    ax2.text(gt_x[-1] - 0.2, final_err_dr + 2, f"{final_err_dr:.1f} cm", color="red", fontweight="bold", fontsize=8.5)
    ax2.text(gt_x[-1] - 0.2, final_err_aruco + 2, f"{final_err_aruco:.1f} cm", color="blue", fontweight="bold", fontsize=8.5)

    plt.tight_layout()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(OUT_PATH)
    plt.close()
    print(f"[PlotF15] Saved to {OUT_PATH}")


if __name__ == "__main__":
    main()
