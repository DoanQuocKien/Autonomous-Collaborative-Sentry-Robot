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
    assert s["diag_frame_fraction_centred"] == 1.0 and s["frames_with_distance"] == len(p.rows)


def test_the_dead_reckoned_pose_follows_the_commands():
    p = new()
    for k in range(11):
        p.update(k / 10.0, [(1, box_at(3.0))])
    assert p.pose[0] > 0.1 and math.isfinite(p.pose[2])


def test_yaw_only_commands_are_short_pulses_and_none_inside_the_centre_band():
    p = new()
    p.update(0.0, [(1, box_at(1.2, u=320))])                             # lock, centred
    ws = [abs(p.update(0.05 * k, [(1, box_at(1.2, u=450))])[1]) for k in range(1, 13)]   # 1.2 m, person off to one side: hold-distance yaw-only
    assert sum(1 for w in ws if w > 0) <= len(ws) // 3 + 1               # at most one frame in three turns
    q = new()
    q.update(0.0, [(1, box_at(1.2, u=320))])
    assert all(q.update(0.05 * k, [(1, box_at(1.2, u=335))])[1] == 0.0 for k in range(1, 13))   # inside +/-10 %: no turn at all


def test_a_new_track_id_for_the_only_person_near_the_old_position_is_relocked_but_two_people_are_not():
    p = new()
    p.update(0.0, [(1, box_at(2.0, u=300))])
    p.update(0.1, [(9, box_at(2.1, u=330))])
    assert p.target_id == 9 and p.rows[-1]["event"] == "REACQUIRE"
    q = new()
    q.update(0.0, [(1, box_at(2.0, u=300))])
    q.update(0.1, [(8, box_at(2.1, u=330)), (9, box_at(2.2, u=350))])
    assert q.target_id == 1 and q.rows[-1]["mode"] == "NO_TARGET"        # two candidates: never guess
    r = new()
    r.update(0.0, [(1, box_at(2.0, u=300))])
    r.update(0.1, [(5, box_at(0.8, u=330))])
    assert r.target_id == 1                                              # far from the last distance: another person


def test_the_feet_row_offset_moves_the_floor_ray_up_so_the_person_reads_farther():
    box = box_at(1.5)
    near, _, _ = foot_point(ground, undist, box, (W, H))
    far, _, _ = foot_point(ground, undist, box, (W, H), feet_row_offset_px=4.0)
    assert far.forward_m > near.forward_m
    cut, c, _ = foot_point(ground, undist, (0, 0, 10, H), (W, H), feet_row_offset_px=4.0)
    assert cut is None and c                                             # feet cut off at the image bottom stays cut off


def test_a_yaw_pulse_expires_by_wall_clock_even_when_the_next_frame_stalls():
    from tools.pursue_live import YAW_PULSE_S, command_to_send
    cmd = {"v": 0.0, "w": -1.0, "t": 100.0}
    assert command_to_send(cmd, 100.0 + YAW_PULSE_S / 2) == (0.0, -1.0)      # inside the pulse
    assert command_to_send(cmd, 100.24) == (0.0, 0.0)                         # a stalled frame: the 0.25 s freshness alone would still turn
    assert command_to_send({"v": 0.5, "w": 0.1, "t": 100.0}, 100.2) == (0.5, 0.1)   # driving commands keep the normal freshness
    assert command_to_send({"v": 0.5, "w": 0.1, "t": 100.0}, 100.3) == (0.0, 0.0)


def test_save_run_keeps_evidence_with_an_unknown_end_voltage_and_never_overwrites(tmp_path):
    from tools.pursue_live import save_run
    p = new()
    p.update(0.1, [(1, box_at(2.0))])
    summary = dict(p.summary(), battery_v_start=12.0, battery_v_end=None, end_reason="error: OSError: ssh")
    d1 = save_run(str(tmp_path), "x", p.rows, summary, [(0.1, b"jpg")])
    d2 = save_run(str(tmp_path), "x", p.rows, summary, [])
    assert d1 != d2 and (d1 / "log.csv").exists() and (d1 / "frames" / "0.100.jpg").exists()
    assert '"battery_v_end": null' in (d1 / "summary.json").read_text()


