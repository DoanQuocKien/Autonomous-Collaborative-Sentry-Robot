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


def test_trim_is_off_by_default_and_turns_left_when_positive():
    from common.mixing import apply_trim
    assert apply_trim(0.5, 0.5, 0.0) == (0.5, 0.5)
    left, right = apply_trim(0.5, 0.5, 0.02)          # a robot that pulls to the right: slow the left wheel, speed up the right
    assert left < 0.5 < right and abs(left - 0.49) < 1e-9 and abs(right - 0.51) < 1e-9
    assert apply_trim(0.0, 0.0, 0.1) == (0.0, 0.0)    # no creeping when stopped


def test_trim_keeps_the_speed_cap_and_the_turn_ratio_when_a_wheel_would_exceed_1():
    from common.mixing import apply_trim
    left, right = apply_trim(1.0, 1.0, 0.1)           # right would be 1.1: both are rescaled, nothing above 1
    assert max(abs(left), abs(right)) == 1.0 and abs(left / right - 0.9 / 1.1) < 1e-9


def test_check_drive_rejects_a_big_trim():
    import pytest
    from common.mixing import check_drive
    check_drive(0.3, 0.12, 1.0, 0.05)
    for bad in (0.3, -0.25, float("nan")):
        with pytest.raises(ValueError):
            check_drive(0.3, 0.12, 1.0, bad)
