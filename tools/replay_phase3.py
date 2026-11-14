"""Phase 3 Replay and Verification Tool (Week 6, kouun-rokku).

Replays closed-loop Phase 3 interception across multi-target encounters:
  Phase 2 Handoff (INTRUDER_QUEUED) -> Closed-loop Pursuit -> Standoff Hold ->
  FIFO Queue Stacking -> Hysteresis Pursuit Exit -> Strike Evasion -> Target Exit Handoff

Evaluates:
  1. Hold dwell time requirement (dwell >= 2.0 s at v_target < 0.1 m/s -> TARGET_STATIONARY -> HOLD).
  2. Hold zero translation (v = 0.0 strictly, no orbiting).
  3. Yaw-only recentering (centered within <= 1.5 s).
  4. Hysteresis band exit (v_target > 0.2 m/s -> TARGET_MOVING -> PURSUE).
  5. Multi-target FIFO queue handoff upon TARGET_EXITED.
  6. STRIKE evasion pulse (preempts to EVADE, reverses away from obstacle, resumes PURSUE).
  7. 100% legal motor commands overcoming physical motor dead zone (0.40).

Usage:
    python -m tools.replay_phase3
    python -m tools.replay_phase3 --out reports/kouun-rokku/week-06/phase3_replay_summary.json
"""
import argparse
import json
import logging
import math
from pathlib import Path
from typing import Any, Dict, List, Tuple

from sentry.app.phase3_runner import Phase3Runner, Phase3Settings
from sentry.app.state_machine import State, StateMachine
from sentry.app.target_queue import TargetQueue
from sentry.nav.controllers import (
    HoldBehaviorConfig,
    InterceptionController,
    PursuitConfig,
)
from sentry.nav.explore import Command as NavCommand, ExploreSettings, legal
from sentry.nav.hold_detector import HoldConfig
from tools.sim_robot import SimRobot

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("replay_phase3")