def test_the_pose_integrates_the_interval_the_robot_actually_received_not_a_fixed_cap():
    p = new()
    p.update(0.0, [(1, box_at(3.0))])                                    # far: drives forward
    v, w = p.cmd
    assert v > 0
    p.update(0.24, [(1, box_at(3.0))])                                   # next frame 0.24 s later: the command was fresh for all of it
    expect, _ = WheelModel().body_speeds(v, w)
    assert abs(p.pose[0] - expect * 0.24 * math.cos(0.0)) < 5e-3
    q = new()
    q.update(0.0, [(1, box_at(3.0))])
    q.update(1.5, [(1, box_at(3.0))])                                    # a 1.5 s stall: only the 0.25 s freshness window moved the robot
    assert abs(q.pose[0] - expect * 0.25) < 5e-3
    d = Pursuit(InterceptionController(), WheelModel(), ground, undist, (W, H), integrate=False)
    d.update(0.0, [(1, box_at(3.0))])
    d.update(0.2, [(1, box_at(3.0))])
    assert d.pose == [0.0, 0.0, 0.0]                                     # dry-run / replay: no command was sent, the pose stays


def test_an_overridden_slow_frame_command_is_what_the_pose_and_the_log_describe():
    p = new()
    p.update(0.0, [(1, box_at(3.0))])
    assert p.rows[-1]["v"] > 0 and p.rows[-1]["v_req"] == p.rows[-1]["v"]
    p.override_command(0.0, 0.0)
    assert p.rows[-1]["suppressed"] == 1 and p.rows[-1]["v"] == 0.0 and p.rows[-1]["v_req"] > 0
    p.update(0.1, [(1, box_at(3.0))])
    assert p.pose[0] == 0.0                                              # nothing was sent, nothing moved


def test_centring_is_reported_in_full_width_units_and_by_time_with_coverage():
    p = new()
    p.update(0.0, [(1, box_at(2.0, u=368))])                             # 48 px off centre in 640 px: 7.5 % of the full width
    p.update(0.1, [(1, box_at(2.0, u=368))])
    s = p.summary()
    assert s["time_fraction_centred_of_tracked"] == 1.0                  # inside +/- 10 % of the full width
    q = new()
    q.update(0.0, [(1, box_at(2.0, u=320 + 70))])                        # 70 px = 10.9 %: outside
    q.update(0.1, [(1, box_at(2.0, u=320 + 70))])
    assert q.summary()["time_fraction_centred_of_tracked"] == 0.0
    r = new()
    r.update(0.0, [(1, box_at(1.2))])
    r.update(0.1, [(1, box_at(1.2))])
    for k in range(2, 7):
        r.update(0.1 + 0.5 * k, [])                                      # target lost: these half-seconds count in the run, not as tracked
    s = r.summary()
    assert s["coverage_tracked_fraction"] < 0.5 and s["time_fraction_distance_in_band_of_run"] < s["time_fraction_distance_in_band_of_tracked"]
    assert "NOT EVALUATED" in s["acceptance"]
    t = new()
    t.update(0.0, [(1, box_at(1.2))])
    t.update(10.0, [(1, box_at(1.2))])                                   # a 10 s gap earns at most TIME_CAP_S, not 10 s
    assert t.summary()["run_time_s"] <= 0.31


def test_inside_the_standoff_band_the_runner_stands_still_and_the_hold_can_trigger():
    p = new()
    for k in range(40):
        d = 1.30 + (0.08 if k % 2 else -0.08)                            # a still person whose range jitters +/- 0.08 m, median inside the 1.2 +/- 0.2 band
        v, w = p.update(k * 0.1, [(1, box_at(d))])
        assert v == 0.0 or k < 2                                        # no creeping after the first frames (the median needs a few samples)
    h = new()
    for k in range(60):
        h.update(k * 0.1, [(1, box_at(1.3 + 0.01 * (k % 2)))])           # a still person with a small jitter: HOLD after about 2 s
    assert h.rows[-1]["mode"] == "HOLD" and any(e == "TARGET_STATIONARY" for _, e in h.hold_events)
    q = new()
    for k in range(8):
        v, w = q.update(k * 0.1, [(1, box_at(1.7))])                    # outside the band: it still drives forward
    assert v > 0
    r = new()
    for k in range(8):
        v, w = r.update(k * 0.1, [(1, box_at(0.7))])                    # far inside the near limit: it still reverses
    assert v < 0
