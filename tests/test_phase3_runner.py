"""Tests for Phase 3 Interception Runner and Phase 2 -> Phase 3 event chain.

Owner: kouun-rokku (KR).
Week 6 deliverable (Implementation Plan §5):
- Tests T0 for the Phase 2 -> Phase 3 event chain.
- PURSUE/HOLD wired to HoldDetector and closed-loop controllers.
- Multi-target FIFO queue handoff upon TARGET_EXITED.
- STRIKE evasion preempting PURSUE/HOLD and auto-resuming.
- 100% legal motor commands satisfying JetBot motor dead zone.
"""
import math
import pytest

from sentry.app.phase3_runner import Phase3Runner, Phase3Settings
from sentry.app.state_machine import State, StateMachine
from sentry.app.target_queue import IntruderRecord, TargetQueue
from sentry.nav.controllers import (
    HoldBehaviorConfig,
    InterceptionController,
    PursuitConfig,
)
from sentry.nav.explore import Command as NavCommand, ExploreSettings, legal
from sentry.nav.hold_detector import HoldConfig


class MockSpeaker:
    def __init__(self):
        self.played = []

    def play(self, clip: str):
        self.played.append(clip)


@pytest.fixture
def explore_settings():
    return ExploreSettings()


@pytest.fixture
def runner():
    speaker = MockSpeaker()
    sm = StateMachine(initial_state=State.STANDBY, t0=0.0)
    queue = TargetQueue()
    ctrl = InterceptionController(
        pursuit_cfg=PursuitConfig(target_distance_m=1.2, kp_distance=1.0, kp_yaw=2.0),
        hold_behavior_cfg=HoldBehaviorConfig(kp_yaw=2.0, w_max=0.8, max_recenter_time_s=1.5),
        hold_detector_cfg=HoldConfig(speed_threshold_mps=0.1, dwell_time_s=2.0, exit_speed_mps=0.2, min_samples=5, min_window_span_s=0.2),
    )
    return Phase3Runner(
        sm=sm,
        controller=ctrl,
        queue=queue,
        speaker=speaker,
    )


def test_standby_stationary_monitoring(runner, explore_settings):
    """In STANDBY without active intruder, robot stays stationary with zero commands."""
    assert runner.state == State.STANDBY
    v, w = runner.step(t=1.0, robot_pose=(0.0, 0.0, 0.0))
    assert v == 0.0 and w == 0.0
    assert legal(NavCommand(v, w, "", ""), explore_settings)


def test_phase2_to_phase3_intruder_queued_activates_pursue(runner, explore_settings):
    """Phase 2 INTRUDER_QUEUED event triggers deploy -> PURSUE and audio prompt."""
    res = runner.enqueue_intruder("intruder_alpha", t=1.0)
    assert res.state == State.PURSUE
    assert runner.state == State.PURSUE
    assert runner.active_target == "intruder_alpha"
    assert "intruder_detected" in runner.prompts

    # Target walking ahead at 2.5 m (beyond 1.2 m standoff) -> positive forward velocity
    v, w = runner.step(t=1.05, robot_pose=(0.0, 0.0, 0.0), target_pos=(2.5, 0.0))
    assert v > 0.40
    assert abs(w) < 0.1
    assert legal(NavCommand(v, w, "", ""), explore_settings)


def test_pursuit_to_standoff_hold_on_stationary_dwell(runner, explore_settings):
    """When target stops for > 2.0s, HoldDetector dispatches TARGET_STATIONARY -> HOLD with v=0."""
    runner.enqueue_intruder("target_1", t=0.0)
    assert runner.state == State.PURSUE

    t = 0.0
    dt = 0.05
    # Target moving forward from (1.5, 0.0)
    target_x = 1.5
    for _ in range(20): # 1.0 s moving at 0.3 m/s
        t += dt
        target_x += 0.3 * dt
        v, w = runner.step(t=t, robot_pose=(0.0, 0.0, 0.0), target_pos=(target_x, 0.0))
        assert runner.state == State.PURSUE
        assert legal(NavCommand(v, w, "", ""), explore_settings)

    # Target stops at target_x for 2.5 s
    hold_entered = False
    for _ in range(50): # 2.5 s stopped
        t += dt
        v, w = runner.step(t=t, robot_pose=(0.0, 0.0, 0.0), target_pos=(target_x, 0.0))
        assert legal(NavCommand(v, w, "", ""), explore_settings)
        if runner.state == State.HOLD:
            hold_entered = True
            # In HOLD: translation must be strictly 0.0 (no orbit)
            assert v == 0.0

    assert hold_entered
    assert runner.state == State.HOLD
    assert "hold_position" in runner.prompts


def test_standoff_hold_yaw_recentering_within_tolerance(runner, explore_settings):
    """In HOLD, yaw-only commands recenter target without translation."""
    runner.enqueue_intruder("target_offset", t=0.0)
    t = 0.0
    dt = 0.05

    # Target stationary with an angular offset (+Y is left, bearing > 0)
    target_pos = (1.5, 0.3)
    for _ in range(50): # 2.5 s dwell to trigger HOLD
        t += dt
        v, w = runner.step(t=t, robot_pose=(0.0, 0.0, 0.0), target_pos=target_pos)
        assert legal(NavCommand(v, w, "", ""), explore_settings)

    assert runner.state == State.HOLD
    # Translation must be zero
    assert v == 0.0
    # Yaw command should turn left (positive w) or stop cleanly if centered
    if w != 0.0:
        assert w >= 0.40 # overcomes dead zone


