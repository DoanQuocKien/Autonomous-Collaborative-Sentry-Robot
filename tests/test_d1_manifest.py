import numpy as np

from tools.d1_manifest import longest_still


def test_longest_still_picks_the_long_quiet_stretch():
    # 30 frames at 10 fps: moving (diff 8) for 5, still for 15, moving for 4, still for 5 (diffs are n-1 = 29 values)
    diffs = np.array([8.0] * 5 + [0.3] * 15 + [8.0] * 4 + [0.3] * 5)
    times = np.arange(30) / 10.0
    k, j = longest_still(times, diffs)
    assert 4 <= k <= 7 and 18 <= j <= 21     # about frames 5..20


def test_all_moving_gives_none():
    assert longest_still(np.arange(21) / 10.0, np.full(20, 9.0)) is None
