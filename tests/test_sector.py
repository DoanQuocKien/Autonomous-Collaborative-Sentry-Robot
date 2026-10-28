"""Unit tests for sector classification and SectorTracker (Week 4, kouun-rokku)."""
from sentry.perception.sector import (
    DepartureSector,
    SectorConfig,
    SectorTracker,
    classify_sector,
    normalize_sector,
    sector_code,
)


def test_normalize_sector_and_codes():
    assert normalize_sector("l") == DepartureSector.LEFT.value
    assert normalize_sector("LEFT") == DepartureSector.LEFT.value
    assert normalize_sector("c") == DepartureSector.CENTER.value
    assert normalize_sector("centre") == DepartureSector.CENTER.value
    assert normalize_sector("r") == DepartureSector.RIGHT.value
    assert normalize_sector("Right") == DepartureSector.RIGHT.value
    assert normalize_sector("anything_else") == DepartureSector.UNKNOWN.value
    assert normalize_sector(None) == DepartureSector.UNKNOWN.value

    assert sector_code("left") == "L"
    assert sector_code("center") == "C"
    assert sector_code("right") == "R"
    assert sector_code("unknown") == "U"


def test_classify_sector_left_drift():
    # Entrant moving from center (x=320) to left (x=160) over 1.5 s
    observations = [
        (0.0, (270.0, 100.0, 370.0, 300.0)),  # x_center = 320
        (0.5, (220.0, 100.0, 320.0, 300.0)),  # x_center = 270
        (1.0, (170.0, 100.0, 270.0, 300.0)),  # x_center = 220
        (1.5, (110.0, 100.0, 210.0, 300.0)),  # x_center = 160
    ]
    sec, drift = classify_sector(observations, frame_width=640.0)
    assert sec == DepartureSector.LEFT.value
    assert drift < -0.08


def test_classify_sector_right_drift():
    # Entrant moving from center (x=320) to right (x=480) over 1.5 s
    observations = [
        (0.0, (270.0, 100.0, 370.0, 300.0)),  # x_center = 320
        (0.5, (320.0, 100.0, 420.0, 300.0)),  # x_center = 370
        (1.0, (370.0, 100.0, 470.0, 300.0)),  # x_center = 420
        (1.5, (430.0, 100.0, 530.0, 300.0)),  # x_center = 480
    ]
    sec, drift = classify_sector(observations, frame_width=640.0)
    assert sec == DepartureSector.RIGHT.value
    assert drift > 0.08


def test_classify_sector_center_straight():
    # Entrant walking straight into room with small detector jitter
    observations = [
        (0.0, (270.0, 100.0, 370.0, 300.0)),  # x_center = 320
        (0.5, (272.0, 120.0, 372.0, 320.0)),  # x_center = 322
        (1.0, (268.0, 150.0, 368.0, 350.0)),  # x_center = 318
        (1.5, (271.0, 180.0, 371.0, 380.0)),  # x_center = 321
        (2.0, (270.0, 210.0, 370.0, 410.0)),  # x_center = 320
    ]
    sec, drift = classify_sector(observations, frame_width=640.0)
    assert sec == DepartureSector.CENTER.value
    assert abs(drift) <= 0.08


def test_classify_sector_normalized_coordinates():
    # Inputs already in [0.0, 1.0]
    observations = [
        (0.0, 0.50),
        (0.5, 0.40),
        (1.0, 0.30),
        (1.5, 0.20),
    ]
    sec, drift = classify_sector(observations)
    assert sec == DepartureSector.LEFT.value
    assert drift < -0.08


def test_classify_sector_insufficient_points():
    assert classify_sector([]) == (DepartureSector.UNKNOWN.value, 0.0)
    assert classify_sector([(0.0, (100, 100, 200, 200))]) == (DepartureSector.UNKNOWN.value, 0.0)


def test_sector_tracker_streaming():
    cfg = SectorConfig(window_s=2.0, drift_threshold=0.08, min_points=3)
    tracker = SectorTracker(config=cfg, frame_width=640.0)

    assert tracker.sector == DepartureSector.UNKNOWN.value
    assert not tracker.is_finalized

    # Frame 1: t=0.0
    tracker.update((270.0, 100.0, 370.0, 300.0), t=0.0)
    assert not tracker.is_finalized

    # Frame 2: t=0.5
    tracker.update((330.0, 100.0, 430.0, 300.0), t=0.5)

    # Frame 3: t=1.0
    tracker.update((390.0, 100.0, 490.0, 300.0), t=1.0)
    assert tracker.sector == DepartureSector.RIGHT.value
    assert tracker.code == "R"

    # Frame 4: t=2.0 (reaches window_s)
    tracker.update((450.0, 100.0, 550.0, 300.0), t=2.0)
    assert tracker.is_finalized
    assert tracker.sector == DepartureSector.RIGHT.value
    assert tracker.drift > 0.08

    # Reset
    tracker.reset()
    assert tracker.sector == DepartureSector.UNKNOWN.value
    assert not tracker.is_finalized


def test_sector_tracker_normalized_coordinates():
    # Verify that normalized coordinates in [0.0, 1.0] are handled properly by default SectorTracker
    cfg = SectorConfig(window_s=2.0, drift_threshold=0.08, min_points=3)
    tracker = SectorTracker(config=cfg, frame_width=640.0)

    # Entrant moving to the right in normalized bbox space: x_center moves 0.2 -> 0.8
    tracker.update((0.1, 0.2, 0.3, 0.8), t=0.0)
    tracker.update((0.4, 0.2, 0.6, 0.8), t=1.0)
    tracker.update((0.7, 0.2, 0.9, 0.8), t=2.0)

    assert tracker.is_finalized
    assert tracker.sector == DepartureSector.RIGHT.value
    assert tracker.code == "R"
    assert tracker.drift > 0.08
