"""Closed-loop simulation of Pursuit PD, Obstacle Override, and Standoff Hold (Week 5, kouun-rokku).

Runs closed loop against tools.sim_robot.SimRobot with a scripted moving target and obstacles:
1. Target walks at 0.4 m/s: robot pursues, centering target and approaching 1.2 m standoff.
2. Obstacle detected at < 0.5 m during pursuit: controller adds deflection offset.
3. Target stops for > 2.0 s: HoldDetector triggers TARGET_STATIONARY -> transitions to HOLD.
4. During HOLD: translation is zero (v = 0.0), yaw-only PD keeps target centered without orbit.
5. Target resumes walking > 0.2 m/s: HoldDetector triggers TARGET_MOVING -> resumes PURSUIT.

Usage:
    python -m tools.sim_pursuit_hold
    python -m tools.sim_pursuit_hold --out reports/kouun-rokku/week-05/sim_pursuit_hold.json
"""
import argparse
import json
import math
from pathlib import Path
from typing import Dict, List, Tuple

from sentry.nav.controllers import (
    HoldBehaviorConfig,
    InterceptionController,
    PursuitConfig,
)
from sentry.nav.explore import Command, ExploreSettings, legal
from sentry.nav.hold_detector import HoldConfig
from tools.sim_robot import SimRobot


