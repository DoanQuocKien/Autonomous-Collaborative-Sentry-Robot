import math
import random

import pytest

from sentry.nav.explore import ExploreSettings, Explorer, fresh_command, legal
from sentry.nav.wheel_model import WheelModel
from sentry.perception.camera import GroundPoint
from sentry.perception.obstacle import Detection, Obstacle, ObstacleResult, repulsive_w

S = ExploreSettings()
W, H = 640, 480


def result(*obstacles, w=0.0):
    return ObstacleResult(0.0, tuple(obstacles), w, None)


def resolved(forward, left):
    return Obstacle(Detection(56, 0.9, (300.0, 200.0, 340.0, 260.0)), GroundPoint(forward, left))


def unresolved(box, reason="reflection_unresolved"):
    return Obstacle(Detection(56, 0.9, box), None, reason)


def test_clear_view_drives_forward_above_the_dead_zone():
    ex = Explorer(S, (W, H))
    c = ex.step(result(), (0, 0, 0), 0.05)
    assert (c.state, c.v, c.w) == ("FORWARD", S.v_forward, 0.0) and legal(c, S)


def test_a_near_obstacle_on_the_left_makes_the_robot_spin_right_and_it_needs_clear_frames_to_resume():
    ex = Explorer(S, (W, H))
    c = ex.step(result(resolved(0.4, 0.15)), (0, 0, 0), 0.05)
    assert c.state == "TURN" and c.v == 0.0 and c.w < 0 and legal(c, S)
    for _ in range(S.clear_frames - 1):                       # clear again, but not for long enough yet
        assert ex.step(result(), (0, 0, 0), 0.05).state == "TURN"
    assert ex.step(result(), (0, 0, 0), 0.05).state == "FORWARD"
    assert ex.step(result(resolved(0.4, 0.15)), (0, 0, 0), 0.05).state == "TURN"        # and it blocks again


def test_a_far_obstacle_only_steers():
    ex = Explorer(S, (W, H))
    c = ex.step(result(resolved(0.58, 0.1), w=-0.05), (0, 0, 0), 0.05)
    assert c.state == "FORWARD" and c.w == pytest.approx(-0.05) and c.v == S.v_forward


def test_steering_never_pushes_a_wheel_into_the_dead_zone():
    ex = Explorer(S, (W, H))
    c = ex.step(result(w=1.0), (0, 0, 0), 0.05)
    assert c.w == pytest.approx(S.w_forward_max) and legal(c, S)


def test_an_obstacle_without_a_distance_blocks_when_low_in_the_image_and_is_ignored_when_far():
    ex = Explorer(S, (W, H))
    near = unresolved((100.0, 220.0, 220.0, 400.0))             # chair on the left, box reaches y = 400 of 480
    c = ex.step(result(near), (0, 0, 0), 0.05)
    assert c.state == "TURN" and c.w < 0                          # on the left -> spin right
    ex2 = Explorer(S, (W, H))
    far = unresolved((100.0, 200.0, 140.0, 250.0))                # small, high in the image: far away
    assert ex2.step(result(far), (0, 0, 0), 0.05).state == "FORWARD"
    cut = unresolved((400.0, 100.0, 639.0, 300.0), "border_truncated")
    assert Explorer(S, (W, H)).step(result(cut), (0, 0, 0), 0.05).w > 0     # on the right, truncated at the border -> spin left


def test_outside_the_box_the_robot_turns_back_to_the_centre():
    ex = Explorer(S, (W, H))
    c = ex.step(result(), (2.0, 0.0, 0.0), 0.05)                  # beyond the box, facing away
    assert c.state == "RETURN" and c.v == 0.0 and c.w != 0.0
    c = Explorer(S, (W, H)).step(result(), (2.0, 0.0, math.pi), 0.05)   # facing the centre: drive on
    assert c.state == "RETURN" and c.v == S.v_forward and legal(c, S)


def test_stops_without_a_frame_when_stuck_and_at_the_time_limit():
    assert Explorer(S, (W, H)).step(None, (0, 0, 0), 0.05)[:2] == (0.0, 0.0)
    ex = Explorer(S, (W, H))
    blocker = result(resolved(0.3, 0.1))
    c = None
    for _ in range(int(S.max_spin_s / 0.05) + 5):
        c = ex.step(blocker, (0, 0, 0), 0.05)
    assert c.state == "STOP" and c.reason == "stuck"
    assert Explorer(ExploreSettings(max_time_s=1.0), (W, H)).step(result(), (0, 0, 0), 2.0).reason == "time"


