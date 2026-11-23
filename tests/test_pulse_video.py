import numpy as np

from tools.pulse_video import motion_bursts, pulse_events, segments

FPS = 240


def _clip():
    rng = np.random.RandomState(0)                          # seeded: the noise is the same every run
    n = 1200
    bright = np.full(n, 20.0)
    motion = rng.uniform(0.0, 0.4, n)
    for s in (300, 800):                                    # two flashes of 96 frames (0.4 s)
        bright[s:s + 96] = 235.0
        motion[s + 12:s + 12 + 110] = 6.0 + rng.uniform(0, 1, 110)   # wheel starts 50 ms late, stops 108 ms after the flash ends
    return bright, motion


def test_segments():
    assert segments([0, 1, 1, 0, 1]) == [(1, 3), (4, 5)]


def test_pulse_events_with_flash():
    rows = pulse_events(*_clip(), FPS)
    assert len(rows) == 2
    for r in rows:
        assert abs(r["flash_ms"] - 400) < 5
        assert abs(r["start_delay_ms"] - 50) < 10
        assert abs(r["motion_ms"] - 458) < 15
        assert abs(r["stop_lag_ms"] - 108) < 15


def test_wheel_only_bursts():
    _, motion = _clip()
    b = motion_bursts(motion, FPS)
    assert len(b) == 2
    assert all(abs((e - s) / FPS * 1000 - 458) < 15 for s, e in b)


def test_no_flash_gives_nothing():
    assert pulse_events(np.full(100, 30.0), np.zeros(100), FPS) == []