def run_simulation(
    total_time_s: float = 12.0,
    dt: float = 0.02, # 50 Hz loop (matching config.toml [sim] loop_hz)
) -> Dict:
    """Execute closed-loop pursuit and hold simulation against SimRobot."""
    sim = SimRobot(v_max=0.5, w_max=2.0, watchdog_s=0.3)
    explore_settings = ExploreSettings()
    ctrl = InterceptionController(
        pursuit_cfg=PursuitConfig(target_distance_m=1.2, kp_distance=1.0, kp_yaw=2.0),
        hold_behavior_cfg=HoldBehaviorConfig(kp_yaw=2.0, w_max=1.0, max_recenter_time_s=1.5),
        hold_detector_cfg=HoldConfig(speed_threshold_mps=0.1, dwell_time_s=2.0, exit_speed_mps=0.2, min_samples=5, min_window_span_s=0.2),
    )

    t = 0.0
    steps = int(total_time_s / dt)
    history = []
    events_logged = []

    # Target motion script:
    # 0.0 - 4.0 s: Target walks along East (+X) from (2.0, 0.0) at 0.35 m/s
    # 4.0 - 8.0 s: Target stops at (3.4, 0.0) for 4.0 s
    # 8.0 - 12.0 s: Target moves North-East (+X, +Y) at 0.4 m/s
    target_x = 2.0
    target_y = 0.0

    obstacle_x = 1.6
    obstacle_y = 0.15

    for _ in range(steps):
        t += dt

        # Update target script
        if t < 4.0:
            target_x += 0.35 * dt
        elif t < 8.0:
            pass  # Stopped
        else:
            target_x += 0.30 * dt
            target_y += 0.25 * dt

        # Target relative to robot frame
        # p_rel = R(-theta) * (p_target - p_robot)
        dx = target_x - sim.x
        dy = target_y - sim.y
        dist_m = math.hypot(dx, dy)
        bearing_world = math.atan2(dy, dx)
        bearing_rel = (bearing_world - sim.theta + math.pi) % (2 * math.pi) - math.pi

        # Target local coordinates (forward, left)
        cos_th = math.cos(sim.theta)
        sin_th = math.sin(sim.theta)
        fwd_m = dx * cos_th + dy * sin_th
        left_m = -dx * sin_th + dy * cos_th

        # Obstacle check during early pursuit (t in [1.5, 2.5])
        obs_dist = None
        obs_bearing = 0.0
        if 1.5 <= t <= 2.5:
            obs_dx = obstacle_x - sim.x
            obs_dy = obstacle_y - sim.y
            obs_dist = math.hypot(obs_dx, obs_dy)
            obs_bearing = (math.atan2(obs_dy, obs_dx) - sim.theta + math.pi) % (2 * math.pi) - math.pi

        # Execute controller step
        # yaw_err is bearing_rel (positive left -> positive w turns left)
        out = ctrl.step(
            t=t,
            robot_pose=(sim.x, sim.y, sim.theta),
            target_local_pos=(fwd_m, left_m),
            yaw_err=bearing_rel,
            obstacle_dist_m=obs_dist,
            obstacle_bearing_rad=obs_bearing,
        )

        if out.event:
            events_logged.append({"t": round(t, 3), "event": out.event, "mode": out.mode})

        # Apply motor dead-zone enforcement through legal()
        # On physical JetBot, commands inside dead zone stall (effective motion 0, 0)
        is_cmd_legal = legal(Command(out.v, out.w, "", ""), explore_settings)
        actual_v = out.v if is_cmd_legal else 0.0
        actual_w = out.w if is_cmd_legal else 0.0

        sim.v = actual_v
        sim.w = actual_w
        sim.last_cmd = t
        sim.step(t, dt)

        history.append({
            "t": round(t, 3),
            "robot_x": round(sim.x, 3),
            "robot_y": round(sim.y, 3),
            "robot_theta": round(sim.theta, 3),
            "target_x": round(target_x, 3),
            "target_y": round(target_y, 3),
            "distance_m": round(dist_m, 3),
            "bearing_rad": round(bearing_rel, 3),
            "v_cmd": round(out.v, 3),
            "w_cmd": round(out.w, 3),
            "cmd_legal": is_cmd_legal,
            "mode": out.mode,
            "obstacle_override": out.obstacle_override,
        })

    # Summary analysis
    # Pursuit steady-state evaluation while target was walking (t in [2.5, 3.8]):
    walk_samples = [h for h in history if 2.5 <= h["t"] <= 3.8]
    walk_distances = [h["distance_m"] for h in walk_samples]
    walk_bearings = [abs(h["bearing_rad"]) for h in walk_samples]
    mean_dist = sum(walk_distances) / len(walk_distances) if walk_distances else 0.0
    centered_pct = sum(1 for b in walk_bearings if b <= 0.15) / len(walk_bearings) if walk_bearings else 0.0

    # Hold evaluation (t in [6.5, 7.8]):
    hold_samples = [h for h in history if 6.5 <= h["t"] <= 7.8]
    hold_speeds = [abs(h["v_cmd"]) for h in hold_samples]
    hold_zero_trans = all(v == 0.0 for v in hold_speeds) if hold_speeds else False
    hold_modes = [h["mode"] for h in hold_samples]
    hold_confirmed = all(m == "HOLD" for m in hold_modes) if hold_modes else False
    all_commands_legal = all(h["cmd_legal"] for h in history)
    max_recenter_s = ctrl.hold.max_observed_recenter_time_s
    recenter_valid = max_recenter_s <= 1.5

    event_names = [e["event"] for e in events_logged]
    stat_events = [e for e in events_logged if e["event"] == "TARGET_STATIONARY"]
    moving_events = [e for e in events_logged if e["event"] == "TARGET_MOVING"]

    stationary_trigger_t = stat_events[0]["t"] if stat_events else None
    moving_trigger_t = moving_events[0]["t"] if moving_events else None

    # Target stopped at 4.0 s, so stationary trigger should occur at 4.0 + ~2.0 s (around 6.0 - 6.5 s)
    dwell_valid = bool(stationary_trigger_t and 5.8 <= stationary_trigger_t <= 6.8)
    exit_valid = bool(moving_trigger_t and 8.0 <= moving_trigger_t <= 9.0)

    pass_all = bool(
        dwell_valid
        and exit_valid
        and hold_zero_trans
        and hold_confirmed
        and all_commands_legal
        and recenter_valid
    )

    summary = {
        "status": "PASS" if pass_all else "FAIL",
        "total_duration_s": total_time_s,
        "events": events_logged,
        "pursuit_mean_distance_m": round(mean_dist, 3),
        "pursuit_centered_ratio": round(centered_pct, 3),
        "hold_confirmed": hold_confirmed,
        "hold_zero_translation": hold_zero_trans,
        "all_commands_legal": all_commands_legal,
        "max_recenter_time_s": round(max_recenter_s, 3),
        "recenter_requirement_met": recenter_valid,
        "stationary_trigger_t": stationary_trigger_t,
        "moving_trigger_t": moving_trigger_t,
        "dwell_requirement_met": dwell_valid,
        "hysteresis_exit_met": exit_valid,
        "sample_count": len(history),
    }
    return summary


def main():
    parser = argparse.ArgumentParser(description="Simulate Pursuit & Standoff Hold closed-loop.")
    parser.add_argument("--out", type=Path, default=None, help="Output path for JSON summary.")
    parser.add_argument("--time", type=float, default=12.0, help="Total simulation duration in seconds.")
    args = parser.parse_args()

    summary = run_simulation(total_time_s=args.time)
    print(f"[SimPursuitHold] Result: {summary['status']}")
    print(f"  Pursuit mean distance: {summary['pursuit_mean_distance_m']} m (target 1.2 m)")
    print(f"  Centering ratio: {summary['pursuit_centered_ratio'] * 100:.1f} %")
    print(f"  Hold triggered at t={summary['stationary_trigger_t']} s (target stopped at 4.0 s)")
    print(f"  Hold zero-translation verified: {summary['hold_zero_translation']}")
    print(f"  Pursuit resumed at t={summary['moving_trigger_t']} s (target moved at 8.0 s)")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(f"[SimPursuitHold] Summary saved to {args.out}")


if __name__ == "__main__":
    main()