def test_every_command_is_legal_over_random_scenes():
    rng = random.Random(1)
    ex = Explorer(S, (W, H), seed=2)
    for _ in range(3000):
        obs = [resolved(rng.uniform(0.05, 3.0), rng.uniform(-1.5, 1.5)) for _ in range(rng.randint(0, 3))]
        if rng.random() < 0.3:
            x0 = rng.uniform(0, 600)
            obs.append(unresolved((x0, rng.uniform(0, 300), x0 + 30, rng.uniform(300, 479))))
        pose = (rng.uniform(-3, 3), rng.uniform(-3, 3), rng.uniform(-math.pi, math.pi))
        pts = [o.ground for o in obs if o.ground is not None]
        c = ex.step(result(*obs, w=repulsive_w(pts, 0.6)), pose, 0.05)
        assert legal(c, S), c


# ---- closed loop: a simulated robot in a small room of round obstacles, seen through a fake camera -----------------
def fake_camera(x, y, yaw, circles, max_range=3.0, half_fov=math.radians(75)):
    seen = []
    for cx, cy, r in circles:
        d = math.hypot(cx - x, cy - y)
        bearing = math.atan2(cy - y, cx - x) - yaw
        bearing = math.atan2(math.sin(bearing), math.cos(bearing))
        surface = d - r
        if abs(bearing) < half_fov and 0.05 < surface < max_range and surface * math.cos(bearing) > 0:
            seen.append(Obstacle(Detection(56, 0.9, (300.0, 200.0, 340.0, 260.0)),
                                 GroundPoint(surface * math.cos(bearing), surface * math.sin(bearing))))
    return seen


def run_sim(circles, seconds=150.0, dt=0.05, start=(0.0, 0.0, 0.0), settings=S, miss=0.0, delay_s=0.0, seed=5):
    model = WheelModel()
    ex = Explorer(settings, (W, H), seed=3)
    rng, queue = random.Random(seed), []
    x, y, yaw = start
    min_clear, max_extent, path, states = 9.9, 0.0, 0.0, set()
    for _ in range(int(seconds / dt)):
        seen = [o for o in fake_camera(x, y, yaw, circles) if rng.random() >= miss]      # each obstacle can be missed in a frame
        queue.append(seen)
        seen = queue.pop(0) if len(queue) > int(round(delay_s / dt)) else []                # a delayed view: the robot acts on old frames
        pts = [o.ground for o in seen]
        c = ex.step(result(*seen, w=repulsive_w(pts, 0.6)), (x, y, yaw), dt)
        assert legal(c, settings), c
        states.add(c.state)
        if c.state == "STOP":
            break
        v, w = model.body_speeds(c.v, c.w)
        x, y, yaw = x + v * math.cos(yaw) * dt, y + v * math.sin(yaw) * dt, yaw + w * dt
        path += abs(v) * dt
        max_extent = max(max_extent, abs(x), abs(y))
        min_clear = min(min_clear, min(math.hypot(cx - x, cy - y) - r for cx, cy, r in circles))
    return min_clear, max_extent, path, states


def test_closed_loop_never_touches_an_obstacle_stays_near_the_box_and_keeps_moving():
    circles = [(1.0, 0.3, 0.20), (0.4, -1.0, 0.25), (-1.0, 0.8, 0.20), (-0.8, -0.9, 0.20), (1.2, -0.6, 0.15), (0.2, 1.2, 0.20)]
    clear, extent, path, states = run_sim(circles)
    assert clear > 0.12, "robot came within %.2f m of an obstacle surface" % clear        # the robot body is about 0.1 m
    assert extent < S.box_half_m + 0.9
    assert path > 8.0
    assert {"FORWARD", "TURN"} <= states


def test_closed_loop_from_several_starts():
    circles = [(1.0, 0.0, 0.25), (-0.3, 1.1, 0.2), (0.0, -1.0, 0.2), (-1.1, -0.2, 0.2)]
    for start in ((0.0, 0.0, 0.0), (0.0, 0.0, math.pi / 2), (-0.5, 0.4, math.pi), (0.3, -0.3, -2.0)):
        clear, extent, path, _ = run_sim(circles, seconds=90.0, start=start)
        assert clear > 0.12 and extent < S.box_half_m + 0.9, (start, clear, extent)


CIRCLES = [(1.0, 0.3, 0.20), (0.4, -1.0, 0.25), (-1.0, 0.8, 0.20), (-0.8, -0.9, 0.20), (1.2, -0.6, 0.15), (0.2, 1.2, 0.20)]


def test_closed_loop_with_detector_dropouts_and_latency():
    for miss, delay in ((0.4, 0.0), (0.0, 0.3), (0.3, 0.2)):
        clear, extent, path, _ = run_sim(CIRCLES, seconds=120.0, miss=miss, delay_s=delay)
        assert clear > 0.25, "miss %.1f delay %.1f s: %.2f m" % (miss, delay, clear)
        assert path > 5.0


def test_a_stalled_control_loop_puts_a_stop_on_the_wire():
    assert fresh_command(0.55, 0.1, t_set=10.0, now=10.2) == (0.55, 0.1)
    assert fresh_command(0.55, 0.1, t_set=10.0, now=10.3) == (0.0, 0.0)
