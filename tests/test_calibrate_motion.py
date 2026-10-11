import json
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


def row(kind, moving, forward=0.0, lateral=0.0, turn=0.0, v=0.0, w=0.0, max_speed=0.3, k=1.0, min_pwm=0.12):
    return {"kind": kind, "v": v, "w": w, "seconds_commanded": 4, "moving_s": moving, "forward_m": forward, "lateral_m": lateral, "turn_deg": turn,
            "battery_v": 12.0, "max_speed": max_speed, "k": k, "min_pwm": min_pwm}


def synthetic_rows(v_gain=0.18, w_gain=1.2, kappa=0.05, n=5):
    rows = []
    for i in range(n):  # moving_s varies, as R1 holds do; the measured values follow the model with a little scatter
        t = 3.0 + 0.4 * i
        d = v_gain * t * (1 + 0.01 * (-1) ** i)
        rows.append(row("straight", t, forward=d, lateral=kappa * d * d / 2, v=1.0))   # constant curvature: lateral = kappa d^2 / 2
        rows.append(row("turn", t / 2, turn=math.degrees(w_gain * t / 2) * (1 + 0.01 * (-1) ** i), w=1.0))
    return rows


def test_fit_recovers_the_gains_whatever_the_hold_time():
    out = fit(synthetic_rows())
    assert abs(out["v_gain_m_per_s"] - 0.18) < 0.005
    assert abs(out["w_gain_rad_per_s"] - 1.2) < 0.03
    assert abs(out["drift_rad_per_m"] - 0.05) < 0.005          # a curvature, not lateral / forward
    assert out["passed"] and out["runs"] == {"straight": 5, "turn": 5, "dropped": 0}
    assert out["k"] == 1.0 and out["min_pwm"] == 0.12 and out["max_speed"] == 0.3   # the values the runs were recorded with
    assert out["battery_v"] == {"min": 12.0, "max": 12.0}
    json.dumps(out, allow_nan=False)                             # valid JSON


def test_fit_fails_on_scatter_and_on_too_few_runs():
    rows = synthetic_rows()
    for i, r in enumerate(r for r in rows if r["kind"] == "straight"):
        r["forward_m"] *= 1.0 + 0.3 * (-1) ** i   # +-30 % scatter
    out = fit(rows)
    assert not out["passed"] and any("CV" in p for p in out["problems"])
    assert any("fewer than" in p for p in fit(synthetic_rows(n=3))["problems"])


def test_no_runs_gives_valid_json_and_a_clear_failure():
    out = fit([])
    assert not out["passed"] and out["repeatability"]["forward_gain_cv"] is None
    json.dumps(out, allow_nan=False)


def test_mixed_settings_and_unusable_rows_are_reported():
    rows = synthetic_rows()
    rows[0]["max_speed"] = 0.5                                   # one run recorded at another speed cap
    rows[2]["moving_s"] = 0.0                                    # a run with no motion in the log
    out = fit(rows)
    assert not out["passed"] and any("different" in p for p in out["problems"])
    assert out["runs"]["dropped"] == 1
