"""Evaluates HoldDetector metrics: timing, hysteresis, and robot yaw invariance.

Usage:
    python -m tools.evaluate_hold_detector --out reports/kouun-rokku/week-05/hold_detector_metrics.json
"""
import argparse
import json
import math
from pathlib import Path
import numpy as np

from sentry.nav.hold_detector import HoldConfig, HoldDetector


def evaluate_detector():
    results = {}

    # Test 1: Dwell time trigger on stationary target
    det1 = HoldDetector(HoldConfig(speed_threshold_mps=0.1, dwell_time_s=2.0))
    t, dt = 0.0, 0.05
    stat_t = None
    first_stat_t = None
    while t < 3.0:
        t += dt
        st = det1.update_world(t, 1.0, 0.0)
        if st.speed_mps is not None and st.speed_mps < 0.1 and first_stat_t is None:
            first_stat_t = t
        if st.event == "TARGET_STATIONARY":
            stat_t = t
            break
    dwell_duration = (stat_t - first_stat_t) if (stat_t and first_stat_t) else None
    results["dwell_time_trigger_s"] = round(dwell_duration, 3) if dwell_duration else None
    results["dwell_time_pass"] = bool(dwell_duration and abs(dwell_duration - 2.0) <= 0.15)

    # Test 2: Hysteresis band [0.1, 0.2] m/s
    det2 = HoldDetector(HoldConfig(speed_threshold_mps=0.1, dwell_time_s=1.0, exit_speed_mps=0.2))
    # Enter hold: run past initial window fill (0.25 s) + dwell_time (1.0 s)
    t = 0.0
    while t < 1.5:
        t += dt
        det2.update_world(t, 0.0, 0.0)
    in_hold_at_start = det2.in_hold

    # Creep at 0.15 m/s for 1.0 s
    creep_held = True
    x = 0.0
    for _ in range(20):
        t += dt
        x += 0.15 * dt
        st = det2.update_world(t, x, 0.0)
        if not det2.in_hold:
            creep_held = False

    # Accelerate to 0.35 m/s
    exit_t = None
    for _ in range(20):
        t += dt
        x += 0.35 * dt
        st = det2.update_world(t, x, 0.0)
        if st.event == "TARGET_MOVING":
            exit_t = t
            break

    results["hysteresis_band_maintained"] = in_hold_at_start and creep_held
    results["hysteresis_exit_verified"] = exit_t is not None and not det2.in_hold

    # Test 3: Robot yawing alone while target moves in world
    det3 = HoldDetector(HoldConfig(speed_threshold_mps=0.1, dwell_time_s=1.0))
    t = 0.0
    false_holds = 0
    for _ in range(100):  # 5.0 seconds
        t += dt
        # Target moves at 0.4 m/s in world
        twx = 0.4 * t
        twy = 0.0
        # Robot spins at 1.5 rad/s at (0, 0)
        r_th = (1.5 * t) % (2 * math.pi) - math.pi
        cos_t = math.cos(r_th)
        sin_t = math.sin(r_th)
        loc_fwd = twx * cos_t + twy * sin_t
        loc_left = -twx * sin_t + twy * cos_t

        st = det3.update(t, (0.0, 0.0, r_th), (loc_fwd, loc_left))
        if det3.in_hold:
            false_holds += 1

    results["robot_yawing_alone_false_hold_count"] = false_holds
    results["robot_yawing_alone_invariant_met"] = (false_holds == 0)

    # Test 4: Robot yawing in place while target is stationary in world
    det4 = HoldDetector(HoldConfig(speed_threshold_mps=0.1, dwell_time_s=1.0))
    t = 0.0
    stationary_detected = False
    for _ in range(50):
        t += dt
        twx, twy = 1.5, 0.0
        r_th = (0.8 * t) % (2 * math.pi) - math.pi
        cos_t = math.cos(r_th)
        sin_t = math.sin(r_th)
        loc_fwd = twx * cos_t + twy * sin_t
        loc_left = -twx * sin_t + twy * cos_t
        st = det4.update(t, (0.0, 0.0, r_th), (loc_fwd, loc_left))
        if st.event == "TARGET_STATIONARY":
            stationary_detected = True

    results["stationary_target_detected_while_robot_spins"] = stationary_detected

    overall_pass = all([
        results["dwell_time_pass"],
        results["hysteresis_band_maintained"],
        results["hysteresis_exit_verified"],
        results["robot_yawing_alone_invariant_met"],
        results["stationary_target_detected_while_robot_spins"],
    ])
    results["status"] = "PASS" if overall_pass else "FAIL"
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    metrics = evaluate_detector()
    print(f"[HoldDetectorMetrics] Status: {metrics['status']}")
    print(f"  Dwell time trigger: {metrics['dwell_time_trigger_s']} s")
    print(f"  Hysteresis band maintained: {metrics['hysteresis_band_maintained']}")
    print(f"  Robot yawing false holds: {metrics['robot_yawing_alone_false_hold_count']}")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
        print(f"[HoldDetectorMetrics] Saved to {args.out}")


if __name__ == "__main__":
    main()
