import math

from tools.tape_angle import tape_yaw_deg

FX, CX = 310.0, 286.0


def test_tape_along_the_axis_has_no_yaw_and_a_rotated_one_is_measured():
    # a tape along the optical axis, 0.1 m to the side of it, on a level camera at H = 0.1 m (horizon row 240)
    def px(forward, side, yaw):
        a = math.radians(yaw)
        x_cam, z = side + forward * math.sin(a), forward * math.cos(a)   # tape rotated by yaw about the lens foot
        return CX + FX * x_cam / z, 240 + 306 * 0.1 / z
    for yaw in (0.0, 3.0, -5.0):
        p0, p1 = px(0.5, 0.0, yaw), px(3.0, 0.0, yaw)
        assert abs(tape_yaw_deg(p0, p1, CX, FX, 240) - yaw) < 0.05
