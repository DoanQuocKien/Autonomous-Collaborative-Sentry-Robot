import math
import random

import pytest

from sentry.nav.bearing_servo import TrimEstimator, TurnController, heading_entropy_nats, wrap_deg


def simulate_turn(target, rate, lag, latency, coast, noise_deg, seed, w_spin=0.45, dt=1.0 / 30, t_max=10.0):
    """A turn-in-place plant: commands reach the motors after `lag`, the robot keeps turning `coast` s after a stop, the bearing is seen after `latency` at 10 Hz.
    Ranges used by the test follow the measured system: video latency p50 46 ms / p95 128 ms, 33 ms command period, e-stop cut 7 ms."""
    rng = random.Random(seed)
    ctl = TurnController(target, w_spin=w_spin, rate_deg_s=120.0)
    theta, hist, applied, cmds = 0.0, [], [], []
    coast_left, last_dir, t, next_obs, last_obs, b_static = 0.0, 1.0, 0.0, 0.0, None, 20.0
    while t < t_max:
        theta_seen = None
        if t >= next_obs:                                                   # one observation every 0.1 s, showing the state `latency` ago
            k = max(0, len(hist) - 1 - int(round(latency / dt)))
            theta_seen = hist[k] if hist else 0.0
            last_obs = b_static - theta_seen + rng.gauss(0.0, noise_deg)
            next_obs += 0.1
        w, done = ctl.step(t, last_obs)
        cmds.append(w)
        applied.append(w)
        w_motor = applied[max(0, len(applied) - 1 - int(round(lag / dt)))]
        if abs(w_motor) > 1e-9:
            theta += math.copysign(rate, w_motor) * dt
            coast_left, last_dir = coast, math.copysign(1.0, w_motor)
        elif coast_left > 0:
            theta += last_dir * rate * dt * 0.5
            coast_left -= dt
        hist.append(theta)
        t += dt
        if done and t > 0.5:
            for _ in range(int(0.8 / dt)):                                   # let the robot finish coasting
                hist.append(theta)
            break
    return theta, ctl, cmds


def open_loop_error(target, rate, lag, coast, nominal_rate=120.0):
    """What a timed spin gives: spin for target / nominal_rate seconds; the robot also turns during the command lag's tail and the coast."""
    duration = abs(target) / nominal_rate
    turned = rate * duration + 0.5 * rate * coast
    return abs(abs(target) - turned)


def run_family(target, rate_lo, rate_hi):
    closed, opened = [], []
    for seed in range(60):
        rng = random.Random(1000 + seed)
        rate, lag, latency, coast = rng.uniform(rate_lo, rate_hi), rng.uniform(0.02, 0.06), rng.uniform(0.05, 0.15), rng.uniform(0.0, 0.05)
        theta, ctl, cmds = simulate_turn(target, rate=rate, lag=lag, latency=latency, coast=coast, noise_deg=0.3, seed=seed)
        assert ctl.state == ctl.DONE
        assert set(abs(round(c, 6)) for c in cmds) <= {0.0, 0.45}, "every command is a stop or a spin above the dead zone"
        closed.append(abs(target - theta))
        opened.append(open_loop_error(target, rate, lag, coast))
    return sorted(closed), opened


@pytest.mark.parametrize("target", [45.0, -45.0, 30.0, -60.0])
def test_closed_loop_turn_error_is_small_and_does_not_depend_on_the_turn_rate(target):
    near, _ = run_family(target, 100, 140)                                   # rate close to the 120 deg/s the controller assumes
    far, far_open = run_family(target, 70, 170)                              # the rate changes with battery and floor: a timed spin cannot follow it
    assert near[len(near) // 2] <= 6.0 and near[int(0.9 * len(near))] <= 13.0, "(the minimum pulse of 0.12 s is about 14 deg, so about +/-7 deg is the limit)"
    assert sum(far) / len(far) <= 7.5
    if abs(target) >= 45.0:     # for a 30 deg turn the +/-7 deg pulse resolution is as large as the timed spin's own error (6.6 vs 6.6 deg in this simulation): no gain there
        assert sum(far_open) / len(far_open) >= 1.2 * sum(far) / len(far), "the timed spin should suffer from the rate mismatch"


def test_turn_stops_when_the_board_is_lost_and_rejects_big_targets():
    ctl = TurnController(45.0)
    assert ctl.step(0.0, 10.0) == (0.45, False)
    w, done = ctl.step(2.0, None)                                          # no observation for 2 s > lost_s
    assert (w, done) == (0.0, True) and ctl.reason == "board lost"
    with pytest.raises(ValueError):
        TurnController(120.0)
    with pytest.raises(ValueError):
        TurnController(0.0)


def test_estimator_converges_on_a_constant_veer_and_reports_less_variance():
    rng = random.Random(1)
    est = TrimEstimator(trim0=0.0, std0=0.03, q_std=0.002)                # a veer that hardly changes: small process noise
    std0 = est.std
    for _ in range(8):
        est.predict()
        est.update(-0.02 + rng.gauss(0.0, 0.004), r_std=0.004)
    assert abs(est.trim + 0.02) < 0.005 and est.std < std0


def test_estimator_tracks_a_drifting_veer_better_than_a_fixed_trim():
    rng = random.Random(2)
    truth, est, kf_err, fixed_err = -0.01, TrimEstimator(0.0, std0=0.03, q_std=0.01), [], []
    for _ in range(60):
        truth += rng.gauss(0.0, 0.008)                                      # the veer wanders from drive to drive
        est.predict()
        kf_err.append((est.trim - truth) ** 2)                             # prediction made BEFORE seeing this drive
        fixed_err.append((0.0 - truth) ** 2)
        est.update(truth + rng.gauss(0.0, 0.003), r_std=0.003)
    assert math.sqrt(sum(kf_err) / len(kf_err)) < 0.7 * math.sqrt(sum(fixed_err) / len(fixed_err))


def test_entropy_orders_straightness_and_wrap():
    straight = [0.4, -0.3, 0.2, -0.5, 0.1, 0.3]
    crooked = [10.0, -12.0, 8.0, -15.0, 9.0, 12.0]
    assert heading_entropy_nats(straight) < heading_entropy_nats(crooked)
    assert heading_entropy_nats([1.0, 1.0, 1.0]) == pytest.approx(0.5 * math.log(2 * math.pi * math.e * 0.05 ** 2))   # floored sd
    assert wrap_deg(190.0) == pytest.approx(-170.0)
    with pytest.raises(ValueError):
        heading_entropy_nats([1.0])
    with pytest.raises(ValueError):
        TrimEstimator().update(float("nan"))
