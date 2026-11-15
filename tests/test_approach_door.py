import pytest

from tools.approach_door import next_action, polygon_area, range_from_area, video_is_fresh


def test_area_scale_and_polygon():
    assert polygon_area([(0, 0), (4, 0), (4, 3), (0, 3)]) == 12
    assert range_from_area(4.0, 1.0, 3.0) == pytest.approx(1.5)      # four times the area = half the range
    with pytest.raises(ValueError):
        range_from_area(0, 1.0, 3.0)


def test_next_action():
    assert next_action(0.0, 3.4, 2.0, 4) == "drive"
    assert next_action(10.0, 3.4, 2.0, 4) == "turn_left" and next_action(-10.0, 3.4, 2.0, 4) == "turn_right"
    assert next_action(10.0, 1.9, 2.0, 4) == "done"                    # arrival wins over a bearing error


def test_wider_window_and_aim_offset():
    assert next_action(7.0, 3.0, 2.0, 8) == "drive" and next_action(9.0, 3.0, 2.0, 8) == "turn_left"      # a 4 deg window made every 14 deg pulse overshoot
    assert next_action(10.0, 3.0, 2.0, 8, aim_offset_deg=2.75) == "drive"                                  # +2.75 deg centre: the door is expected to drift right during the burst
    assert next_action(-6.0, 3.0, 2.0, 8, aim_offset_deg=2.75) == "turn_right"


def test_video_freshness():
    assert video_is_fresh(10.0, 10.4) and not video_is_fresh(10.0, 10.6)
    assert not video_is_fresh(None, 10.0) and not video_is_fresh(11.0, 10.0)        # no frame yet, or a clock that went backwards


def test_area_exponent():
    assert range_from_area(4.0, 1.0, 3.0, exponent=2.0) == pytest.approx(1.5)
    assert range_from_area(2.808, 1.0, 3.13, exponent=1.6) == pytest.approx(1.64, abs=0.01)      # the 2026-11-12 run: tape 1.62 m
    with pytest.raises(ValueError):
        range_from_area(1.0, 1.0, 3.0, exponent=0)


def test_distance_bound_cuts_a_runaway_but_not_the_real_runs():
    from tools.approach_door import DISTANCE_BOUND_MARGIN_M
    from tools.drive_model import drive_distance_m
    per_burst = drive_distance_m(0.85, 0.6)
    for r0, bursts in ((3.42, 10), (3.13, 8), (2.63, 4), (2.50, 3)):          # ap_1, ap2_2, ap3_1, ap4_1: none may be cut short
        assert per_burst * bursts < r0 - 2.0 + DISTANCE_BOUND_MARGIN_M, (r0, bursts)
    assert per_burst * 20 >= 3.42 - 2.0 + DISTANCE_BOUND_MARGIN_M              # 20 bursts (the old only limit) are about 4.2 m: the bound stops it first
