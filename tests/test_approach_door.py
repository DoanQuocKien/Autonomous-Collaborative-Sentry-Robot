import pytest

from tools.approach_door import next_action, polygon_area, range_from_area


def test_area_scale_and_polygon():
    assert polygon_area([(0, 0), (4, 0), (4, 3), (0, 3)]) == 12
    assert range_from_area(4.0, 1.0, 3.0) == pytest.approx(1.5)      # four times the area = half the range
    with pytest.raises(ValueError):
        range_from_area(0, 1.0, 3.0)


def test_next_action():
    assert next_action(0.0, 3.4, 2.0, 4) == "drive"
    assert next_action(10.0, 3.4, 2.0, 4) == "turn_left" and next_action(-10.0, 3.4, 2.0, 4) == "turn_right"
    assert next_action(10.0, 1.9, 2.0, 4) == "done"                    # arrival wins over a bearing error
