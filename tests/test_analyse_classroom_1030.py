import pytest

from tools.analyse_classroom_1030 import align_t0, fit_m0_vs_battery, pulse_turns, windowed_verify


def _run(t0=5000.0, lat=0.12, turn=0.44):
    """A synthetic deploy run: 3 spin pulses (0.2 s on, 0.5 s pause) then a drive; the board's bearing jumps by -turn per pulse, seen `lat` s after the pulse ends."""
    log, cmds, t = [], [], 0.0
    for k in range(3):
        for _ in range(6):
            log.append(dict(t=round(t, 3), cmd_v=0.0, cmd_w=0.45, state="APPROACH_VANTAGE", x_m=0.0, y_m=0.0))
            t += 1 / 30.0
        for _ in range(15):
            log.append(dict(t=round(t, 3), cmd_v=0.0, cmd_w=0.0, state="APPROACH_VANTAGE", x_m=0.0, y_m=0.0))
            t += 1 / 30.0
    for _ in range(60):
        log.append(dict(t=round(t, 3), cmd_v=0.55, cmd_w=0.0, state="APPROACH_VANTAGE", x_m=0.0, y_m=0.0))
        t += 1 / 30.0

    def cmd_at(tt):
        rows = [r for r in log if r["t"] <= tt]
        return (rows[-1]["cmd_v"], rows[-1]["cmd_w"]) if rows else (0.0, 0.0)
    servo, s = [], -0.05
    while s < t:
        n_done = sum(1 for k in range(3) if s >= k * 0.7 + 0.2 + lat)
        v, w = cmd_at(s)
        servo.append(dict(t=t0 + s, range_m=2.7, bearing_rad=0.3 - turn * n_done, cmd_v=v, cmd_w=w))
        s += 0.05
    return log, servo


def test_alignment_and_still_to_still_turn():
    log, servo = _run()
    t0, votes, n = align_t0(log, servo)
    assert t0 == pytest.approx(5000.0, abs=0.04) and votes >= n - 1
    p = pulse_turns(log, servo, t0)
    assert len(p) >= 2 and all(q["turn_rad"] == pytest.approx(0.44, abs=1e-6) for q in p)          # left pulse, bearing falls: turn = -(after - before)
    assert all(q["earliest_final_after_end"] >= 0.12 for q in p)                                     # the latency shows as the delay of the first changed frame


def test_windowed_rule_and_offset_fit():
    assert windowed_verify([0.1 * i for i in range(10)], [True] * 10) == pytest.approx(0.5)            # the 6th answer, all in view
    assert windowed_verify([0.1 * i for i in range(10)], [i % 2 == 0 for i in range(10)]) is None      # 50 % < 70 %
    pts = [(V, 0.165, 1.64 * (0.165 - (0.03 - 0.02 * (V - 11.5))), 1.0) for V in (11.3, 11.4, 11.5, 11.6, 11.7)]
    f = fit_m0_vs_battery(pts)
    assert f["m0_at_11_5"] == pytest.approx(0.03, abs=1e-9) and f["m0_per_volt"] == pytest.approx(-0.02, abs=1e-9)
