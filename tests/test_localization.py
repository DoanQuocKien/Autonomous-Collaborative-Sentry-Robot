"""T0 unit tests for sentry.nav.localization."""
import math
import cv2
import numpy as np
import pytest

from sentry.nav.localization import (
    LocalizationTracker,
    MarkerAnchor,
    RobotPose,
    angle_diff,
    wrap_angle,
)


def test_angle_helpers():
    assert math.isclose(wrap_angle(0.0), 0.0)
    assert math.isclose(wrap_angle(math.pi), -math.pi, abs_tol=1e-7)
    assert math.isclose(wrap_angle(3.0 * math.pi), -math.pi, abs_tol=1e-7)
    assert math.isclose(wrap_angle(-3.0 * math.pi), -math.pi, abs_tol=1e-7)

    # Angle diff
    assert math.isclose(angle_diff(math.pi / 2, 0.0), math.pi / 2)
    assert math.isclose(angle_diff(0.0, math.pi / 2), -math.pi / 2)
    assert math.isclose(angle_diff(math.pi, -math.pi), 0.0, abs_tol=1e-7)


def test_robot_pose_dataclass():
    pose = RobotPose(x=1.5, y=-0.5, theta=math.pi / 2, t=10.0)
    assert pose.x == 1.5
    assert pose.y == -0.5
    assert math.isclose(pose.theta_deg, 90.0)
    assert pose.as_tuple() == (1.5, -0.5, math.pi / 2)

    # Pose2D compatibility aliases for HNHL's gridmap and prescan
    assert pose.x_m == 1.5
    assert pose.y_m == -0.5
    assert pose.yaw_rad == math.pi / 2

    # Keyword construction with x_m, y_m, yaw_rad
    pose_alt = RobotPose(x_m=2.0, y_m=3.0, yaw_rad=-0.5, t=5.0)
    assert pose_alt.x == 2.0 and pose_alt.x_m == 2.0
    assert pose_alt.y == 3.0 and pose_alt.y_m == 3.0
    assert pose_alt.theta == -0.5 and pose_alt.yaw_rad == -0.5

    # Door world coordinate calculation
    # Robot at (0, 0, 0), door straight ahead at 2.0 m (bearing=0) -> (2.0, 0.0)
    origin_pose = RobotPose(x=0.0, y=0.0, theta=0.0)
    door_xy = origin_pose.calculate_door_world_xy(bearing_rad=0.0, distance_m=2.0)
    assert math.isclose(door_xy[0], 2.0, abs_tol=1e-5)
    assert math.isclose(door_xy[1], 0.0, abs_tol=1e-5)

    # Robot at (1, 1), heading pi/2 (pointing +Y), door at bearing -pi/2 (to the right -> +X)
    turned_pose = RobotPose(x=1.0, y=1.0, theta=math.pi / 2)
    door_xy2 = turned_pose.calculate_door_world_xy(bearing_rad=-math.pi / 2, distance_m=2.0)
    assert math.isclose(door_xy2[0], 3.0, abs_tol=1e-5)
    assert math.isclose(door_xy2[1], 1.0, abs_tol=1e-5)


def test_dead_reckoning_straight_and_turn():
    tracker = LocalizationTracker(motion_calib=None, camera_calib=None)
    v_fwd, _ = tracker.wheel_model.body_speeds(1.0, 0.0)
    _, w_turn = tracker.wheel_model.body_speeds(0.0, 1.0)

    # 1 second forward at full speed: v_fwd m forward (~0.430 m)
    tracker.set_pose(0.0, 0.0, 0.0)
    p = tracker.update_odometry(v=1.0, w=0.0, dt=1.0)
    assert math.isclose(p.x, v_fwd, abs_tol=1e-5)
    assert math.isclose(p.y, 0.0, abs_tol=1e-5)
    assert math.isclose(p.theta, 0.0, abs_tol=1e-5)

    # Turn in place: 90 degrees left (pi/2 rad)
    dt_turn = (math.pi / 2.0) / w_turn
    p = tracker.update_odometry(v=0.0, w=1.0, dt=dt_turn)
    assert math.isclose(p.theta, math.pi / 2.0, abs_tol=1e-5)


