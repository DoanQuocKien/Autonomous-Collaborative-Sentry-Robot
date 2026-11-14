import math

import numpy as np

from sentry.nav.controllers import InterceptionController
from sentry.nav.wheel_model import WheelModel
from sentry.perception.body_range import iou, trunk_range
from sentry.perception.camera import GroundPoint
from tools.pursue_live import Pursuit

W, H = 640, 480
K = np.array([[306.0, 0, 320.0], [0, 306.0, 240.0], [0, 0, 1.0]])
ident = lambda p: np.asarray(p, dtype=float)


def person(z, x_off=0.0, y_off=0.0, trunk_m=0.50):
    """17 keypoints of a frontal person at camera depth z (pitch 0): shoulders 0.38 m wide, hips 0.30 m wide, trunk trunk_m long, centre at (x_off, y_off) m from the optical axis."""
    k = np.zeros((17, 2))
    f = K[0, 0]
    cx, cy = K[0, 2] + f * x_off / z, K[1, 2] + f * y_off / z
    half = f * trunk_m / z / 2
    k[5], k[6] = (cx - f * 0.19 / z, cy - half), (cx + f * 0.19 / z, cy - half)
    k[11], k[12] = (cx - f * 0.15 / z, cy + half), (cx + f * 0.15 / z, cy + half)
    return k, np.ones(17)


def test_the_trunk_length_gives_the_range_and_the_side_offset():
    k, c = person(2.0, x_off=0.3)
    fwd, left = trunk_range(k, c, ident, K, 0.0)
    assert abs(fwd - 2.0) < 0.01 and abs(left + 0.3) < 0.02                  # right of the axis = negative left
    k, c = person(1.2)
    assert abs(trunk_range(k, c, ident, K, 0.0)[0] - 1.2) < 0.01
    k, c = person(2.0)
    fwd_p = trunk_range(k, c, ident, K, math.radians(-4.5))[0]               # camera looking up: forward = Z (cos p - sin p y)
    assert abs(fwd_p - 2.0) < 0.05


def test_a_keypoint_that_is_not_confident_or_a_tiny_trunk_gives_no_range():
    k, c = person(2.0)
    c[11] = 0.5
    assert trunk_range(k, c, ident, K, 0.0) is None
    k, c = person(60.0)                                                      # trunk of about 2.5 px
    assert trunk_range(k, c, ident, K, 0.0) is None


def test_iou_basic():
    assert iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0 and iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0


def ground(u, v):
    if v <= 210:
        return None
    fwd = 150.0 / (v - 200.0)
    return GroundPoint(fwd, (320.0 - u) / 320.0 * fwd * 0.5)


def box_at(dist_m, u=320.0, h=200.0):
    v = 200.0 + 150.0 / dist_m
    return (u - h / 4, v - h, u + h / 4, v)


def test_the_runner_uses_the_trunk_range_when_the_keypoints_are_confident_and_falls_back_to_the_foot_row():
    trunk_fn = lambda kx, kc: trunk_range(kx, kc, ident, K, 0.0)
    p = Pursuit(InterceptionController(), WheelModel(), ground, ident, (W, H), trunk_fn=trunk_fn)
    b = box_at(1.2)                                                          # the foot row says 1.2 m
    k, c = person(2.0)                                                       # the trunk says 2.0 m
    for i in range(12):
        p.update(i * 0.05, [(1, b)], [(b, k, c)])
    assert p.rows[-1]["range_src"] == "trunk" and abs(p.rows[-1]["dist_m"] - 2.0) < 0.05 and abs(p.rows[-1]["foot_forward_m"] - 1.2) < 0.05
    c2 = c.copy()
    c2[5] = 0.2
    p.update(1.0, [(1, b)], [(b, k, c2)])                                    # keypoint lost: foot row again
    assert p.rows[-1]["range_src"] == "foot" and abs(p.rows[-1]["dist_m"] - 1.2) < 0.05
    q = Pursuit(InterceptionController(), WheelModel(), ground, ident, (W, H))
    q.update(0.0, [(1, b)])
    assert q.rows[-1]["range_src"] is None and abs(q.rows[-1]["dist_m"] - 1.2) < 0.05    # default: foot only, as before


def test_the_trunk_range_is_a_causal_median_so_one_bad_frame_does_not_move_the_robot():
    trunk_fn = lambda kx, kc: trunk_range(kx, kc, ident, K, 0.0)
    p = Pursuit(InterceptionController(), WheelModel(), ground, ident, (W, H), trunk_fn=trunk_fn)
    b = box_at(1.2)
    for i in range(10):
        k, c = person(2.0)
        p.update(i * 0.05, [(1, b)], [(b, k, c)])
    k, c = person(1.0)                                                       # one frame with a wrong trunk (a lean)
    p.update(0.5, [(1, b)], [(b, k, c)])
    assert abs(p.rows[-1]["dist_m"] - 2.0) < 0.1
