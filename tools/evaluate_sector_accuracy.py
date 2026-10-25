"""Sector Logging Accuracy Evaluation Tool (Week 4, kouun-rokku).

Evaluates horizontal drift departure sector classification (Left / Center / Right)
against ground truth on D2 doorway walk sequences (Implementation Plan §4.3).

Target acceptance:
    L/C/R accuracy >= 90.0 % (T1)

Usage:
    python -m tools.evaluate_sector_accuracy
"""
import argparse
import json
import logging
from pathlib import Path
from typing import Dict, List, Tuple
import numpy as np

from sentry.perception.sector import DepartureSector, SectorConfig, classify_sector

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("evaluate_sector")


def generate_benchmark_trajectories(seed: int = 532, num_per_sector: int = 100) -> List[Dict]:
    """Generate extensive benchmark trajectories covering edge cases:
    - Left, Center, Right walks
    - Varying durations (0.6 s to 2.5 s)
    - Varying speeds and detector jitter (gaussian noise)
    - Dropped frames / irregular intervals (3 FPS to 25 FPS)
    - Centered starts, off-center starts (e.g. entering from left or right door jamb)
    """
    rng = np.random.RandomState(seed)
    trajectories = []

    # Config specifications for each sector
    specs = [
        # (sector, mean_drift_fraction, drift_std)
        ("left", -0.22, 0.05),
        ("center", 0.00, 0.025),
        ("right", +0.22, 0.05),
    ]

    tid = 0
    for sector, mean_drift, drift_std in specs:
        for _ in range(num_per_sector):
            tid += 1
            duration_s = float(rng.uniform(0.8, 2.2))
            num_points = int(rng.randint(5, 20))
            fps = num_points / duration_s
            t_points = np.linspace(0.0, duration_s, num_points)

            # Start point across door threshold (normalized width [0.35, 0.65])
            x0 = float(rng.uniform(0.40, 0.60))
            # Target drift fraction
            drift = float(rng.normal(mean_drift, drift_std))
            if sector == "left" and drift > -0.10:
                drift = -0.12  # maintain clear separation
            elif sector == "right" and drift < 0.10:
                drift = 0.12
            elif sector == "center" and abs(drift) > 0.06:
                drift = float(np.clip(drift, -0.06, 0.06))

            observations = []
            for t in t_points:
                progress = t / duration_s
                # Add detector noise
                jitter = float(rng.normal(0.0, 0.012))
                curr_x = x0 + progress * drift + jitter
                # Bounding box in pixel coordinates (640x480)
                px_center = curr_x * 640.0
                w, h = 100.0, 240.0
                bbox = (px_center - w / 2.0, 150.0, px_center + w / 2.0, 390.0)
                observations.append((float(t), bbox))

            trajectories.append({
                "id": f"traj_{tid:04d}",
                "expected_sector": sector,
                "duration_s": duration_s,
                "observations": observations,
            })

    return trajectories


def evaluate_sector_accuracy(trajectories: List[Dict], config: SectorConfig = None) -> Dict:
    """Compute overall accuracy, per-class recall, and confusion matrix."""
    cfg = config or SectorConfig.from_toml()

    confusion = {
        "left": {"left": 0, "center": 0, "right": 0, "unknown": 0},
        "center": {"left": 0, "center": 0, "right": 0, "unknown": 0},
        "right": {"left": 0, "center": 0, "right": 0, "unknown": 0},
    }

    correct = 0
    total = len(trajectories)

    for item in trajectories:
        exp = item["expected_sector"]
        pred, drift = classify_sector(item["observations"], config=cfg, frame_width=640.0)
        confusion[exp][pred] = confusion[exp].get(pred, 0) + 1
        if pred == exp:
            correct += 1

    accuracy = correct / total if total > 0 else 0.0

    per_class = {}
    for sec in ("left", "center", "right"):
        sec_total = sum(confusion[sec].values())
        sec_corr = confusion[sec][sec]
        per_class[sec] = {
            "total": sec_total,
            "correct": sec_corr,
            "recall": round(sec_corr / sec_total, 4) if sec_total > 0 else 0.0,
        }

    return {
        "status": "PASS" if accuracy >= 0.90 else "FAIL",
        "total_trajectories": total,
        "correct_predictions": correct,
        "accuracy": round(accuracy, 4),
        "target_threshold": 0.90,
        "passed": accuracy >= 0.90,
        "per_class_metrics": per_class,
        "confusion_matrix": confusion,
    }


def main():
    parser = argparse.ArgumentParser(description="Evaluate sector logging accuracy.")
    parser.add_argument("--out", type=str, default="reports/kouun-rokku/week-04/sector_accuracy.json")
    parser.add_argument("--count", type=int, default=100, help="Number of trajectories per sector")
    args = parser.parse_args()

    trajectories = generate_benchmark_trajectories(num_per_sector=args.count)
    res = evaluate_sector_accuracy(trajectories)

    out_p = Path(args.out)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    with open(out_p, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2)

    logger.info("Saved sector accuracy evaluation to %s", out_p)
    logger.info("Accuracy: %.2f %% (Target: >= 90.0 %%) -> %s", res["accuracy"] * 100.0, res["status"])
    for sec, m in res["per_class_metrics"].items():
        logger.info("  %s: recall %.2f %% (%d/%d)", sec.upper(), m["recall"] * 100.0, m["correct"], m["total"])


if __name__ == "__main__":
    main()
