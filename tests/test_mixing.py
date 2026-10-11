import math

import pytest

from common.mixing import check_drive, deadzone, mix


def test_straight_and_pivot_directions():
    assert mix(1, 0) == (1, 1)
    assert mix(0, 1) == (-1, 1)      # positive w = left turn (matches jetbot Robot.left)
    assert mix(0, -1) == (1, -1)


def test_saturation_rescales_not_clips():
    left, right = mix(-1.0, 0.8)     # the spec's evasion command
    assert math.isclose(left, -1.0) and math.isclose(right, -0.2 / 1.8)
    assert math.isclose(right / left, 0.2 / 1.8)   # turn ratio preserved (clipping would give 0.2)
    assert max(abs(left), abs(right)) <= 1.0


def test_within_range_unchanged():
    assert mix(0.4, 0.2) == (0.4 - 0.2, 0.4 + 0.2)


def test_gain_k():
    assert mix(0, 0.5, k=2.0) == (-1.0, 1.0)


def test_non_finite_stops():
    assert mix(float("nan"), 0) == (0.0, 0.0)
    assert mix(0, float("inf")) == (0.0, 0.0)


def test_deadzone_zeroes_values_below_min_pwm_only():
    assert deadzone(0.09, 0.12) == 0.0 and deadzone(-0.09, 0.12) == 0.0
    assert deadzone(0.12, 0.12) == 0.12 and deadzone(-0.3, 0.12) == -0.3
    assert deadzone(0.05, 0.0) == 0.05                               # min_pwm 0: nothing is zeroed


@pytest.mark.parametrize("max_speed,min_pwm,k", [
    (-0.3, 0.0, 1.0), (1.5, 0.0, 1.0), (0.3, 0.3, 1.0), (0.3, 0.5, 1.0), (0.3, -0.1, 1.0),
    (float("nan"), 0.0, 1.0), (0.3, 0.1, float("nan")), (0.3, 0.1, 0.0), (True, 0.0, 1.0),
])
def test_check_drive_rejects_unsafe_settings(max_speed, min_pwm, k):
    with pytest.raises(ValueError):
        check_drive(max_speed, min_pwm, k)
