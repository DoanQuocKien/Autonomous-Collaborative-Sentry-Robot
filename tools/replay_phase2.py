"""Phase 2 Replay Tool on D2 Dataset (Week 4, kouun-rokku).

Replays recorded ESP32-CAM doorway entries through the end-to-end Phase 2 monitoring pipeline:
  ESP32 stream -> Face Verification -> OSNet re-ID Appearance -> Sector Logging -> TargetQueue -> StateMachine

Usage:
    python -m tools.replay_phase2 --simulated --out reports/kouun-rokku/week-04/phase2_replay_summary.json

This tool uses synthetic entries and mock appearance vectors. For the actual
shared D2 cafe pilot, use tools.evaluate_d2_pilot; neither tool approves T1.
"""
import argparse
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from sentry.app.phase2_pipeline import MockAppearanceExtractor, Phase2Pipeline
from sentry.app.state_machine import State, StateMachine
from sentry.app.target_queue import TargetQueue
from sentry.perception.face import FaceVerifier, normalize_embedding

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("replay_phase2")


def generate_d2_replay_entries(
    seed: int = 532,
    num_per_member: int = 10,
    stranger_identity: str = "member_KR",
) -> Tuple[Dict[str, List[np.ndarray]], List[Dict[str, Any]]]:
    """Generate D2 leave-one-out replay entries (Implementation Plan §4.3 & PR #57).

    The three teammates (DQK, HNHL, KR) each have 10 entrance sequences.
    In this fold, two members are enrolled in the whitelist, and the third is the stranger (intruder).
    Trajectories simulate realistic walking paths departing Left, Center, or Right.
    """
    rng = np.random.RandomState(seed)
    identities = ["member_DQK", "member_HNHL", "member_KR"]
    centroids = {name: normalize_embedding(rng.randn(512)) for name in identities}

    # Enrolled whitelist (exclude stranger_identity)
    whitelist = {}
    for name in identities:
        if name != stranger_identity:
            # 3 enrolled reference embeddings
            whitelist[name] = [
                normalize_embedding(centroids[name] + rng.randn(512) * 0.02)
                for _ in range(3)
            ]

    entries = []
    entry_counter = 0

    # Sector patterns: L (moves from x=320 to x=180), C (stays around x=320), R (moves from x=320 to x=460)
    sector_specs = [
        ("left", -120.0),
        ("center", 5.0),
        ("right", 130.0),
    ]

    for member_idx, name in enumerate(identities):
        for run_idx in range(num_per_member):
            entry_counter += 1
            entry_id = f"D2_{name}_run{run_idx+1:02d}"
            is_stranger = (name == stranger_identity)

            # Face embedding for this run (centroid + small natural variation)
            face_emb = normalize_embedding(centroids[name] + rng.randn(512) * 0.025)

            # Planned departure sector for this entry
            sec_name, x_shift = sector_specs[run_idx % len(sector_specs)]

            # Generate 2.0 s trajectory (10 frames at 5 FPS)
            t_start = 100.0 + entry_counter * 10.0
            observations = []
            x0 = 320.0 + rng.randn() * 8.0
            y0 = 150.0

            for step in range(10):
                t = t_start + step * 0.2
                progress = step / 9.0  # 0.0 to 1.0
                curr_x = x0 + progress * x_shift + rng.randn() * 3.0
                curr_y = y0 + progress * 80.0
                # Bounding box ~ 100 px wide, 240 px tall
                w, h = 100.0, 240.0
                bbox = (curr_x - w / 2.0, curr_y - h / 2.0, curr_x + w / 2.0, curr_y + h / 2.0)
                observations.append((t, bbox))

            # Simulated body crop image
            dummy_crop = np.full((256, 128, 3), 100 + member_idx * 40 + run_idx * 2, dtype=np.uint8)

            entries.append({
                "id": entry_id,
                "person_name": name,
                "is_stranger": is_stranger,
                "expected_sector": sec_name,
                "face_embedding": face_emb,
                "person_crop_bgr": dummy_crop,
                "observations": observations,
                "timestamp": t_start,
            })

    return whitelist, entries


