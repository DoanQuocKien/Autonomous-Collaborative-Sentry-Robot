"""T0 unit tests for vendored Python 3.6 ByteTrack tracker (third_party/bytetrack).

Verifies:
1. Python 3.6 syntax compatibility across all modules via ast.parse(..., feature_version=(3, 6)).
2. Absence of sentry.* or dataclasses imports inside third_party/bytetrack.
3. Pure numpy and scipy linear assignment without compiled C++ lap requirement.
4. Drop-in parity with Ultralytics ByteTrack on multi-track scenarios (ID agreement >= 95%).
"""
import ast
import glob
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from sentry.config import load
from sentry.perception.tracker import ByteTrackBackend, VendoredByteTrackBackend
from third_party.bytetrack import (
    BaseTrack,
    BYTETracker,
    KalmanFilter,
    STrack,
    TrackState,
)
from third_party.bytetrack.matching import (
    fuse_score,
    iou_distance,
    ious,
    linear_assignment,
)

ROOT = Path(__file__).resolve().parents[1]


def test_bytetrack_files_are_python36_compatible_and_self_contained():
    bytetrack_dir = ROOT / "third_party" / "bytetrack"
    py_files = list(bytetrack_dir.glob("*.py"))
    assert len(py_files) >= 5, "Expected at least 5 Python files in third_party/bytetrack"

    for path in py_files:
        src = path.read_text(encoding="utf-8")
        # Validate Python 3.6 AST
        tree = ast.parse(src, filename=str(path), feature_version=(3, 6))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("sentry"), f"{path.name} must not import sentry"
                    assert alias.name not in ("dataclasses",), f"{path.name} must not import {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                assert not mod.startswith("sentry"), f"{path.name} must not import from sentry"
                assert mod not in ("dataclasses", "__future__"), f"{path.name} must not import from {mod}"


def test_linear_assignment_pure_scipy():
    cost = np.array([
        [0.1, 0.9, 0.9],
        [0.8, 0.2, 0.9],
        [0.9, 0.8, 0.15],
    ])
    matches, u_a, u_b = linear_assignment(cost, thresh=0.5)
    assert len(matches) == 3
    assert np.array_equal(matches, [[0, 0], [1, 1], [2, 2]])
    assert len(u_a) == 0 and len(u_b) == 0

    # High cost above threshold leads to unmatched
    cost[2, 2] = 0.8
    matches, u_a, u_b = linear_assignment(cost, thresh=0.5)
    assert len(matches) == 2
    assert 2 in u_a and 2 in u_b


def test_kalman_filter_step_and_multi_predict():
    kf = KalmanFilter()
    measurement = np.array([50.0, 50.0, 0.5, 100.0])  # x, y, a, h
    mean, cov = kf.initiate(measurement)
    assert mean.shape == (8,)
    assert cov.shape == (8, 8)

    # Predict
    p_mean, p_cov = kf.predict(mean, cov)
    assert p_mean.shape == (8,)

    # Update with shifted measurement
    new_meas = np.array([52.0, 51.0, 0.5, 100.0])
    u_mean, u_cov = kf.update(p_mean, p_cov, new_meas)
    assert u_mean[0] > 50.0 and u_mean[1] > 50.0


def test_vendored_bytetrack_backend_contract_and_low_confidence_association():
    cfg = load()["tracking"]
    backend = VendoredByteTrackBackend(cfg)

    # Frame 1: high confidence detection
    first = backend.update([[10.0, 10.0, 40.0, 80.0, 0.9, 0]], (100, 100))
    assert len(first) == 1
    track_id = int(first[0][4])
    assert track_id >= 1

    # Frame 2: low confidence detection (0.15), must associate with same track ID
    low = backend.update([[11.0, 10.0, 41.0, 80.0, 0.15, 0]], (100, 100))
    assert len(low) == 1
    assert int(low[0][4]) == track_id

    # Frame 3: target occluded (empty detections), must NOT emit lost prediction
    empty = backend.update([], (100, 100))
    assert len(empty) == 0

    # Frame 4: target reappears, must re-acquire same track ID
    back = backend.update([[12.0, 10.0, 42.0, 80.0, 0.9, 0]], (100, 100))
    assert len(back) == 1
    assert int(back[0][4]) == track_id
    BaseTrack.reset_counter()


def test_parity_between_vendored_and_ultralytics_bytetrack():
    """Verify >= 95% ID agreement between vendored ByteTrack and Ultralytics ByteTrack."""
    from ultralytics.trackers.byte_tracker import STrack as USTRack
    from third_party.bytetrack import BaseTrack as VBaseTrack
    USTRack.reset_id()
    VBaseTrack.reset_counter()

    cfg = load()["tracking"]
    backend_ultralytics = ByteTrackBackend(cfg)
    backend_vendored = VendoredByteTrackBackend(cfg)

    # Generate synthetic 2-person crossing scenario over 30 frames
    # Person A: starts at x=50, moves East at 2 px/frame
    # Person B: starts at x=200, moves West at 2 px/frame
    total_detections = 0
    agreed_detections = 0

    for f in range(30):
        xa = 50.0 + f * 2.0
        xb = 200.0 - f * 2.0

        # Alternate confidences to exercise high/low association
        conf_a = 0.90 if f % 4 != 2 else 0.18
        conf_b = 0.88 if f % 5 != 3 else 0.20

        # At frame 15, simulate temporary occlusion of Person B
        rows = []
        rows.append([xa, 40.0, xa + 30.0, 100.0, conf_a, 0])
        if f != 15:
            rows.append([xb, 40.0, xb + 30.0, 100.0, conf_b, 0])

        res_u = backend_ultralytics.update(rows, (300, 300))
        res_v = backend_vendored.update(rows, (300, 300))

        # Compare outputs: match detections by IoU > 0.7 and compare track IDs
        if len(res_u) > 0 and len(res_v) > 0:
            boxes_u = res_u[:, :4]
            boxes_v = res_v[:, :4]
            iou_mat = ious(boxes_u, boxes_v)

            for i in range(len(res_u)):
                j = np.argmax(iou_mat[i])
                if iou_mat[i, j] >= 0.7:
                    total_detections += 1
                    id_u = int(res_u[i, 4])
                    id_v = int(res_v[j, 4])
                    if id_u == id_v:
                        agreed_detections += 1

    agreement_rate = (agreed_detections / total_detections) if total_detections > 0 else 0.0
    assert agreement_rate >= 0.95, f"ID agreement {agreement_rate * 100:.1f}% below 95% threshold!"
