"""T0 integration tests for closed-loop pursuit, obstacle override, and standoff hold simulation."""
import pytest

from tools.sim_pursuit_hold import run_simulation


def test_closed_loop_pursuit_and_standoff_hold_simulation():
    res = run_simulation(total_time_s=12.0)
    assert res["status"] == "PASS"
    assert res["dwell_requirement_met"]
    assert res["hysteresis_exit_met"]
    assert res["hold_zero_translation"]
    assert res["hold_confirmed"]
    assert res["all_commands_legal"]
    assert res["recenter_requirement_met"]
    assert res["max_recenter_time_s"] <= 1.5
    assert res["pursuit_centered_ratio"] >= 0.80
    assert 5.8 <= res["stationary_trigger_t"] <= 6.8
    assert 8.0 <= res["moving_trigger_t"] <= 9.0
