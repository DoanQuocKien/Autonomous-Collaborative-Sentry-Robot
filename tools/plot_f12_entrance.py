"""Generates Figure F12: Entrance recognition bake-off (ORB vs XFeat vs DINOv2).

Source: reports/DoanQuocKien/week-02/d1/entrance_bench_robot_ref.json
Saves: reports/kouun-rokku/week-05/F12_entrance_bakeoff.png
"""
import json
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "reports" / "DoanQuocKien" / "week-02" / "d1" / "entrance_bench_robot_ref.json"
OUT_PATH = ROOT / "reports" / "kouun-rokku" / "week-05" / "F12_entrance_bakeoff.png"


def main():
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Filter methods for both doors
    methods = ["orb", "xfeat", "dino_s", "dino_b"]
    labels = ["ORB (Baseline)", "XFeat (Lightweight)", "DINOv2-S (ViT-S)", "DINOv2-B (ViT-B)"]

    class_results = {r["method"]: r for r in data["results"] if r.get("door") == "class_door"}
    cafe_results = {r["method"]: r for r in data["results"] if r.get("door") == "cafe_glass"}

    class_auc = [class_results[m]["auc"] for m in methods]
    cafe_auc = [cafe_results[m]["auc"] for m in methods]

    class_tpr = [class_results[m]["tpr_at_5pct_fpr"] for m in methods]
    cafe_tpr = [cafe_results[m]["tpr_at_5pct_fpr"] for m in methods]

    x = np.arange(len(methods))
    width = 0.35

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.5), dpi=200)

    # Subplot 1: AUC
    ax1.bar(x - width / 2, class_auc, width, label="Classroom Door (Primary)", color="#1f77b4", alpha=0.9)
    ax1.bar(x + width / 2, cafe_auc, width, label="Cafe Glass Door (Secondary)", color="#aec7e8", alpha=0.9)
    ax1.set_ylabel("ROC AUC", fontsize=11, fontweight="bold")
    ax1.set_title("Entrance Recognition AUC (Robot Reference)", fontsize=11, fontweight="bold")
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, rotation=15, ha="right", fontsize=9)
    ax1.set_ylim(0.5, 1.05)
    ax1.axhline(1.0, color="gray", linestyle="--", alpha=0.5)
    ax1.legend(loc="lower right", fontsize=9)
    ax1.grid(axis="y", linestyle=":", alpha=0.6)

    # Add data labels
    for i in range(len(methods)):
        ax1.text(x[i] - width / 2, class_auc[i] + 0.01, f"{class_auc[i]:.3f}", ha="center", fontsize=8)
        ax1.text(x[i] + width / 2, cafe_auc[i] + 0.01, f"{cafe_auc[i]:.3f}", ha="center", fontsize=8)

    # Subplot 2: TPR @ 5% FPR
    ax2.bar(x - width / 2, class_tpr, width, label="Classroom Door", color="#2ca02c", alpha=0.9)
    ax2.bar(x + width / 2, cafe_tpr, width, label="Cafe Glass Door", color="#98df8a", alpha=0.9)
    ax2.set_ylabel("True Positive Rate (TPR @ 5% FPR)", fontsize=11, fontweight="bold")
    ax2.set_title("TPR at 5% FPR Operating Point", fontsize=11, fontweight="bold")
    ax2.set_xticks(x)
    ax2.set_xticklabels(labels, rotation=15, ha="right", fontsize=9)
    ax2.set_ylim(0.0, 1.15)
    ax2.axhline(0.90, color="red", linestyle="--", label="T1 Pass Threshold (90%)", alpha=0.8)
    ax2.legend(loc="upper left", fontsize=9)
    ax2.grid(axis="y", linestyle=":", alpha=0.6)

    for i in range(len(methods)):
        ax2.text(x[i] - width / 2, class_tpr[i] + 0.02, f"{class_tpr[i] * 100:.1f}%", ha="center", fontsize=8)
        ax2.text(x[i] + width / 2, cafe_tpr[i] + 0.02, f"{cafe_tpr[i] * 100:.1f}%", ha="center", fontsize=8)

    plt.tight_layout()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(OUT_PATH)
    plt.close()
    print(f"[PlotF12] Saved to {OUT_PATH}")


if __name__ == "__main__":
    main()
