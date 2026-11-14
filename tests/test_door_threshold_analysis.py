import numpy as np

from tools.door_threshold_analysis import pooled_tar, window_rates


def rows(window, a, b):
    return [{"window": window, "cos_A": str(x), "cos_B": str(y)} for x, y in zip(a, b)]


def test_pooled_tar_counts_a_missing_face_as_a_miss():
    clips = {("A", "1.8_straight"): [0.6, 0.3, float("nan"), 0.5]}
    assert pooled_tar(clips, list(clips), 0.45) == 0.5


def test_window_rules_use_consecutive_frames():
    R = {"A": rows("1.8_straight", [0.2, 0.6, 0.2, 0.2], [0.1, 0.1, 0.1, 0.1]),
         "B": rows("1.8_straight", [0.1, 0.1, 0.1, 0.1], [0.5, 0.5, 0.5, 0.5])}
    tar, far, mx, ng, ni = window_rates(R, 2, "max", 0.45)          # A: windows (0.2,0.6) and (0.6,0.2) pass, (0.2,0.2) fails; B: all 3 pass
    assert ng == 6 and np.isclose(tar, 5 / 6) and far == 0.0 and np.isclose(mx, 0.1)
    tar_mean = window_rates(R, 2, "mean", 0.45)[0]                   # mean of (0.2, 0.6) = 0.4 < 0.45: the mean rule is stricter than max
    assert tar_mean < tar
