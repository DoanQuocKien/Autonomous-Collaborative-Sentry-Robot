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
