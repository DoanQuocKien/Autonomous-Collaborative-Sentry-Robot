import math

from tools.scan_boards import camera_to_robot, pulse_angle, to_start_frame


def test_the_pulse_angle_is_the_fall_of_a_fixed_boards_bearing_median_over_boards():
    prev = {0: (math.radians(10), 3.0), 2: (math.radians(-50), 2.0), 5: (math.radians(80), 0.6)}      # id 5 is too near (0.6 m): ignored
    cur = {0: (math.radians(-15), 3.0), 2: (math.radians(-75), 2.0), 5: (math.radians(10), 0.6)}
    ang, n = pulse_angle(prev, cur)
    assert n == 2 and abs(math.degrees(ang) - 25.0) < 1e-9
    assert pulse_angle({0: (0.0, 3.0)}, {1: (0.0, 3.0)}) == (None, 0)                                  # no board in common
    ang, _ = pulse_angle({0: (math.radians(-165), 3.0)}, {0: (math.radians(170), 3.0)})                # across the +/-180 wrap
    assert abs(math.degrees(ang) - 25.0) < 1e-9


def test_a_point_ahead_of_a_robot_turned_left_goes_to_the_left_in_the_start_frame():
    x, y = to_start_frame(2.0, 0.0, math.radians(90))
    assert abs(x) < 1e-9 and abs(y - 2.0) < 1e-9
    x, y = to_start_frame(1.0, 1.0, 0.0)
    assert (x, y) == (1.0, 1.0)


def test_camera_frame_to_forward_and_left_with_a_pitched_camera():
    f, l = camera_to_robot([-0.5, 0.0, 2.0], 0.0)                              # 0.5 m to the right of the axis, 2 m ahead
    assert abs(f - 2.0) < 1e-9 and abs(l - 0.5) < 1e-9 or abs(l + (-0.5)) < 1e-9
    f, l = camera_to_robot([0.0, 0.0, 2.0], math.radians(-14))                 # looking up 14 deg: a point on the axis is nearer in forward
    assert abs(f - 2.0 * math.cos(math.radians(14))) < 1e-9
