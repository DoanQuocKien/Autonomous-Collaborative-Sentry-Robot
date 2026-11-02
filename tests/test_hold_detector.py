"""T0 unit tests for sentry/nav/hold_detector.py (Week 5, kouun-rokku).

Verifies:
1. Target ground position conversion from robot frame to world frame.
2. Dwell time: target ground speed < 0.1 m/s for > 2.0 s triggers TARGET_STATIONARY.
3. Hysteresis: exit HOLD requires target speed > 0.2 m/s; stays in HOLD in [0.1, 0.2] m/s band.
4. Core invariant: "Robot yawing alone never triggers hold":
   - When target is moving in world, robot rotation does not cause false stationary triggers.
   - When target is stationary in world, robot rotation does not cause false moving triggers.
5. Robustness to vision noise via linear-regression window filter.
"""
import math
import numpy as np
import pytest

from sentry.nav.hold_detector import (
    HoldConfig,
    HoldDetector,
    HoldState,
    local_to_world_coords,
)
from sentry.nav.localization import RobotPose


def test_local_to_world_coords_rotation_and_translation():
    # Robot at (1.0, 2.0) facing North (pi/2)
    robot_pose = (1.0, 2.0, math.pi / 2.0)
    # Target 2.0 m directly ahead in robot frame (forward=2.0, left=0.0)
    wx, wy = local_to_world_coords(robot_pose, 2.0, 0.0)
    assert wx == pytest.approx(1.0, abs=1e-5)
    assert wy == pytest.approx(4.0, abs=1e-5)

    # Target 1.0 m to the left in robot frame (forward=0.0, left=1.0)
    wx, wy = local_to_world_coords(robot_pose, 0.0, 1.0)
    assert wx == pytest.approx(0.0, abs=1e-5)
    assert wy == pytest.approx(2.0, abs=1e-5)

    # RobotPose object compatibility
    pose_obj = RobotPose(x=3.0, y=1.0, theta=0.0)
    wx, wy = local_to_world_coords(pose_obj, 1.5, 0.5)
    assert wx == pytest.approx(4.5, abs=1e-5)
    assert wy == pytest.approx(1.5, abs=1e-5)


def test_invalid_coordinates_and_timestamps_raise_value_error():
    detector = HoldDetector()
    with pytest.raises(ValueError):
        local_to_world_coords((0, 0, 0), float("nan"), 0.0)
    with pytest.raises(ValueError):
        detector.update_world(float("nan"), 0.0, 0.0)

    detector.update_world(1.0, 0.0, 0.0)
    # Monotonic timestamp check
    with pytest.raises(ValueError, match="strictly greater"):
        detector.update_world(1.0, 0.1, 0.0)
    with pytest.raises(ValueError, match="strictly greater"):
        detector.update_world(0.5, 0.1, 0.0)


def test_dwell_time_triggers_target_stationary_after_two_seconds():
    # 1. Target stationary from start: triggers exactly after 2.0 s dwell
    detector = HoldDetector(HoldConfig(speed_threshold_mps=0.1, dwell_time_s=2.0, window_s=0.5))
    t = 0.0
    dt = 0.1
    events = []
    while t < 1.95:
        t += dt
        st = detector.update_world(t, wx=1.0, wy=0.0)
        assert not detector.in_hold
        assert st.event is None

    # Step across 2.0 s boundary
    t += dt
    st = detector.update_world(t, wx=1.0, wy=0.0)
    assert detector.in_hold
    assert st.event == "TARGET_STATIONARY"

    # 2. Target walking, then stopping: transitions to stationary and triggers 2.0 s later
    detector.reset()
    t = 0.0
    while t < 1.0:
        t += dt
        detector.update_world(t, wx=0.5 * t, wy=0.0)
        assert not detector.in_hold

    # Target stops at wx=0.5 m; filter clears walking points within window_s=0.5 s
    # and dwell triggers after 2.0 s of continuous low speed
    stationary_t = None
    triggered = False
    while t < 4.0:
        t += dt
        st = detector.update_world(t, wx=0.5, wy=0.0)
        if st.speed_mps < 0.1 and stationary_t is None:
            stationary_t = t
        if st.event == "TARGET_STATIONARY":
            triggered = True
            assert (t - stationary_t) == pytest.approx(2.0, abs=0.15)
            break
    assert triggered and detector.in_hold


def test_hysteresis_between_enter_and_exit_thresholds():
    detector = HoldDetector(HoldConfig(speed_threshold_mps=0.1, dwell_time_s=1.0, exit_speed_mps=0.2))
    t = 0.0
    dt = 0.05

    # Target stationary at x=0 for 1.2 s -> enters HOLD
    while t < 1.2:
        t += dt
        st = detector.update_world(t, wx=0.0, wy=0.0)
    assert detector.in_hold

    # Target creeps slowly at 0.14 m/s (above 0.1 m/s, but below 0.2 m/s exit threshold)
    # Must remain in HOLD without flickering
    x = 0.0
    for _ in range(20):
        t += dt
        x += 0.14 * dt
        st = detector.update_world(t, wx=x, wy=0.0)
        assert detector.in_hold, "Target creeping at 0.14 m/s must not exit HOLD (hysteresis band)"
        assert st.event is None

    # Target speeds up to 0.35 m/s (> 0.2 m/s exit threshold) -> exits HOLD
    exit_events = []
    for _ in range(20):
        t += dt
        x += 0.35 * dt
        st = detector.update_world(t, wx=x, wy=0.0)
        if st.event:
            exit_events.append(st.event)

    assert not detector.in_hold
    assert "TARGET_MOVING" in exit_events


