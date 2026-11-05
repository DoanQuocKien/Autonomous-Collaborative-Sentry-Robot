import math

from sentry.nav.controllers import InterceptionController
from sentry.nav.explore import Command, ExploreSettings, legal
from sentry.nav.wheel_model import WheelModel
from sentry.perception.camera import GroundPoint
from tools.pursue_live import Pursuit, foot_point

W, H = 640, 480


def ground(u, v):
    """A fake floor: the lower the foot point in the image, the nearer (forward = 150 / (v - 200) m), straight ahead of u = 320."""
    if v <= 210:
        return None
    fwd = 150.0 / (v - 200.0)
    return GroundPoint(fwd, (320.0 - u) / 320.0 * fwd * 0.5)


def undist(pts):
    return [tuple(p) for p in pts]


def box_at(dist_m, u=320.0, h=200.0):
    v = 200.0 + 150.0 / dist_m
    return (u - h / 4, v - h, u + h / 4, v)


def new():
    return Pursuit(InterceptionController(), WheelModel(), ground, undist, (W, H))


def test_a_far_person_is_followed_a_near_one_is_backed_away_from_and_every_command_is_legal():
    p = new()
    s = ExploreSettings()
    v, w = p.update(0.1, [(7, box_at(2.8))])
    assert v > 0 and p.target_id == 7                                    # 2.8 m: drive towards the person
    p2 = new()
    v, w = p2.update(0.1, [(3, box_at(0.7))])
    assert v < 0                                                         # too close: reverse
    for t in range(2, 40):
        p.update(t / 10.0, [(7, box_at(2.0 - 0.02 * t, u=300 + t))])
    assert all(legal(Command(r["v"], r["w"], "", ""), s) for r in p.rows)


def test_the_largest_person_in_range_is_locked_and_kept_by_id_even_when_another_walks_in():
    p = new()
    p.update(0.1, [(1, box_at(3.0)), (2, box_at(1.5, u=100))])
    assert p.target_id == 2                                              # the larger (nearer) box
    p.update(0.2, [(1, box_at(1.0)), (2, box_at(1.6, u=100))])
    assert p.target_id == 2 and p.rows[-1]["track_id"] == 2


def test_no_person_or_a_lost_person_stops_and_ends_the_run_after_the_limit():
    p = new()
    p.update(0.1, [(1, box_at(2.5))])
    assert p.update(0.2, []) == (0.0, 0.0)
    for k in range(3, 60):
        p.update(k / 10.0, [])
    assert p.end_reason and "lost" in p.end_reason


def test_feet_cut_off_by_the_image_bottom_means_no_translation():
    p = new()
    p.update(0.1, [(1, box_at(2.5))])
    v, w = p.update(0.2, [(1, (200.0, 100.0, 300.0, float(H)))])
    assert v == 0.0 and p.rows[-1]["mode"] == "YAW_ONLY" and p.rows[-1]["feet_cut"] == 1
    assert foot_point(ground, undist, (200, 100, 300, H), (W, H))[1] is True


def test_a_person_who_stands_still_triggers_hold_after_about_two_seconds_with_no_translation():
    p = new()
    for k in range(1, 50):
        p.update(k / 10.0, [(1, box_at(1.2))])                           # 10 Hz, standing at 1.2 m, robot not moving
    modes = [r["mode"] for r in p.rows]
    assert modes[-1] == "HOLD" and p.rows[-1]["v"] == 0.0 and any(e == "TARGET_STATIONARY" for _, e in p.hold_events)
    first = next(r["t"] for r in p.rows if r["mode"] == "HOLD")
    assert 1.5 < first < 3.5
    s = p.summary()
    assert s["fraction_centred_within_10pct"] == 1.0 and s["frames_with_distance"] == len(p.rows)


def test_the_dead_reckoned_pose_follows_the_commands():
    p = new()
    for k in range(11):
        p.update(k / 10.0, [(1, box_at(3.0))])
    assert p.pose[0] > 0.1 and math.isfinite(p.pose[2])