def test_hold_hysteresis_resumes_pursue_when_target_moves(runner, explore_settings):
    """When target accelerates past 0.2 m/s, HoldDetector emits TARGET_MOVING -> resumes PURSUE."""
    runner.enqueue_intruder("target_1", t=0.0)
    t = 0.0
    dt = 0.05
    target_x = 1.5

    # 1. Drive into HOLD (stationary for 2.2 s)
    for _ in range(45):
        t += dt
        runner.step(t=t, robot_pose=(0.0, 0.0, 0.0), target_pos=(target_x, 0.0))

    assert runner.state == State.HOLD

    # 2. Creep at 0.12 m/s in hysteresis band [0.1, 0.2]: should stay in HOLD
    for _ in range(15):
        t += dt
        target_x += 0.12 * dt
        v, w = runner.step(t=t, robot_pose=(0.0, 0.0, 0.0), target_pos=(target_x, 0.0))
        assert runner.state == State.HOLD
        assert v == 0.0

    # 3. Accelerate past 0.25 m/s: should trigger TARGET_MOVING -> PURSUE
    pursue_resumed = False
    for _ in range(20):
        t += dt
        target_x += 0.35 * dt
        v, w = runner.step(t=t, robot_pose=(0.0, 0.0, 0.0), target_pos=(target_x, 0.0))
        assert legal(NavCommand(v, w, "", ""), explore_settings)
        if runner.state == State.PURSUE:
            pursue_resumed = True
            assert v > 0.40

    assert pursue_resumed
    assert runner.state == State.PURSUE


def test_multi_target_fifo_queue_and_exit_handoff(runner, explore_settings):
    """Multiple intruders: T1 pursued while T2 waits in FIFO; upon T1 exit, T2 is engaged."""
    runner.enqueue_intruder("intruder_T1", t=1.0)
    assert runner.state == State.PURSUE
    assert runner.active_target == "intruder_T1"

    # Second intruder arrives at door while T1 is active
    res2 = runner.enqueue_intruder("intruder_T2", t=2.0)
    assert runner.state == State.PURSUE # Still pursuing T1
    assert runner.active_target == "intruder_T1"
    assert len(runner.queue) == 1

    # T1 exits the room -> StateMachine transitions to SEARCH for next target in queue (T2)
    res_exit = runner.notify_target_exited(t=5.0)
    assert runner.state == State.SEARCH
    assert runner.active_target == "intruder_T2"

    # Vision re-acquires T2 in the room -> transitions back to PURSUE
    res_found = runner._dispatch_event("TARGET_FOUND", t=6.0)
    assert runner.state == State.PURSUE
    assert runner.active_target == "intruder_T2"

    # T2 exits with no remaining queued targets -> transitions to STANDBY (Spec §4.6)
    res_exit2 = runner.notify_target_exited(t=10.0)
    assert runner.state == State.STANDBY
    assert runner.active_target is None


def test_strike_event_preempts_to_evade_and_resumes_pursuit(runner, explore_settings):
    """Preemptive strike trigger causes reverse/yaw evade pulse (400 ms) and returns to PURSUE."""
    runner.enqueue_intruder("target_strike", t=0.0)
    assert runner.state == State.PURSUE

    # Step at t=1.0 s
    v, w = runner.step(t=1.0, robot_pose=(0.0, 0.0, 0.0), target_pos=(1.5, 0.0))
    assert runner.state == State.PURSUE

    # Lunge attack detected at t=1.2 s, obstacle on the left -> yaw right (negative w)
    res_strike = runner.trigger_strike(t=1.2, obstacle_side="left")
    assert runner.state == State.EVADE

    # During evasion: reverse velocity (-1.0) and turn away from obstacle
    v_ev, w_ev = runner.step(t=1.25, robot_pose=(0.0, 0.0, 0.0))
    assert runner.state == State.EVADE
    assert v_ev == -1.0
    assert w_ev < 0.0 # turned right away from left obstacle
    assert legal(NavCommand(v_ev, w_ev, "", ""), explore_settings)

    # 400 ms duration expires at t=1.65 s -> auto-resumes PURSUE
    runner.step(t=1.65, robot_pose=(0.0, 0.0, 0.0), target_pos=(1.5, 0.0))
    assert runner.state == State.PURSUE


def test_obstacle_repulsion_during_pursuit(runner, explore_settings):
    """Foreground obstacle at 0.45 m deflects pursuit path away from obstacle."""
    runner.enqueue_intruder("target_obs", t=0.0)
    # Obstacle on the right (-0.2 rad bearing, since left is positive) at 0.45 m (< 0.5 m threshold)
    v, w = runner.step(
        t=1.0,
        robot_pose=(0.0, 0.0, 0.0),
        target_pos=(2.0, 0.0),
        obstacle_dist_m=0.45,
        obstacle_bearing_rad=-0.2,
    )
    assert legal(NavCommand(v, w, "", ""), explore_settings)
    # Should steer left (positive deflection offset) away from right obstacle
    assert w > 0.0
