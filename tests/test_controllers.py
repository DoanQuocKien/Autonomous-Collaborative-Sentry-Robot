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
    assert w < 0.0, f"Expected right turn w < 0.0, got {w}"
    assert v > 0.0
    from common.mixing import mix
    from sentry.nav.explore import Command, ExploreSettings, legal
    s = ExploreSettings()
    assert legal(Command(v, w, "", ""), s)
    left, right = mix(v, w)
    assert abs(left) >= 0.40 and abs(right) >= 0.40

    # 3. Obstacle critical at 0.25 m (< 0.35 m)
    # Forward velocity must be cut to zero for collision prevention; spin in place away
    ctrl.reset()
    v, w, _, obs_active = ctrl.compute(
        t=1.0, target_dist_m=2.0, yaw_err=0.0, obstacle_dist_m=0.25, obstacle_bearing_rad=-0.1
    )
    assert obs_active
    assert v == 0.0
    assert w >= 0.45  # Deflects left since obstacle was on right
    assert legal(Command(v, w, "", ""), s)
    left, right = mix(v, w)
    assert abs(left) >= 0.40 and abs(right) >= 0.40


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


def test_hold_controller_recenter_time_within_1_5s_and_all_commands_legal():
    """HoldController must center within 1.5 s and emit 100% legal commands above dead zone."""
    from sentry.nav.explore import Command, ExploreSettings, legal
    s = ExploreSettings()
    hold = HoldController(HoldBehaviorConfig(max_recenter_time_s=1.5, center_tolerance_norm=0.10))

    t = 1.0
    dt = 0.05
    # Uncentered target offset: 0.30 norm error
    # Simulated robot turning in response to hold.compute(t, yaw_err)
    yaw_err = 0.30
    steps = 0
    while abs(yaw_err) > 0.10 and steps < 40:
        v, w, is_c = hold.compute(t, yaw_err)
        assert legal(Command(v, w, "", ""), s), f"Command ({v}, {w}) must be legal for motors"
        assert v == 0.0
        assert abs(w) >= 0.45  # Must overcome dead zone
        # Physical unicycle rotation: w normalized * w_max (approx 2.0 rad/s) * dt
        yaw_err -= w * 0.4 * dt
        t += dt
        steps += 1

    # Final step when centered
    v, w, is_c = hold.compute(t, yaw_err)
    assert is_c
    assert v == 0.0 and w == 0.0
    assert legal(Command(v, w, "", ""), s)

    recenter_duration = hold.max_observed_recenter_time_s
    assert recenter_duration <= 1.5, f"Recentering took {recenter_duration} s, exceeding 1.5 s limit!"


def test_controllers_suppress_derivative_kick_on_stalled_frame():
    """Frame stall dt > 0.2 s suppresses derivative term, preventing derivative kick."""
    ctrl = PursuitController()
    # Step 1 at t=1.0
    ctrl.compute(t=1.0, target_dist_m=2.0, yaw_err=0.1)
    # Stalled frame 1.5 s later (dt = 1.5 s) with error change
    v, w, _, _ = ctrl.compute(t=2.5, target_dist_m=3.0, yaw_err=0.4)
    # Without kick suppression, (dist_err - prev) / 1.5 or kick would alter behavior;
    # with suppression d_dist=0 and d_yaw=0 so outputs remain bounded within normal caps.
    assert -0.45 <= v <= 0.55
    assert abs(w) <= 1.0


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
        assert out.mode == "PURSUE"
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


def test_wheel_mixing_dead_zone_all_cases():
    """Verify that every emitted command satisfies legal(Command(v, w), ExploreSettings())
    and that both mixed wheels are strictly >= 0.40 (or 0.0 when stopped).

    Regression test for Review Item 1 (HNHL):
    PursuitController().compute(0, 2.0, 0.2) must not produce unmixable commands like (0.55, 0.30).
    """
    from common.mixing import mix
    from sentry.nav.explore import Command, ExploreSettings, legal
    s = ExploreSettings()
    ctrl = PursuitController()

    # Case 1: Compute(0, 2.0, 0.2) from Reviewer comment
    v, w, is_c, obs = ctrl.compute(t=0.0, target_dist_m=2.0, yaw_err=0.2)
    assert legal(Command(v, w, "", ""), s), f"Command ({v}, {w}) must be legal"
    left, right = mix(v, w)
    assert abs(left) >= 0.40 and abs(right) >= 0.40, f"Mixed wheels ({left}, {right}) below 0.40!"
    assert w == pytest.approx(0.14, abs=0.01)  # Bounded to w_trans_max

    # Case 2: Reverse motion (target too close at 0.5 m)
    ctrl.reset()
    v, w, is_c, obs = ctrl.compute(t=1.0, target_dist_m=0.5, yaw_err=0.1)
    assert v == -0.45 and w == 0.0
    assert legal(Command(v, w, "", ""), s)
    left, right = mix(v, w)
    assert abs(left) >= 0.40 and abs(right) >= 0.40

    # Case 3: Pure spin in place (target at standoff distance 1.2 m, uncentered yaw_err = 0.3)
    ctrl.reset()
    v, w, is_c, obs = ctrl.compute(t=1.0, target_dist_m=1.2, yaw_err=0.3)
    assert v == 0.0 and abs(w) >= 0.45
    assert legal(Command(v, w, "", ""), s)
    left, right = mix(v, w)
    assert abs(left) >= 0.40 and abs(right) >= 0.40

    # Case 4: Standoff clean stop (target at 1.2 m, centered yaw_err = 0.02)
    ctrl.reset()
    v, w, is_c, obs = ctrl.compute(t=1.0, target_dist_m=1.2, yaw_err=0.02)
    assert v == 0.0 and w == 0.0
    assert legal(Command(v, w, "", ""), s)


