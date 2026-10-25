"""Test for Face Verification ROC evaluation pipeline (Week 3, HNHL)."""
from pathlib import Path
import pytest

from tools.evaluate_face_roc import evaluate_roc, generate_simulated_eval_vectors


def test_d2_roc_evaluation_pipeline_logic():
    dataset, negatives = generate_simulated_eval_vectors(seed=42)
    results = evaluate_roc(dataset, negatives)

    assert results["status"] == "SIMULATION_PROTOTYPE"
    assert results["t1_accepted"] is False
    assert len(results["roc_curve"]) > 10
    op = results["operating_point"]
    assert op["threshold"] == pytest.approx(0.45, abs=0.02)
    assert 0.0 <= op["far"] <= 1.0
    assert 0.0 <= op["tar"] <= 1.0
