import math

from tools.calibrate_motion import fit, moving_seconds


def test_moving_seconds_counts_only_nonzero_stretches():
    log = ["09:19:19.078 e-stop released: motor commands accepted",
           "09:19:19.123 motors +0.12 +0.12",
           "09:19:20.123 motors +0.00 +0.00",      # 1.0 s moving
           "09:19:22.000 motors +0.15 +0.15",
           "09:19:26.000 motors +0.00 +0.00",      # 4.0 s moving
           "09:19:30.000 e-stop ENGAGED: refusing motor commands"]
    assert abs(moving_seconds(log) - 5.0) < 1e-9
    assert moving_seconds(["09:00:00.000 motors +0.00 +0.00"]) == 0.0


def synthetic_rows(v_gain=0.18, w_gain=1.2, drift=0.03, n=5):
    rows = []
    for i in range(n):  # moving_s varies, as R1 holds do; the measured distance follows the model with a little scatter
        t = 3.0 + 0.4 * i
        rows.append({"kind": "straight", "v": 1.0, "w": 0.0, "seconds_commanded": 4, "moving_s": t, "forward_m": v_gain * t * (1 + 0.01 * (-1) ** i), "lateral_m": drift * v_gain * t, "turn_deg": 0})
        rows.append({"kind": "turn", "v": 0.0, "w": 1.0, "seconds_commanded": 2, "moving_s": t / 2, "forward_m": 0, "lateral_m": 0, "turn_deg": math.degrees(w_gain * t / 2) * (1 + 0.01 * (-1) ** i)})
    return rows


def test_fit_recovers_the_gains_whatever_the_hold_time():
    out = fit(synthetic_rows())
    assert abs(out["v_gain_m_per_s"] - 0.18) < 0.005
    assert abs(out["w_gain_rad_per_s"] - 1.2) < 0.03
    assert abs(out["drift_rad_per_m"] - 0.03) < 0.002
    assert out["passed"] and out["runs"] == {"straight": 5, "turn": 5}
    assert out["k"] == 1.0 and out["min_pwm"] == 0.12


def test_fit_fails_on_scatter_and_on_too_few_runs():
    rows = synthetic_rows()
    for i, r in enumerate(r for r in rows if r["kind"] == "straight"):
        r["forward_m"] *= 1.0 + 0.3 * (-1) ** i   # +-30 % scatter
    out = fit(rows)
    assert not out["passed"] and any("CV" in p for p in out["problems"])
    assert any("fewer than" in p for p in fit(synthetic_rows(n=3))["problems"])
