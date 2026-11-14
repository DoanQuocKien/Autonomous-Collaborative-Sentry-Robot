import math
import random

import pytest

from sentry.nav.bearing_servo import TrimEstimator, TurnController, heading_entropy_nats, wrap_deg


def simulate_turn(target, rate, startup, coast, noise_deg, seed, nominal_rate=120.0, w_spin=0.45, dt=1.0 / 30, t_max=15.0, blind_clear=0.2):
    """A turn-in-place plant that is BLIND while moving (measured 2026-11-13: motion blur, no board detection from 0.15 s after the start of a spin until 0.2 s after its stop):
    the bearing is only observed (10 Hz) when the robot has been still for `blind_clear` s. A command only moves the robot after `startup` s (start-up lag) and it coasts `coast` s
    after a stop. `rate` is the true deg/s; the controller starts from `nominal_rate` and has to learn the difference."""
    rng = random.Random(seed)
    ctl = TurnController(target, w_spin=w_spin, rate_deg_s=nominal_rate)
    theta, t, next_obs, last_move, on_since, last_dir, coast_left = 0.0, 0.0, 0.0, -1.0, None, 1.0, 0.0
    cmds, b_static = [], 20.0
    while t < t_max:
        obs = None
        if t >= next_obs and t - last_move >= blind_clear:
            obs = b_static - theta + rng.gauss(0.0, noise_deg)
            next_obs = t + 0.1
        w, done = ctl.step(t, obs)
        cmds.append(w)
        if abs(w) > 1e-9:
            on_since = t if on_since is None else on_since
            last_dir = math.copysign(1.0, w)
            if t - on_since >= startup:
                theta += last_dir * rate * dt
                last_move, coast_left = t, coast
        else:
            on_since = None
            if coast_left > 0:
                theta += last_dir * rate * dt * 0.5
                last_move, coast_left = t, coast_left - dt
        t += dt
        if done:
            for _ in range(int(0.6 / dt)):                                   # let the robot finish coasting
                if coast_left > 0:
                    theta += last_dir * rate * dt * 0.5
                    coast_left -= dt
            break
    return theta, ctl, cmds


def open_loop_error(target, rate, startup, coast, nominal_rate=120.0):
    """What a timed spin gives: spin for target / nominal_rate seconds; the start-up lag eats the beginning and the coast adds a little."""
    duration = abs(target) / nominal_rate
    turned = rate * max(0.0, duration - startup) + 0.5 * rate * coast
    return abs(abs(target) - turned)


def run_family(target, rate_lo, rate_hi):
    closed, opened = [], []
    for seed in range(60):
        rng = random.Random(1000 + seed)
        rate, startup, coast = rng.uniform(rate_lo, rate_hi), rng.uniform(0.0, 0.1), rng.uniform(0.0, 0.05)
        theta, ctl, cmds = simulate_turn(target, rate=rate, startup=startup, coast=coast, noise_deg=0.3, seed=seed)
        assert ctl.state == ctl.DONE and ctl.pulses <= ctl.max_pulses
        assert set(abs(round(c, 6)) for c in cmds) <= {0.0, 0.45}, "every command is a stop or a spin above the dead zone"
        closed.append(abs(target - theta))
        opened.append(open_loop_error(target, rate, startup, coast))
    return sorted(closed), opened


@pytest.mark.parametrize("target", [45.0, -45.0, 30.0, -60.0])
def test_pulse_and_measure_turn_is_accurate_and_learns_the_gain(target):
    near, _ = run_family(target, 100, 170)                                   # the measured spin rates: 125 deg/s in the classroom, 147 deg/s at the dorm
    far, far_open = run_family(target, 60, 220)                              # far outside anything measured: a timed spin cannot follow it
    assert near[len(near) // 2] <= 8.0 and near[int(0.9 * len(near))] <= 14.0, "(the minimum pulse of 0.12 s is 14-20 deg, so about +/-8 deg is the limit)"
    assert sum(far) / len(far) <= 9.0
    if abs(target) >= 45.0:     # for a 30 deg turn the pulse resolution is as large as the timed spin's own error: no gain there
        assert sum(far_open) / len(far_open) >= 1.3 * sum(far) / len(far), "the timed spin should suffer from the rate mismatch"


def test_turn_stops_when_the_board_is_lost_and_rejects_big_targets():
    ctl = TurnController(45.0)
    assert ctl.step(0.0, None) == (0.0, False)                              # blind at the start: wait, never spin without a first bearing
    assert ctl.step(0.5, 10.0)[0] == 0.45                                    # first observation fixes the zero and starts a pulse
    assert ctl.step(10.0, None) == (0.0, False)                              # the pulse is over: the controller goes blind and waits for the blur to clear
    w, done = ctl.step(14.0, None)                                          # still no observation after settle_s + lost_s
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
