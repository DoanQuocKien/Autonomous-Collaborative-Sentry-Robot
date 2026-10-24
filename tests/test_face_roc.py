"""Test for Face Verification ROC evaluation on D2 leave-one-out data (Week 3, HNHL)."""
import json
from pathlib import Path
import pytest

from tools.evaluate_face_roc import evaluate_roc, generate_d2_eval_vectors


def test_d2_roc_evaluation_meets_spec_thresholds():
    dataset, negatives = generate_d2_eval_vectors(seed=42)
    results = evaluate_roc(dataset, negatives)

    assert results["meets_target"] is True
    op = results["operating_point"]
    assert op["threshold"] == pytest.approx(0.45, abs=0.02)
    assert op["tar"] >= 0.95
    assert op["far"] <= 0.01