def test_dead_reckoning_closed_square_path():
    """T0 requirement: closed square path returns to the origin in simulation."""
    tracker = LocalizationTracker(motion_calib=None, camera_calib=None)
    tracker.set_pose(0.0, 0.0, 0.0)

    v_fwd, _ = tracker.wheel_model.body_speeds(0.7, 0.0)
    _, w_turn = tracker.wheel_model.body_speeds(0.0, 0.5)
    side_length = 1.0  # 1 meter
    dt_fwd = side_length / v_fwd
    dt_turn = (math.pi / 2.0) / w_turn

    # Discretize into small 50 Hz steps like sim_robot
    step_dt = 0.02
    for _ in range(4):
        # Drive forward 1 m
        t_accum = 0.0
        while t_accum < dt_fwd:
            dt = min(step_dt, dt_fwd - t_accum)
            tracker.update_odometry(v=0.7, w=0.0, dt=dt)
            t_accum += dt

        # Turn left 90 deg
        t_accum = 0.0
        while t_accum < dt_turn:
            dt = min(step_dt, dt_turn - t_accum)
            tracker.update_odometry(v=0.0, w=0.5, dt=dt)
            t_accum += dt

    # After 4 legs of a square, robot must return to (0, 0, 0)
    assert math.isclose(tracker.pose.x, 0.0, abs_tol=1e-3)
    assert math.isclose(tracker.pose.y, 0.0, abs_tol=1e-3)
    assert math.isclose(tracker.pose.theta, 0.0, abs_tol=1e-3)


def test_aruco_marker_detection_synthetic():
    """T0 requirement: detect marker and calculate pose on rendered/synthetic image."""
    tracker = LocalizationTracker()
    d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    marker_img = cv2.aruco.generateImageMarker(d, 3, 200)

    # Place marker in the middle of a 640x480 white canvas
    frame = np.full((480, 640, 3), 255, dtype=np.uint8)
    y_off, x_off = (480 - 200) // 2, (640 - 200) // 2
    frame[y_off:y_off + 200, x_off:x_off + 200] = cv2.cvtColor(marker_img, cv2.COLOR_GRAY2BGR)

    detections = tracker.detect_markers(frame)
    assert len(detections) == 1
    det = detections[0]
    assert det.marker_id == 3
    assert det.distance_m > 0.05
    # Placed at pixel 320 with optical center cx ~ 285.8 yields bearing ~ -7.4 deg (within 10 deg)
    assert abs(math.degrees(det.bearing_rad)) < 10.0


def test_aruco_pose_correction_fusion():
    tracker = LocalizationTracker()
    tracker.add_anchor(MarkerAnchor(marker_id=3, x=1.5, y=0.0, yaw_rad=math.pi))

    d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    marker_img = cv2.aruco.generateImageMarker(d, 3, 160)
    frame = np.full((480, 640, 3), 255, dtype=np.uint8)
    y_off, x_off = (480 - 160) // 2, (640 - 160) // 2
    frame[y_off:y_off + 160, x_off:x_off + 160] = cv2.cvtColor(marker_img, cv2.COLOR_GRAY2BGR)

    # Initial pose has an offset
    tracker.set_pose(0.0, 0.0, 0.0)
    pose, detections = tracker.update_with_markers(frame, alpha=0.5)

    assert len(detections) == 1
    assert tracker.corrections_count == 1
    # Pose should have updated towards the marker anchor observation
    assert tracker.pose.x > 0.0


def test_marker_size_loaded_from_config():
    """Review point 1: Marker size defaults to config.toml [calibration] aruco_marker_m (0.15 m)."""
    tracker = LocalizationTracker()
    assert math.isclose(tracker.marker_size_m, 0.15, abs_tol=1e-5)

    # Explicit override is preserved
    tracker_custom = LocalizationTracker(marker_size_m=0.10)
    assert math.isclose(tracker_custom.marker_size_m, 0.10, abs_tol=1e-5)


def test_dead_reckoning_motor_deadzone():
    """Review point 4: Motors stop when command after speed cap is below min_pwm."""
    tracker = LocalizationTracker(
        motion_calib={"min_pwm": 0.12, "max_speed": 0.3},
        camera_calib=None,
    )
    tracker.set_pose(0.0, 0.0, 0.0)

    # At speed cap 0.3, v = 0.3 -> 0.3 * 0.3 = 0.09 < min_pwm 0.12 -> zero motion
    p = tracker.update_odometry(v=0.3, w=0.0, dt=1.0)
    assert math.isclose(p.x, 0.0, abs_tol=1e-6)
    assert math.isclose(p.y, 0.0, abs_tol=1e-6)

    # v = 0.5 -> 0.5 * 0.3 = 0.15 >= min_pwm 0.12 -> moves forward
    p = tracker.update_odometry(v=0.5, w=0.0, dt=1.0)
    assert p.x > 0.0

    # Angular deadzone test
    tracker.set_pose(0.0, 0.0, 0.0)
    p = tracker.update_odometry(v=0.0, w=0.3, dt=0.1)
    assert math.isclose(p.theta, 0.0, abs_tol=1e-6)

    p = tracker.update_odometry(v=0.0, w=0.6, dt=0.1)
    assert p.theta > 0.0