def test_nonfinite_inputs_rejected_without_mutating_state():
    """Verify NaN/Inf/negative distance are rejected with ValueError without corrupting state.

    Regression test for Review Item 4 (HNHL):
    Validates distance, yaw, obstacle inputs before mutating history, and ensures clean recovery.
    """
    ctrl = PursuitController()

    # NaN distance rejected
    with pytest.raises(ValueError, match="target_dist_m"):
        ctrl.compute(t=1.0, target_dist_m=float("nan"), yaw_err=0.0)
    assert ctrl._prev_t is None
    assert ctrl._prev_dist_err is None

    # Negative distance rejected
    with pytest.raises(ValueError, match="target_dist_m"):
        ctrl.compute(t=1.0, target_dist_m=-0.5, yaw_err=0.0)
    assert ctrl._prev_t is None

    # NaN yaw rejected
    with pytest.raises(ValueError, match="yaw_err"):
        ctrl.compute(t=1.0, target_dist_m=2.0, yaw_err=float("nan"))
    assert ctrl._prev_t is None

    # Inf obstacle rejected
    with pytest.raises(ValueError, match="obstacle_dist_m"):
        ctrl.compute(t=1.0, target_dist_m=2.0, yaw_err=0.0, obstacle_dist_m=float("inf"))
    assert ctrl._prev_t is None

    # HoldController rejects NaN yaw
    hold = HoldController()
    with pytest.raises(ValueError, match="yaw_err"):
        hold.compute(t=1.0, yaw_err=float("nan"))
    assert hold._prev_t is None
    assert hold._entered_t is None

    # Immediate recovery after rejected inputs
    v, w, is_c, obs = ctrl.compute(t=1.0, target_dist_m=2.0, yaw_err=0.0)
    assert v > 0.4 and ctrl._prev_t == 1.0


def test_gap_reset_reconciles_interception_controller_mode_and_resumes_pursuit():
    """Observation gap > 1.0 s resets detector and reconciles InterceptionController to PURSUE.

    Regression test for Review Item 3 (HNHL):
    Enter HOLD at 20 Hz for 3 s -> gap to t=5.0 s emits TARGET_LOST and reconciles mode='PURSUE' ->
    subsequent moving target resumes forward pursuit without getting stuck in HOLD.
    """
    ctrl = InterceptionController()
    t = 0.0
    dt = 0.05
    robot_pose = (0.0, 0.0, 0.0)

    # 1. Enter HOLD: Target stationary at world (1.5, 0.0) for 3.0 s at 20 Hz
    for _ in range(60):
        t += dt
        out = ctrl.step(t, robot_pose, (1.5, 0.0), yaw_err=0.0)

    assert ctrl.mode == "HOLD"
    assert out.v == 0.0

    # 2. Frame gap of 2.0 s: target observation arrives at t = 5.0 s (> max_observation_gap_s 1.0 s)
    out_gap = ctrl.step(5.0, robot_pose, (1.5, 0.0), yaw_err=0.0)
    assert out_gap.event == "TARGET_LOST", f"Expected TARGET_LOST on gap, got {out_gap.event}"
    assert ctrl.mode == "PURSUE", f"Mode must reconcile back to PURSUE on gap/target loss, got {ctrl.mode}"

    # 3. Subsequent moving target reacquired: target moves East at 0.5 m/s
    t = 5.0
    moving_outputs = []
    for _ in range(20):
        t += dt
        wx = 1.5 + 0.5 * (t - 5.0)
        out = ctrl.step(t, robot_pose, (wx, 0.0), yaw_err=0.0)
        moving_outputs.append(out)

    assert ctrl.mode == "PURSUE"
    # Robot should actively drive forward in pursuit of moving target
    assert any(o.v > 0.4 for o in moving_outputs), "Robot must resume forward pursuit motion!"


def test_pursuit_turns_in_place_before_driving_when_far_off_centre():
    """Audit 2026-11-14: forward steering is capped at v - dead_zone (about 0.15), so a sideways walker was lost."""
    ctl = PursuitController(PursuitConfig())
    v, w, _, _ = ctl.compute(0.0, 2.5, 0.8)                     # far and 0.8 off-centre (left)
    assert v == 0.0 and w >= PursuitConfig().w_spin
    v, w, _, _ = PursuitController(PursuitConfig()).compute(0.0, 2.5, 0.2)   # small error: drive and steer
    assert v >= PursuitConfig().v_min_forward and w > 0
    # hysteresis: once turning, keep turning down to spin_first_exit_yaw; a fresh controller at 0.45 drives
    assert ctl.compute(0.1, 2.5, 0.45)[0] == 0.0
    assert ctl.compute(0.2, 2.5, 0.3)[0] >= PursuitConfig().v_min_forward
    assert PursuitController(PursuitConfig()).compute(0.0, 2.5, 0.45)[0] >= PursuitConfig().v_min_forward
