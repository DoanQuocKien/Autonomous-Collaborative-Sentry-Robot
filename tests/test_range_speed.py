import random

import pytest

from tools.range_speed import fit_speed


def test_fit_recovers_the_speed_and_skips_the_start_up():
    rng = random.Random(0)
    # a robot that starts at 2.4 m, takes 0.4 s to reach 0.22 m/s, with 5 mm of range noise
    pts, r = [], 2.4
    for k in range(60):
        t = k * 0.05
        v = 0.22 * min(1.0, t / 0.4)
        r -= v * 0.05
        pts.append((t, r + rng.gauss(0, 0.005)))
    speed, sd, n = fit_speed(pts, skip_s=0.5)
    assert speed == pytest.approx(0.22, abs=0.01) and 0.002 < sd < 0.01 and n < 60


def test_reverse_gives_a_negative_speed_and_short_runs_return_none():
    pts = [(k * 0.1, 2.0 + 0.15 * k * 0.1) for k in range(20)]
    speed, _, _ = fit_speed(pts, skip_s=0.3)
    assert speed == pytest.approx(-0.15, abs=0.001)
    assert fit_speed(pts[:3], skip_s=0.0)[0] is None
    assert fit_speed([(0.0, 2.0)] * 6, skip_s=0.0)[0] is None            # no time spread: no slope