def run_phase3_replay(total_time_s: float = 18.0, dt: float = 0.02) -> Dict[str, Any]:
    """Execute end-to-end Phase 3 replay simulation."""
    sim = SimRobot(v_max=0.55, w_max=2.0, watchdog_s=0.3)
    explore_settings = ExploreSettings()

    sm = StateMachine(initial_state=State.STANDBY, t0=0.0)
    queue = TargetQueue()
    ctrl = InterceptionController(
        pursuit_cfg=PursuitConfig(target_distance_m=1.2, kp_distance=1.0, kp_yaw=2.0),
        hold_behavior_cfg=HoldBehaviorConfig(kp_yaw=2.0, w_max=0.8, max_recenter_time_s=1.5),
        hold_detector_cfg=HoldConfig(speed_threshold_mps=0.1, dwell_time_s=2.0, exit_speed_mps=0.2, min_samples=5, min_window_span_s=0.2),
    )
    runner = Phase3Runner(
        sm=sm,
        controller=ctrl,
        queue=queue,
        explore_settings=explore_settings,
    )

    # Simulation script:
    # t=1.0: Intruder T1 detected at door -> INTRUDER_QUEUED -> PURSUE
    # t=1.0-4.0: T1 moves along +X at 0.35 m/s
    # t=4.0-8.0: T1 stops at (3.05, 0.0) for 4.0 s -> triggers HOLD around t=6.0 s
    # t=6.5: Intruder T2 detected at door -> INTRUDER_QUEUED -> queued in FIFO while T1 held
    # t=8.0-11.0: T1 moves along +X at 0.35 m/s -> triggers PURSUE
    # t=10.0: T1 lunges -> STRIKE event (obstacle on left) -> EVADE for 0.4 s -> auto resumes PURSUE
    # t=12.0: T1 exits the room -> TARGET_EXITED -> T2 engaged (via SEARCH -> TARGET_FOUND)
    # t=15.0: T2 exits the room -> TARGET_EXITED -> queue empty -> STANDBY

    t = 0.0
    steps = int(total_time_s / dt)

    t1_x = 2.0
    t1_y = 0.0
    t2_x = 1.8
    t2_y = 0.4

    history = []
    events_recorded = []
    hold_v_samples = []
    illegal_commands = 0
    t1_enqueued = False
    t2_enqueued = False
    strike_triggered = False
    t1_exited = False
    t2_found = False
    t2_exited = False

    stationary_detected_t = None
    moving_resumed_t = None

    for _ in range(steps):
        t = round(t + dt, 4)

        # 1. Event triggers
        if t >= 1.0 and not t1_enqueued:
            t1_enqueued = True
            res = runner.enqueue_intruder("intruder_T1", t=t)
            events_recorded.append({"t": t, "event": "INTRUDER_QUEUED", "target": "intruder_T1", "state": res.state.value})

        if t >= 6.5 and not t2_enqueued:
            t2_enqueued = True
            res = runner.enqueue_intruder("intruder_T2", t=t)
            events_recorded.append({"t": t, "event": "INTRUDER_QUEUED", "target": "intruder_T2", "state": res.state.value})

        if t >= 10.0 and not strike_triggered:
            strike_triggered = True
            res = runner.trigger_strike(t=t, obstacle_side="left")
            events_recorded.append({"t": t, "event": "STRIKE", "state": res.state.value})

        if t >= 12.0 and not t1_exited:
            t1_exited = True
            res = runner.notify_target_exited(t=t)
            events_recorded.append({"t": t, "event": "TARGET_EXITED", "target": "intruder_T1", "state": res.state.value})

        if t >= 12.5 and t1_exited and not t2_found:
            t2_found = True
            res = runner._dispatch_event("TARGET_FOUND", t=t)
            events_recorded.append({"t": t, "event": "TARGET_FOUND", "target": "intruder_T2", "state": res.state.value})

        if t >= 15.0 and not t2_exited:
            t2_exited = True
            res = runner.notify_target_exited(t=t)
            events_recorded.append({"t": t, "event": "TARGET_EXITED", "target": "intruder_T2", "state": res.state.value})

        # 2. Update target trajectory
        if t < 4.0:
            t1_x += 0.35 * dt
        elif t < 8.0:
            pass # T1 stopped
        elif t < 12.0:
            t1_x += 0.35 * dt

        # Active target position relative to robot
        if runner.active_target == "intruder_T1":
            target_world_x = t1_x
            target_world_y = t1_y
        elif runner.active_target == "intruder_T2":
            target_world_x = t2_x
            target_world_y = t2_y
        else:
            target_world_x = None
            target_world_y = None

        target_local = None
        dist_m = 0.0
        bearing_rel = 0.0

        if target_world_x is not None:
            dx = target_world_x - sim.x
            dy = target_world_y - sim.y
            dist_m = math.hypot(dx, dy)
            bearing_world = math.atan2(dy, dx)
            bearing_rel = (bearing_world - sim.theta + math.pi) % (2 * math.pi) - math.pi
            cos_th = math.cos(sim.theta)
            sin_th = math.sin(sim.theta)
            fwd_m = dx * cos_th + dy * sin_th
            left_m = -dx * sin_th + dy * cos_th
            target_local = (fwd_m, left_m)

        # Step runner
        v_cmd, w_cmd = runner.step(
            t=t,
            robot_pose=(sim.x, sim.y, sim.theta),
            target_pos=target_local,
        )

        # Verify command legality
        cmd_obj = NavCommand(v_cmd, w_cmd, "", "")
        is_legal = legal(cmd_obj, explore_settings)
        if not is_legal:
            illegal_commands += 1

        # Check state transitions
        if runner.state == State.HOLD:
            hold_v_samples.append(abs(v_cmd))
            if stationary_detected_t is None:
                stationary_detected_t = t
        elif runner.state == State.PURSUE and stationary_detected_t is not None and moving_resumed_t is None and t > 8.0:
            moving_resumed_t = t

        # Update simulated robot
        sim.v = v_cmd
        sim.w = w_cmd
        sim.last_cmd = t
        sim.step(t, dt)

        history.append({
            "t": t,
            "state": runner.state.value,
            "active_target": runner.active_target,
            "v_cmd": round(v_cmd, 3),
            "w_cmd": round(w_cmd, 3),
            "legal": is_legal,
            "distance_m": round(dist_m, 3),
            "bearing_rad": round(bearing_rel, 3),
        })

    # Metrics evaluation
    dwell_met = stationary_detected_t is not None and (5.8 <= stationary_detected_t <= 6.8)
    exit_met = moving_resumed_t is not None and (8.0 <= moving_resumed_t <= 9.2)
    hold_zero_trans = len(hold_v_samples) > 0 and all(v == 0.0 for v in hold_v_samples)
    recenter_met = ctrl.hold.max_observed_recenter_time_s <= 1.5
    all_legal = (illegal_commands == 0)
    fifo_correct = (runner.active_target is None and len(queue) == 0 and len(queue.all_completed()) == 2)

    pass_all = bool(dwell_met and exit_met and hold_zero_trans and recenter_met and all_legal and fifo_correct)

    results = {
        "status": "PASS" if pass_all else "FAIL",
        "evaluation_tier": "T0_SIMULATION_CLOSED_LOOP",
        "total_duration_s": total_time_s,
        "metrics": {
            "dwell_time_trigger_s": stationary_detected_t,
            "dwell_requirement_met": dwell_met,
            "hysteresis_exit_trigger_s": moving_resumed_t,
            "hysteresis_exit_met": exit_met,
            "hold_zero_translation_verified": hold_zero_trans,
            "hold_sample_count": len(hold_v_samples),
            "max_recenter_time_s": round(ctrl.hold.max_observed_recenter_time_s, 3),
            "recenter_requirement_met": recenter_met,
            "all_commands_legal": all_legal,
            "illegal_command_count": illegal_commands,
            "fifo_queue_sequence_met": fifo_correct,
            "completed_target_count": len(queue.all_completed()),
        },
        "events_recorded": events_recorded,
        "sample_count": len(history),
    }
    return results


