import math

from common.mixing import deadzone, mix


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


def test_deadzone():
    assert deadzone(0.1, 0.3) == 0.0 and deadzone(-0.29, 0.3) == 0.0
    assert deadzone(0.3, 0.3) == 0.3 and deadzone(-0.5, 0.3) == -0.5
    assert deadzone(0.01, 0.0) == 0.01