def test_dead_zone_is_per_wheel_so_steering_while_driving_is_kept():
    """Review of PR #37: the robot applies the dead zone to each wheel's final value (common/mixing.py), not to v and w separately."""
    def step(v, w, dt=0.01):
        tracker = LocalizationTracker(camera_calib=None, config_path=None)
        tracker.set_pose(0.0, 0.0, 0.0)
        p = tracker.update_odometry(v=v, w=w, dt=dt)
        return math.hypot(p.x, p.y) / dt, p.theta / dt

    v_mps, w_radps = step(0.6, 0.065)             # steering while driving: both wheels above the dead zone, the turn must stay
    assert abs(v_mps - 0.2325) < 0.01 and w_radps > 0.3
    v_mps, w_radps = step(0.5, 0.15)              # left wheel 0.35 * 0.3 = 0.105 < 0.12 stops: an arc, faster turn than the command alone
    assert 0.0 < v_mps < step(0.5, 0.0)[0] and w_radps > 1.5
    assert step(0.0, 0.3) == (0.0, 0.0)           # wheels at 0.09: stands still
    assert step(0.3, 0.0) == (0.0, 0.0)
    v_mps, w_radps = step(0.0, 0.5)               # wheels at 0.15: spins
    assert v_mps == 0.0 and abs(w_radps - 2.62) / 2.62 < 0.08


def test_localization_uses_wheel_model_from_motion_json():
    """Issue #41: LocalizationTracker uses WheelModel (k=1.64, m0=0.038, track=0.137) from calib/motion.json."""
    tracker = LocalizationTracker(camera_calib=None, config_path=None)
    assert math.isclose(tracker.wheel_model.k, 1.64)
    assert math.isclose(tracker.wheel_model.m0, 0.038)
    assert math.isclose(tracker.wheel_model.track, 0.137)
    assert math.isclose(tracker.min_pwm, 0.12)
    assert math.isclose(tracker.max_speed, 0.3)

    measured_speeds = {0.4: 0.139, 0.5: 0.185, 0.6: 0.238, 0.7: 0.276, 0.85: 0.357, 1.0: 0.435}
    for v_cmd, s_meas in measured_speeds.items():
        tracker.set_pose(0.0, 0.0, 0.0)
        p = tracker.update_odometry(v=v_cmd, w=0.0, dt=1.0)
        assert abs(p.x - s_meas) / s_meas < 0.06, (v_cmd, p.x, s_meas)
        assert math.isclose(p.y, 0.0, abs_tol=1e-7)
        assert math.isclose(p.theta, 0.0, abs_tol=1e-7)

    measured_turns = {0.4: 1.98, 0.5: 2.62, 1.0: 6.27}
    for w_cmd, r_meas in measured_turns.items():
        tracker.set_pose(0.0, 0.0, 0.0)
        p = tracker.update_odometry(v=0.0, w=w_cmd, dt=0.2)
        om = p.theta / 0.2
        assert abs(om - r_meas) / r_meas < 0.08, (w_cmd, om, r_meas)

    # Online scale knob adjusts integrated distance
    tracker.scale = 0.8
    tracker.set_pose(0.0, 0.0, 0.0)
    p_scaled = tracker.update_odometry(v=0.7, w=0.0, dt=1.0)
    expected_unscaled = (1.64 * (0.7 * 0.3 - 0.038))
    assert math.isclose(p_scaled.x, 0.8 * expected_unscaled, abs_tol=1e-6)


def test_marker_distance_gating_and_alpha_decay():
    """Review point 2: Reject markers beyond max_marker_distance_m (1.5 m) to suppress noise."""
    tracker = LocalizationTracker(max_marker_distance_m=0.20)
    tracker.add_anchor(MarkerAnchor(marker_id=3, x=1.5, y=0.0, yaw_rad=math.pi))

    d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    marker_img = cv2.aruco.generateImageMarker(d, 3, 100)
    frame = np.full((480, 640, 3), 255, dtype=np.uint8)
    y_off, x_off = (480 - 100) // 2, (640 - 100) // 2
    frame[y_off:y_off + 100, x_off:x_off + 100] = cv2.cvtColor(marker_img, cv2.COLOR_GRAY2BGR)

    # Distance of small 100px marker on 640x480 is > 0.20 m
    dets = tracker.detect_markers(frame)
    assert len(dets) == 1
    assert dets[0].distance_m > 0.20

    # With max_marker_distance_m = 0.20, detection should be rejected in update_with_markers
    tracker.set_pose(0.0, 0.0, 0.0)
    pose, _ = tracker.update_with_markers(frame, alpha=0.5)
    assert tracker.corrections_count == 0
    assert math.isclose(pose.x, 0.0, abs_tol=1e-6)
