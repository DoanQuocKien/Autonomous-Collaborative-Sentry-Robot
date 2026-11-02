"""T0 unit tests for sentry/nav/controllers.py (Week 5, DoanQuocKien & kouun-rokku).

Verifies:
1. PursuitController distance PD maintaining 1.2 m standoff.
2. PursuitController yaw PD centering target in FOV.
3. Obstacle override: repulsive deflection when d_obs < 0.5 m, forward cut when d_obs < 0.35 m.
4. HoldController: v = 0.0 strictly (zero translation/no orbit), yaw-only recentering.
5. InterceptionController: closed-loop switching between PURSUE and HOLD driven by HoldDetector.
"""
import math
import pytest

from sentry.nav.controllers import (
    HoldBehaviorConfig,
    HoldController,
    InterceptionController,
    PursuitConfig,
    PursuitController,
)


def test_pursuit_distance_pd_maintains_one_point_two_meter_standoff():
    ctrl = PursuitController(PursuitConfig(target_distance_m=1.2, kp_distance=0.8, kd_distance=0.1))

    # Target far ahead at 2.5 m -> positive forward command v > 0
    v, w, is_centered, obs_active = ctrl.compute(t=1.0, target_dist_m=2.5, yaw_err=0.0)
    assert v > 0.4 and v <= 0.55
    assert w == pytest.approx(0.0)
    assert is_centered and not obs_active

    # Target close at 0.8 m (< 1.2 m) -> reverse command v < 0
    ctrl.reset()
    v, w, is_centered, obs_active = ctrl.compute(t=1.0, target_dist_m=0.8, yaw_err=0.0)
    assert v < 0.0
    assert w == pytest.approx(0.0)

    # Target at exact 1.2 m standoff -> v ~ 0
    ctrl.reset()
    v, w, is_centered, obs_active = ctrl.compute(t=1.0, target_dist_m=1.2, yaw_err=0.0)
    assert abs(v) < 1e-5


def test_pursuit_centering_pd_steers_toward_target():
    ctrl = PursuitController(PursuitConfig(kp_yaw=1.5, kd_yaw=0.2, center_tolerance_norm=0.10))

    # Target to the left (yaw_err = +0.3) -> positive angular velocity w > 0 (turn left)
    v, w, is_centered, _ = ctrl.compute(t=1.0, target_dist_m=1.2, yaw_err=0.3)
    assert w > 0.3
    assert not is_centered

    # Target to the right (yaw_err = -0.3) -> negative angular velocity w < 0 (turn right)
    ctrl.reset()
    v, w, is_centered, _ = ctrl.compute(t=1.0, target_dist_m=1.2, yaw_err=-0.3)
    assert w < -0.3
    assert not is_centered

    # Target within +/- 10% center tolerance -> is_centered is True
    ctrl.reset()
    _, _, is_centered, _ = ctrl.compute(t=1.0, target_dist_m=1.2, yaw_err=0.05)
    assert is_centered


def test_obstacle_override_applies_deflection_and_cuts_critical_forward():
    ctrl = PursuitController(PursuitConfig(
        obstacle_threshold_m=0.5,
        obstacle_critical_m=0.35,
        obstacle_avoid_w=0.45,
    ))

    # 1. Obstacle at 1.0 m (> 0.5 m) -> no override
    v, w, _, obs_active = ctrl.compute(
        t=1.0, target_dist_m=2.0, yaw_err=0.0, obstacle_dist_m=1.0, obstacle_bearing_rad=0.0
    )
    assert not obs_active
    assert w == pytest.approx(0.0)

    # 2. Obstacle in foreground at 0.45 m (< 0.5 m) on the left (bearing = +0.2 rad)
    # Must add negative yaw deflection (steer right) to bypass obstacle
    ctrl.reset()
    v, w, _, obs_active = ctrl.compute(
        t=1.0, target_dist_m=2.0, yaw_err=0.0, obstacle_dist_m=0.45, obstacle_bearing_rad=0.2
    )
    assert obs_active
    assert w < -0.3, f"Expected right turn w < -0.3, got {w}"
    assert v > 0.0

    # 3. Obstacle critical at 0.25 m (< 0.35 m)
    # Forward velocity must be cut to zero/reverse for collision prevention
    ctrl.reset()
    v, w, _, obs_active = ctrl.compute(
        t=1.0, target_dist_m=2.0, yaw_err=0.0, obstacle_dist_m=0.25, obstacle_bearing_rad=-0.1
    )
    assert obs_active
    assert v <= 0.0
    assert w > 0.3  # Deflects left since obstacle was on right


def test_hold_controller_zero_translation_and_yaw_recenter():
    hold = HoldController(HoldBehaviorConfig(kp_yaw=1.5, kd_yaw=0.2, center_tolerance_norm=0.10))

    # In hold, linear speed v is ALWAYS strictly 0.0 (no translation, no orbiting)
    v, w, is_centered = hold.compute(t=1.0, yaw_err=0.25)
    assert v == 0.0
    assert w > 0.0
    assert not is_centered

    # Bbox centered
    v, w, is_centered = hold.compute(t=1.1, yaw_err=0.04)
    assert v == 0.0
    assert is_centered


def test_interception_controller_closed_loop_pursue_to_hold_and_exit():
    ctrl = InterceptionController()
    t = 0.0
    dt = 0.05
    robot_pose = (0.0, 0.0, 0.0)

    # Phase 1: Target moving East at 0.5 m/s, robot following
    for _ in range(20):
        t += dt
        target_wx = 1.5 + 0.5 * t
        target_wy = 0.0
        out = ctrl.step(t, robot_pose, (target_wx, target_wy), yaw_err=0.0)
        assert out.mode == "PURSUIT"
        assert out.event is None

    # Phase 2: Target stops at world (2.5, 0.0) for 2.8 seconds
    events = []
    for _ in range(60):
        t += dt
        out = ctrl.step(t, robot_pose, (2.5, 0.0), yaw_err=0.05)
        if out.event:
            events.append(out.event)

    assert "TARGET_STATIONARY" in events
    assert ctrl.mode == "HOLD"
    assert out.v == 0.0  # Translation stopped

    # Phase 3: While in HOLD, target slightly off center -> yaw PD commands rotation, v stays 0
    out = ctrl.step(t + dt, robot_pose, (2.5, 0.0), yaw_err=-0.2)
    assert out.mode == "HOLD"
    assert out.v == 0.0
    assert out.w < 0.0

    # Phase 4: Target resumes walking at 0.4 m/s -> exits HOLD back to PURSUIT
    t += dt
    x = 2.5
    exit_events = []
    for _ in range(30):
        t += dt
        x += 0.4 * dt
        out = ctrl.step(t, robot_pose, (x, 0.0), yaw_err=0.0)
        if out.event:
            exit_events.append(out.event)

    assert "TARGET_MOVING" in exit_events
    assert ctrl.mode == "PURSUE"