def run_phase2_replay(
    entries: List[Dict[str, Any]],
    whitelist: Dict[str, List[np.ndarray]],
    cosine_threshold: float = 0.45,
    snapshot_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Execute Phase 2 replay end-to-end and evaluate acceptance criteria."""
    verifier = FaceVerifier(whitelist=whitelist, threshold=cosine_threshold)
    extractor = MockAppearanceExtractor(seed=532)
    queue = TargetQueue()
    sm = StateMachine(initial_state=State.STANDBY, t0=90.0)

    pipeline = Phase2Pipeline(
        face_verifier=verifier,
        appearance_extractor=extractor,
        target_queue=queue,
        state_machine=sm,
        snapshot_dir=snapshot_dir,
    )

    summary = pipeline.replay_dataset(entries)

    # Evaluate sector classification accuracy against ground-truth labels
    correct_sectors = 0
    total_sector_eval = 0
    confusion = {"left": {"left": 0, "center": 0, "right": 0},
                 "center": {"left": 0, "center": 0, "right": 0},
                 "right": {"left": 0, "center": 0, "right": 0}}

    for entry, result in zip(entries, summary.event_results):
        exp = entry.get("expected_sector")
        pred = result.sector
        if exp in confusion:
            total_sector_eval += 1
            if pred in confusion[exp]:
                confusion[exp][pred] += 1
            if exp == pred:
                correct_sectors += 1

    sector_accuracy = (correct_sectors / total_sector_eval) if total_sector_eval > 0 else 0.0

    # Verification accuracy
    false_accepts = sum(1 for e, r in zip(entries, summary.event_results) if e["is_stranger"] and not r.is_intruder)
    false_rejects = sum(1 for e, r in zip(entries, summary.event_results) if not e["is_stranger"] and r.is_intruder)

    simulation_pass = false_accepts == 0 and false_rejects == 0 and sector_accuracy >= 0.90
    results = {
        "status": "SIMULATION_PASS" if simulation_pass else "SIMULATION_FAIL",
        "evaluation_tier": "T0_SIMULATED_APPEARANCE",
        "appearance_simulated": True,
        "t1_accepted": False,
        "total_entries": summary.total_entries,
        "authorized_count": summary.authorized_count,
        "intruder_count": summary.intruder_count,
        "false_accepts": false_accepts,
        "false_rejects": false_rejects,
        "sector_evaluation": {
            "total_evaluated": total_sector_eval,
            "correct": correct_sectors,
            "accuracy": round(sector_accuracy, 4),
            "threshold_required": 0.90,
            "passed": sector_accuracy >= 0.90,
            "confusion_matrix": confusion,
        },
        "sector_distribution": summary.sector_counts,
        "queue_metrics": {
            "final_queued_length": summary.final_queue_length,
            "active_target_id": summary.active_target_id,
            "history_count": len(queue.all_history()),
        },
        "state_machine_transitions": [
            {
                "prev_state": r.prev_state.value,
                "state": r.state.value,
                "event": r.event,
                "t": r.t,
                "command": {
                    "v": r.command.v,
                    "w": r.command.w,
                    "play": r.command.play,
                    "actions": list(r.command.actions),
                    "target_id": r.command.target_id,
                },
            }
            for r in summary.state_machine_history
        ],
    }
    return results


def main():
    parser = argparse.ArgumentParser(description="Replay Phase 2 pipeline on D2 dataset.")
    parser.add_argument("--simulated", action="store_true", required=True, help="Explicitly use synthetic entries and mock appearance (not T1)")
    parser.add_argument("--threshold", type=float, default=0.45, help="Whitelist cosine threshold")
    parser.add_argument("--out", type=str, default="reports/kouun-rokku/week-04/phase2_replay_summary.json", help="Output JSON path")
    args = parser.parse_args()

    whitelist, entries = generate_d2_replay_entries()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Running Phase 2 replay on %d entries (threshold=%.2f)...", len(entries), args.threshold)
    res = run_phase2_replay(entries, whitelist, cosine_threshold=args.threshold)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2)

    logger.info("Saved replay summary to %s", out_path)
    logger.info("Results:")
    logger.info("  Total entries: %d", res["total_entries"])
    logger.info("  Authorized entries: %d (FA: %d)", res["authorized_count"], res["false_accepts"])
    logger.info("  Intruders queued: %d (FR: %d)", res["intruder_count"], res["false_rejects"])
    logger.info(
        "  Sector accuracy: %.1f %% (%s)",
        res["sector_evaluation"]["accuracy"] * 100.0,
        "PASS" if res["sector_evaluation"]["passed"] else "FAIL",
    )
    logger.info("  State machine active target: %s", res["queue_metrics"]["active_target_id"])


if __name__ == "__main__":
    main()
