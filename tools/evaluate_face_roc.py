"""Face Verification ROC Evaluation Tool (Week 3, HNHL).

Implements the ROC calculation logic, leave-one-out rotation, and FAR/FRR analysis
for face verification threshold calibration.
(Implementation Plan line 242, §4.3).

NOTE: When run without real D2 entries, it runs on simulated embeddings as a
pipeline verification test (T0). T1 acceptance will be run on real D2 recordings
collected during the team integration session.
"""
import argparse
import json
from pathlib import Path
from typing import Dict, List, Tuple
import numpy as np

from sentry.config import load
from sentry.perception.face import FaceVerifier, normalize_embedding


def generate_simulated_eval_vectors(seed=532):
    """Generate simulated feature sets (3 members x 10 entries + negatives) for pipeline testing."""
    rng = np.random.RandomState(seed)

    identities = ["member_DQK", "member_HNHL", "member_KR"]
    centroids = {name: normalize_embedding(rng.randn(512)) for name in identities}

    dataset = {}
    for name in identities:
        samples = []
        for _ in range(10):
            noise = rng.randn(512) * 0.028
            samples.append(normalize_embedding(centroids[name] + noise))
        dataset[name] = samples

    negatives = []
    for _ in range(60):
        negatives.append(normalize_embedding(rng.randn(512)))

    return dataset, negatives


def evaluate_roc(dataset, negatives, thresholds=None) -> Dict:
    """Compute TAR, FAR, FRR across thresholds using leave-one-out."""
    if thresholds is None:
        thresholds = np.linspace(0.10, 0.85, 31).round(3).tolist()

    identities = list(dataset.keys())
    genuine_scores: List[float] = []
    impostor_scores: List[float] = []

    for stranger_idx, stranger in enumerate(identities):
        enrolled_whitelist = {}
        for member in identities:
            if member != stranger:
                enrolled_whitelist[member] = dataset[member][:3]

        verifier = FaceVerifier(enrolled_whitelist, threshold=0.0)

        for member in enrolled_whitelist:
            for query in dataset[member][3:]:
                _, score, _ = verifier.verify(query)
                genuine_scores.append(score)

        for query in dataset[stranger]:
            _, score, _ = verifier.verify(query)
            impostor_scores.append(score)

        for neg in negatives[:20]:
            _, score, _ = verifier.verify(neg)
            impostor_scores.append(score)

    roc_curve = []
    best_operating_point = None

    for th in thresholds:
        fa_count = sum(1 for s in impostor_scores if s >= th)
        far = fa_count / len(impostor_scores) if impostor_scores else 0.0

        fr_count = sum(1 for s in genuine_scores if s < th)
        frr = fr_count / len(genuine_scores) if genuine_scores else 0.0
        tar = 1.0 - frr

        point = {
            "threshold": float(th),
            "tar": round(tar, 4),
            "far": round(far, 4),
            "frr": round(frr, 4),
        }
        roc_curve.append(point)

        if abs(th - 0.45) < 0.015:
            best_operating_point = point

    cfg_th = float(load().get("thresholds", {}).get("whitelist_cosine", 0.45))

    results = {
        "status": "SIMULATION_PROTOTYPE",
        "is_real_d2": False,
        "t1_accepted": False,
        "note": "Simulation prototype to verify ROC logic and threshold calculation. T1 acceptance is pending live D2 doorway recording during the Sunday team session.",
        "dataset_name": "simulated_d2_leave_one_out",
        "num_identities": len(identities),
        "total_genuine_queries": len(genuine_scores),
        "total_impostor_queries": len(impostor_scores),
        "config_threshold": cfg_th,
        "operating_point": best_operating_point or roc_curve[len(roc_curve) // 2],
        "target_tar_threshold": 0.95,
        "target_far_threshold": 0.01,
        "roc_curve": roc_curve,
    }

    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="reports/HuynhNguyenHoaiLoc/week-03/face_roc_metrics.json")
    args = parser.parse_args()

    dataset, negatives = generate_simulated_eval_vectors()
    results = evaluate_roc(dataset, negatives)

    out_file = Path(args.out)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"ROC evaluation prototype saved to {out_file}")
    print(f"Status: {results['status']} (t1_accepted={results['t1_accepted']})")


if __name__ == "__main__":
    main()
