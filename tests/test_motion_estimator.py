import math
import random

from sentry.nav.motion_estimator import MotionEstimator


def drive(true_scale, v, seconds, drift=0.0, start_range=1.95, hz=12, dropout=0.3, noise=0.01, seed=0, w_gain=6.48, delay=0.0):
    """A simulated drive from rest toward a marker straight ahead (the true speed = true_scale * 0.48 * (v - 0.146), a 0.3 s ramp, a heading drift in rad/s); yields (t, range, bearing)."""
    rnd = random.Random(seed)
    x = y = th = 0.0                                                    # robot pose; the marker sits at (start_range, 0)
    dt = 1.0 / hz
    for i in range(int(seconds * hz)):
        t = i * dt
        s = true_scale * 0.48 * (v - 0.146) * min(1.0, max(0.0, t - delay) / 0.3)
        th += drift * dt
        x += s * math.cos(th) * dt
        y += s * math.sin(th) * dt
        if rnd.random() < dropout:
            continue                                                    # the marker is not found in every frame on a rugged floor
        dx, dy = start_range - x, -y
        r = math.hypot(dx, dy)
        yield t, r + rnd.gauss(0, noise), math.atan2(dy, dx) - th


def test_prior_speed_has_the_dead_zone_and_the_affine_shape():
    e = MotionEstimator()
    assert e.speed(0.3) == 0.0 and e.speed(0.0) == 0.0
    assert abs(e.speed(0.7) - 0.48 * (0.7 - 0.146)) < 1e-9 and abs(e.speed(1.0) - 0.41) < 0.01
    assert e.speed(-0.7) < 0                                            # the sign follows the command
    assert abs(e.speed(0.7, scale=0.8) - 0.8 * e.speed(0.7)) < 1e-9


def test_scale_converges_to_the_floor_factor_from_sparse_noisy_ranges():
    e = MotionEstimator()
    for k, v in enumerate((0.7, 0.6, 0.85)):                            # three drives; a stop between them closes each segment
        for t, r, b in drive(0.8, v, 4.0, seed=k):
            e.observe(t, r, b, v, 0.0)
        out = e.finish()
        assert out is not None and abs(out["ratio"] - 0.8) < 0.12, (v, out)
    assert abs(e.scale - 0.8) < 0.07 and e.updates == 3


def test_segments_that_are_too_short_slow_or_below_the_dead_zone_do_not_update():
    e = MotionEstimator()
    for t, r, b in drive(1.0, 0.7, 1.0):                                # 1 s: shorter than settle + min span
        e.observe(t, r, b, 0.7, 0.0)
    assert e.finish() is None and e.updates == 0
    for t, r, b in drive(1.0, 0.7, 4.0):
        e.observe(t, r, b, 0.3, 0.0)                                    # command below v_min: the robot would not move, nothing to learn
    assert e.finish() is None and e.updates == 0
    for t, r, b in drive(0.1, 0.7, 4.0):                                # an implausibly slow drive (a collision, a stall): ratio 0.1, rejected
        e.observe(t, r, b, 0.7, 0.0)
    assert e.finish() is None and e.updates == 0


def test_heading_drift_is_recovered_from_range_and_bearing_without_the_marker_orientation():
    for drift in (+0.15, -0.10, 0.0):                                   # rad/s, left +
        e = MotionEstimator()
        for t, r, b in drive(1.0, 0.7, 4.5, drift=drift, dropout=0.1):
            e.observe(t, r, b, 0.7, 0.0)
        out = e.finish()
        assert out is not None and abs(out["drift_rad_per_s"] - drift) < 0.05, (drift, out)


def test_startup_lag_is_measured_and_separated_from_the_steady_speed():
    e = MotionEstimator()
    for t, r, b in drive(1.0, 0.7, 5.0, delay=0.9, dropout=0.1):        # static friction: nothing moves for 0.9 s after the command
        e.observe(t, r, b, 0.7, 0.0)
    out = e.finish()
    assert out is not None and 0.5 < out["startup_lag_s"] < 1.5, out
    assert abs(out["ratio"] - 1.0) < 0.12                               # the steady speed is NOT reduced by the lag
