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
    tracker.v_gain = 0.5
    tracker.w_gain = 2.0
    tracker.drift_rad_per_m = 0.0
    tracker.apply_drift_compensation = False

    # 1 second forward at full speed: 0.5 m forward
    tracker.set_pose(0.0, 0.0, 0.0)
    p = tracker.update_odometry(v=1.0, w=0.0, dt=1.0)
    assert math.isclose(p.x, 0.5, abs_tol=1e-5)
    assert math.isclose(p.y, 0.0, abs_tol=1e-5)
    assert math.isclose(p.theta, 0.0, abs_tol=1e-5)

    # Turn in place: 90 degrees left (pi/2 rad)
    dt_turn = (math.pi / 2.0) / tracker.w_gain
    p = tracker.update_odometry(v=0.0, w=1.0, dt=dt_turn)
    assert math.isclose(p.theta, math.pi / 2.0, abs_tol=1e-5)


def test_dead_reckoning_closed_square_path():
    """T0 requirement: closed square path returns to the origin in simulation."""
    tracker = LocalizationTracker(motion_calib=None, camera_calib=None)
    tracker.v_gain = 0.4
    tracker.w_gain = 1.5
    tracker.drift_rad_per_m = 0.0
    tracker.apply_drift_compensation = False
    tracker.set_pose(0.0, 0.0, 0.0)

    side_length = 1.0  # 1 meter
    dt_fwd = side_length / tracker.v_gain
    dt_turn = (math.pi / 2.0) / tracker.w_gain

    # Discretize into small 50 Hz steps like sim_robot
    step_dt = 0.02
    for _ in range(4):
        # Drive forward 1 m
        t_accum = 0.0
        while t_accum < dt_fwd:
            dt = min(step_dt, dt_fwd - t_accum)
            tracker.update_odometry(v=1.0, w=0.0, dt=dt)
            t_accum += dt

        # Turn left 90 deg
        t_accum = 0.0
        while t_accum < dt_turn:
            dt = min(step_dt, dt_turn - t_accum)
            tracker.update_odometry(v=0.0, w=1.0, dt=dt)
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
        motion_calib={
            "min_pwm": 0.12,
            "max_speed": 0.3,
            "v_gain_m_per_s": 0.4135,
            "w_gain_rad_per_s": 6.48,
            "drift_rad_per_m": 0.0,
        },
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
    def step(v, w):
        tracker = LocalizationTracker(
            motion_calib={"min_pwm": 0.12, "max_speed": 0.3, "v_gain_m_per_s": 0.4135, "w_gain_rad_per_s": 6.48, "drift_rad_per_m": 0.0},
            camera_calib=None, config_path=None)
        tracker.set_pose(0.0, 0.0, 0.0)
        p = tracker.update_odometry(v=v, w=w, dt=0.1)
        return p.x / 0.1 / 0.4135, p.theta / 0.1 / 6.48            # effective (v, w) in command units, small dt: no arc error

    v, w = step(0.6, 0.065)                       # steering while driving: both wheels above the dead zone, the turn must stay
    assert math.isclose(v, 0.6, rel_tol=0.02) and math.isclose(w, 0.065, rel_tol=0.02)
    v, w = step(0.5, 0.15)                        # left wheel 0.35 * 0.3 = 0.105 < 0.12 stops: v 0.325, w 0.325
    assert math.isclose(v, 0.325, rel_tol=0.03) and math.isclose(w, 0.325, rel_tol=0.03)
    assert step(0.0, 0.3) == (0.0, 0.0)           # wheels at 0.09: stands still
    assert step(0.3, 0.0) == (0.0, 0.0)
    v, w = step(0.0, 0.5)                         # wheels at 0.15: spins
    assert v == 0.0 and math.isclose(w, 0.5, rel_tol=0.02)


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
