"""Unit test for edge conversion parity contracts (Week 3, HNHL)."""
import json
from pathlib import Path
import numpy as np
import pytest

from tools.check_edge_parity import compute_cosine, compute_iou, run_parity_evaluation


def test_compute_cosine_and_iou():
    v1 = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    v2 = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    v3 = np.array([0.0, 1.0, 0.0], dtype=np.float32)

    assert compute_cosine(v1, v2) == pytest.approx(1.0)
    assert compute_cosine(v1, v3) == pytest.approx(0.0)

    # Identical boxes
    box1 = (10, 10, 50, 50)
    box2 = (10, 10, 50, 50)
    assert compute_iou(box1, box2) == pytest.approx(1.0)

    # Half overlap
    box3 = (10, 10, 30, 50)
    assert 0.4 < compute_iou(box1, box3) < 0.6


def test_parity_evaluation_meets_thresholds(tmp_path):
    out = tmp_path / "parity.json"
    res = run_parity_evaluation(out)

    assert res["all_passed"] is True
    for model_name, info in res["models"].items():
        assert info["cosine_min"] >= res["target_cosine_threshold"]
        if "box_iou_ge_90_fraction" in info:
            assert info["box_iou_ge_90_fraction"] >= 0.95
