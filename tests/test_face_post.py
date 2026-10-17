import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "jetson"))
pytest.importorskip("cv2")
import face_post  # noqa: E402


def _fake_outputs(size, cell, stride, score, dist, kp_off):
    """SCRFD-like outputs with exactly one confident anchor (first of the two) at grid cell `cell` of the given stride."""
    outs = []
    for st in face_post.STRIDES:
        n = 2 * (size // st) ** 2
        s, b, k = np.zeros((n, 1), np.float32), np.zeros((n, 4), np.float32), np.zeros((n, 10), np.float32)
        if st == stride:
            i = 2 * (cell[1] * (size // st) + cell[0])
            s[i, 0], b[i], k[i] = score, dist, kp_off
        outs += [s, b, k]
    return outs[::-1]                      # TensorRT order differs from the ONNX order: the decoder must not depend on it


def test_decode_places_the_box_and_landmarks_from_the_anchor_centre():
    # stride 16, cell (x=5, y=3) -> centre (80, 48); distances l,t,r,b = 2,3,4,5 cells of 16 px; kps offsets (+1,+1) cells each
    outs = _fake_outputs(320, (5, 3), 16, 0.9, [2, 3, 4, 5], [1] * 10)
    boxes, scores, kps = face_post.decode_scrfd(outs, scale=0.5, size=320)
    assert np.allclose(boxes[0], [(80 - 32) / 0.5, (48 - 48) / 0.5, (80 + 64) / 0.5, (48 + 80) / 0.5])
    assert np.allclose(kps[0, 0], [(80 + 16) / 0.5, (48 + 16) / 0.5]) and scores[0] == pytest.approx(0.9)
    assert face_post.decode_scrfd(outs, 0.5, thr=0.95)[0].shape == (0, 4)


def test_align_recovers_the_template_from_a_shifted_and_scaled_face():
    import cv2
    frame = np.zeros((300, 400, 3), np.uint8)
    kps = face_post.ARCFACE_112 * 1.5 + np.array([120, 60], np.float32)     # the same landmarks, 1.5x larger, moved
    for x, y in kps:
        cv2.circle(frame, (int(round(x)), int(round(y))), 4, (255, 255, 255), -1)
    crop = face_post.align(frame, kps)
    assert crop.shape == (112, 112, 3)
    for x, y in face_post.ARCFACE_112:                                         # the dots must land on the template points
        assert crop[int(round(y)), int(round(x))].max() > 120
    assert face_post.embed_blob(crop).shape == (1, 3, 112, 112)
