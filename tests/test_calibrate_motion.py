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


def test_moving_seconds_across_midnight():
    log = ["23:59:59.000 motors +0.20 +0.20", "00:00:01.500 motors +0.00 +0.00"]
    assert abs(moving_seconds(log) - 2.5) < 1e-9


def multi_speed_rows(gain=0.5, v0=0.3, wgain=7.0, w0=0.2, n=3):
    rows = []
    for v in (0.4, 0.7, 1.0):
        for i in range(n):
            t = 5.0 + 0.1 * i
            rows.append(row("straight", t, forward=gain * (v - v0) * t * (1 + 0.01 * (-1) ** i), lateral=0.05 * v, v=v))
    for w, t in ((0.5, 1.5), (1.0, 0.5)):
        for i in range(n):
            rows.append(row("turn", t, turn=math.degrees(wgain * (w - w0) * t) * (1 + 0.01 * (-1) ** i), w=w))
    return rows


def test_several_speeds_give_an_affine_model_that_shows_the_dead_zone():
    out = fit(multi_speed_rows())
    f, t = out["speed_model"]["forward"], out["speed_model"]["turn"]
    assert abs(f["gain"] - 0.5) < 0.02 and abs(f["x_at_zero"] - 0.3) < 0.03        # speed is zero at command 0.3, not at 0
    assert abs(t["gain"] - 7.0) < 0.3 and abs(t["x_at_zero"] - 0.2) < 0.03
    assert out["passed"], out["problems"]
    assert set(out["drift_by_v"]) == {"0.4", "0.7", "1"} and out["v_gain_m_per_s"] == f["gain"]
    json.dumps(out, allow_nan=False)


def test_several_speeds_need_runs_at_every_speed():
    rows = [r for r in multi_speed_rows() if not (r["kind"] == "straight" and r["v"] == 0.7)][:-1]   # lose one run of the lowest-count group
    rows = [r for r in rows if not (r["kind"] == "turn" and r["w"] == 1.0)][:] + [r for r in multi_speed_rows() if r["kind"] == "turn" and r["w"] == 1.0][:2]
    out = fit(rows)
    assert not out["passed"] and any("fewer than 3" in p for p in out["problems"])


def test_one_speed_keeps_the_old_per_unit_gain():
    out = fit(synthetic_rows())
    assert "speed_model" not in out and abs(out["v_gain_m_per_s"] - 0.18) < 0.005
