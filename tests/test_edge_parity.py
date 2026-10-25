"""Unit test for edge conversion parity metrics functions (Week 3, HNHL)."""
from pathlib import Path
import numpy as np
import pytest

from tools.check_edge_parity import (
    collect_parity_images,
    compute_cosine,
    compute_iou,
    write_parity_harness_spec,
)


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


def test_parity_harness_spec_generation(tmp_path):
    spec = write_parity_harness_spec(tmp_path / "spec.json")
    assert spec["status"] == "HARNESS_READY_PENDING_ENGINE_BUILD"
    assert spec["evaluated_on_real_engines"] is False
    assert spec["target_thresholds"]["cosine_similarity"] == 0.999
