from tools.link_cut_test import stop_time, threshold


def test_stop_time_is_the_first_moment_the_picture_stays_still_after_the_cut():
    series = [(0.0, 9.0), (0.1, 9.0), (0.2, 8.0), (0.3, 0.4), (0.4, 7.0), (0.5, 0.3), (0.6, 0.2), (0.7, 0.2)]
    thr = threshold(0.3, 9.0)                      # 0.3 + 25 % of the gap = 2.475
    assert abs(thr - 2.475) < 1e-9
    assert stop_time(series, 0.15, thr) == 0.5     # a single quiet frame (0.3 s) is not enough, two in a row are
    assert stop_time(series, 0.6, thr) == 0.6
    assert stop_time([(0.0, 9.0), (0.1, 9.0)], 0.0, thr) is None   # never stops
