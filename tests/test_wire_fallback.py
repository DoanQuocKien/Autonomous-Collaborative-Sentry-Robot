"""Tests for geometric wire fallback (Week 3, HNHL)."""
import math
import cv2
import numpy as np
import pytest

from sentry.perception.camera import CameraGeometry
from sentry.perception.wire_fallback import WireCandidate, WireGeometricFallback


def _synthetic_floor_with_line(line_color=20, bg_color=200, length=80):
    img = np.full((480, 640, 3), bg_color, dtype=np.uint8)
    # Draw a line in the lower half (floor region)
    x1, y1 = 200, 350
    x2, y2 = 200 + length, 350 + int(length * 0.2)
    cv2.line(img, (x1, y1), (x2, y2), (line_color, line_color, line_color), thickness=2)
    return img, (x1, y1, x2, y2)


def test_detect_dark_wire_on_light_floor():
    detector = WireGeometricFallback(min_length_px=40.0, contrast_threshold=30.0)
    img, (x1, y1, x2, y2) = _synthetic_floor_with_line(line_color=10, bg_color=220, length=100)

    candidates = detector.detect(img)
    assert len(candidates) >= 1

    matched = any(c.polarity == "dark" and c.length_px >= 40.0 for c in candidates)
    assert matched


def test_detect_bright_wire_on_dark_floor():
    detector = WireGeometricFallback(min_length_px=40.0, contrast_threshold=30.0)
    img, (x1, y1, x2, y2) = _synthetic_floor_with_line(line_color=240, bg_color=30, length=90)

    candidates = detector.detect(img)
    assert len(candidates) >= 1

    matched = any(c.polarity == "bright" and c.length_px >= 40.0 for c in candidates)
    assert matched


def test_rejects_sub_threshold_contrast():
    # Contrast is only 5 intensity levels, threshold is 20
    detector = WireGeometricFallback(min_length_px=40.0, contrast_threshold=20.0)
    img, _ = _synthetic_floor_with_line(line_color=200, bg_color=205, length=80)

    candidates = detector.detect(img)
    assert len(candidates) == 0


def test_detect_with_camera_geometry():
    cam = CameraGeometry.from_files("calib/camera.json", "calib/camera_pose_classroom_locked.json")
    detector = WireGeometricFallback(camera=cam, min_length_px=40.0, contrast_threshold=30.0, keep_clear_m=1.0)
    # Row 360 is on the floor ~ 0.5-0.7m
    img = np.full((480, 640, 3), 200, dtype=np.uint8)
    cv2.line(img, (250, 380), (390, 380), (10, 10, 10), thickness=2)

    candidates = detector.detect(img)
    assert len(candidates) >= 1
    c = candidates[0]
    assert c.ground_range_m is not None
    assert 0.2 < c.ground_range_m < 2.0
    assert c.bearing_rad is not None
    assert c.keep_clear is True


def test_rejects_invalid_input_shape():
    detector = WireGeometricFallback()
    with pytest.raises(ValueError):
        detector.detect(np.zeros((480, 640), dtype=np.uint8))