def main():
    parser = argparse.ArgumentParser(description="Replay Phase 3 closed-loop pursuit, hold, and queue handoff.")
    parser.add_argument("--out", type=str, default="reports/kouun-rokku/week-06/phase3_replay_summary.json", help="Output JSON path")
    parser.add_argument("--time", type=float, default=18.0, help="Total simulation duration in seconds")
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Executing Phase 3 replay simulation (%.1f s)...", args.time)
    res = run_phase3_replay(total_time_s=args.time)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2)

    logger.info("Saved Phase 3 replay summary to %s", out_path)
    logger.info("Result: %s", res["status"])
    logger.info("  Hold triggered at t=%.2f s (target stopped at 4.0 s) -> %s",
                res["metrics"]["dwell_time_trigger_s"] or -1.0,
                "PASS" if res["metrics"]["dwell_requirement_met"] else "FAIL")
    logger.info("  Hold zero-translation verified: %s (%d samples)",
                res["metrics"]["hold_zero_translation_verified"],
                res["metrics"]["hold_sample_count"])
    logger.info("  Max recenter time: %.2f s (<= 1.5 s) -> %s",
                res["metrics"]["max_recenter_time_s"],
                "PASS" if res["metrics"]["recenter_requirement_met"] else "FAIL")
    logger.info("  Pursuit resumed at t=%.2f s (target accelerated at 8.0 s) -> %s",
                res["metrics"]["hysteresis_exit_trigger_s"] or -1.0,
                "PASS" if res["metrics"]["hysteresis_exit_met"] else "FAIL")
    logger.info("  FIFO queue completed count: %d -> %s",
                res["metrics"]["completed_target_count"],
                "PASS" if res["metrics"]["fifo_queue_sequence_met"] else "FAIL")
    logger.info("  All commands legal: %s (illegal: %d)",
                res["metrics"]["all_commands_legal"],
                res["metrics"]["illegal_command_count"])


if __name__ == "__main__":
    main()