def test_robot_yawing_alone_never_triggers_hold_when_target_moves():
    """Core acceptance test: robot yawing while target moves in world NEVER triggers HOLD."""
    detector = HoldDetector(HoldConfig(speed_threshold_mps=0.1, dwell_time_s=1.0))
    t = 0.0
    dt = 0.05
    target_speed = 0.45  # Target walking at 0.45 m/s East in world
    robot_omega = 1.2    # Robot actively spinning in place at 1.2 rad/s

    # Run for 4.0 seconds (well past the 1.0 s dwell threshold)
    for _ in range(80):
        t += dt
        # Target true world position
        target_wx = target_speed * t
        target_wy = 1.0

        # Robot spinning in place at world origin (0, 0)
        robot_theta = (robot_omega * t) % (2.0 * math.pi) - math.pi
        robot_pose = (0.0, 0.0, robot_theta)

        # In robot frame, target coordinates appear to rotate rapidly:
        # p_local = R(-theta) * (p_world - p_robot)
        cos_th = math.cos(robot_theta)
        sin_th = math.sin(robot_theta)
        local_fwd = target_wx * cos_th + target_wy * sin_th
        local_left = -target_wx * sin_th + target_wy * cos_th

        # Feed local coordinates + robot pose to detector
        st = detector.update(t, robot_pose, (local_fwd, local_left))

        # World speed must reflect ~0.45 m/s, NEVER < 0.1 m/s
        assert not detector.in_hold, f"Robot yawing alone falsely triggered HOLD at t={t}!"
        assert st.event != "TARGET_STATIONARY"


def test_robot_yawing_alone_does_not_break_hold_when_target_is_stationary():
    """When target is stationary in world and robot spins/re-centers, HOLD triggers and stays."""
    detector = HoldDetector(HoldConfig(speed_threshold_mps=0.1, dwell_time_s=1.0, exit_speed_mps=0.2))
    t = 0.0
    dt = 0.05
    target_wx = 1.5
    target_wy = 0.5
    robot_omega = 0.8  # Robot spinning at 0.8 rad/s

    # Run for 3.0 seconds
    for _ in range(60):
        t += dt
        robot_theta = (robot_omega * t) % (2.0 * math.pi) - math.pi
        robot_pose = (0.0, 0.0, robot_theta)

        cos_th = math.cos(robot_theta)
        sin_th = math.sin(robot_theta)
        local_fwd = target_wx * cos_th + target_wy * sin_th
        local_left = -target_wx * sin_th + target_wy * cos_th

        st = detector.update(t, robot_pose, (local_fwd, local_left))

    # After 3.0 s of target stationary, robot must be firmly in HOLD
    assert detector.in_hold
    assert st.speed_mps < 0.05, f"Expected near zero speed, got {st.speed_mps}"


def test_linear_regression_filters_detector_noise():
    """Window linear regression filters high-frequency 2 cm detector jitter."""
    detector = HoldDetector(HoldConfig(speed_threshold_mps=0.1, dwell_time_s=1.0, window_s=0.5))
    rng = np.random.default_rng(seed=42)
    t = 0.0
    dt = 0.05
    wx_base = 2.0
    wy_base = 1.0

    for _ in range(40):
        t += dt
        # Add +/- 2.5 cm random vision jitter to stationary world position
        noisy_wx = wx_base + rng.normal(0, 0.02)
        noisy_wy = wy_base + rng.normal(0, 0.02)
        st = detector.update_world(t, noisy_wx, noisy_wy)

    # Filtered speed should remain well below 0.1 m/s despite single-frame jumps
    assert st.speed_mps < 0.1
    assert detector.in_hold


def test_gap_in_observations_resets_history_and_releases_hold():
    """Target lost across gap > 1.0 s releases HOLD state."""
    detector = HoldDetector(HoldConfig(dwell_time_s=1.0, max_observation_gap_s=1.0, min_samples=5, min_window_span_s=0.2))
    t = 0.0
    for _ in range(30):
        t += 0.05
        detector.update_world(t, 0.0, 0.0)
    assert detector.in_hold, "Must be in HOLD after 1.5 s stationary"

    # Gap of 2.0 s: target lost from view
    t += 2.0
    st = detector.update_world(t, 0.0, 0.0)
    assert not detector.in_hold, "Gap > 1.0 s must release HOLD"
    assert st.dwell_progress_s == 0.0


def test_minimum_samples_and_span_suppress_cluster_jitter():
    """Two samples 33 ms apart with 1 cm jitter must NOT produce velocity spikes before min span."""
    detector = HoldDetector(HoldConfig(min_samples=5, min_window_span_s=0.2))
    # Frame 1 and 2 separated by 33 ms with 1 cm jitter
    detector.update_world(1.000, 0.00, 0.0)
    st = detector.update_world(1.033, 0.01, 0.0)
    # Must return 0.0 speed because n < 5 and span < 0.2 s
    assert st.speed_mps == 0.0
