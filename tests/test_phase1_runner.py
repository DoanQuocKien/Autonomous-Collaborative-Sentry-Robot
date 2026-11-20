import math

from sentry.app.deploy_runner import wrap
from sentry.app.phase1_runner import Phase1Runner, Phase1Settings
from sentry.app.state_machine import State, StateMachine, StateMachineConfig
from sentry.nav.declared_room import declared_grid
from sentry.nav.explore import Command, ExploreSettings, legal
from sentry.nav.gridmap import OccupancyGrid
from sentry.nav.vantage import VantageSelector
from sentry.nav.wheel_model import WheelModel
from sentry.perception.entrance import EntranceResult

DT = 1.0 / 30.0
BOX = (-1.0, -2.0, 5.0, 2.0)
WALLS = [(5.1, -2.1, 5.1, 2.1), (-1.1, -2.1, -1.1, 2.1), (-1.1, 2.1, 5.1, 2.1), (-1.1, -2.1, 5.1, -2.1)]
DOOR = (5.1, 0.0)


class Speaker:
    def __init__(self):
        self.played = []

    def play(self, clip):
        self.played.append(clip)
        return True


def run(start=(0.0, 0.0, 2.5), box=BOX, never_see=False, bearing_error=0.0, find_timeout=45.0, handshake_at=30.0, seconds=200.0, door=DOOR):
    g = declared_grid(box, WALLS, door, grid=OccupancyGrid(0.1, 12.0, 8.0, (-3.0, -4.0)))
    sp, sm = Speaker(), StateMachine(StateMachineConfig())
    r = Phase1Runner(sm, sp, g, VantageSelector(1.8, 2.7, 0.15), door, (2.0, 0.0), settings=Phase1Settings(find_timeout_s=find_timeout))
    model = WheelModel()
    x, y, yaw = start
    cmds, t = [], 0.0
    r.start(0.0)
    while t < seconds and not r.failed:
        to_door = math.atan2(door[1] - y, door[0] - x)
        rel = wrap(to_door - yaw)
        seen = (not never_see) and abs(rel) < 0.5
        r.observe_entrance(EntranceResult(seen, 30, None, (rel + bearing_error) if seen else None, None), t)
        v, w = r.step(t, (x, y, yaw), t >= handshake_at)
        cmds.append((t, v, w))
        v_m, w_r = model.body_speeds(v, w)
        x += v_m * math.cos(yaw) * DT
        y += v_m * math.sin(yaw) * DT
        yaw = wrap(yaw + w_r * DT)
        t += DT
        if sm.state == State.STANDBY:
            break
    return r, sm, sp, cmds, (x, y, yaw), t


def test_the_whole_chain_scans_finds_the_door_picks_a_sweet_spot_and_deploys_to_standby():
    r, sm, sp, cmds, pose, t = run()
    assert r.failed is None and r.phase == "DEPLOY" and sm.state == State.STANDBY
    vp = r.vantage
    assert 1.8 <= vp.door_distance_m <= 2.7 and vp.boundary_distance_m < 0.6        # the spec's conditions, with the distance margin
    px, py, _ = [p for _, n, p in r.events if n == "VANTAGE_REACHED"][0]
    assert math.hypot(px - vp.x_m, py - vp.y_m) <= 0.14                             # it stopped on the chosen spot
    assert sp.played == ["place_camera", "camera_verified"]
    assert [s for _, s in r.log] == ["APPROACH_VANTAGE", "WAIT_CAMERA", "RETRACT", "STANDBY"]
    s = ExploreSettings()
    assert all(legal(Command(v, w, "", ""), s) for _, v, w in cmds)


def test_the_scan_is_short_pulses_with_still_holds_between_them():
    r, sm, sp, cmds, pose, t = run(never_see=True, find_timeout=3.0)
    scan = [(v, w) for tt, v, w in cmds if tt < 2.0]
    assert set(scan) <= {(0.0, 0.45), (0.0, 0.0)} and (0.0, 0.45) in scan and scan.count((0.0, 0.0)) > scan.count((0.0, 0.45))


def test_no_entrance_in_view_fails_after_the_scan_timeout_and_stops():
    r, sm, sp, cmds, pose, t = run(never_see=True, find_timeout=8.0)
    assert r.failed.startswith("entrance not found") and 8.0 <= t < 9.0 and sp.played == [] and r.step(t, pose) == (0.0, 0.0)


def test_a_room_with_no_sweet_spot_fails_with_a_reason_instead_of_driving_anywhere():
    r, sm, sp, cmds, pose, t = run(box=(-1.0, -1.0, 1.0, 1.0), start=(0.0, 0.0, 0.0))
    assert r.failed.startswith("no sweet spot") and sp.played == [] and r.vantage is None


def test_an_entrance_seen_far_from_the_declared_door_is_noted_and_the_run_goes_on():
    r, sm, sp, cmds, pose, t = run(bearing_error=0.9)                               # the detector's bearing is 52 deg off
    assert r.door_bearing_error_deg > 30.0 and r.notes and "declared door" in r.notes[0] and r.failed is None and sm.state == State.STANDBY


def sim_find_door(start, stand_off, door=(6.0, 0.0), ref=(58464.0, 1.96), flag_at=60.0, seconds=200.0, find_filter=None):
    """The robot in a world with one door: the entrance result is (in view within 0.9 rad of the heading) the true bearing and the outline area of the enrolment scale at the true range."""
    from sentry.app.find_door_runner import FindDoorRunner
    sp, sm = Speaker(), StateMachine(StateMachineConfig())
    r = FindDoorRunner(sm, sp, ref=ref, stand_off_m=stand_off)
    model, (x, y, yaw), t, cmds = WheelModel(), start, 0.0, []
    r.start(0.0)
    while t < seconds and sm.state != State.STANDBY and not r.failed:
        rel = wrap(math.atan2(door[1] - y, door[0] - x) - yaw)
        d = math.hypot(door[0] - x, door[1] - y)
        side = math.sqrt(ref[0] * (ref[1] / d) ** 2) / 2.0
        quad = [(-side, -side), (side, -side), (side, side), (-side, side)]
        r.observe_entrance(EntranceResult(abs(rel) < 0.9, 30, None, rel if abs(rel) < 0.9 else None, quad if abs(rel) < 0.9 else None), t)
        v, w = r.step(t, (x, y, yaw), t >= flag_at)
        cmds.append((t, v, w, sm.state))
        v_m, w_r = model.body_speeds(v, w)
        x, y, yaw = x + v_m * math.cos(yaw) * DT, y + v_m * math.sin(yaw) * DT, wrap(yaw + w_r * DT)
        t += DT
    return r, sm, sp, cmds, (x, y, yaw), math.hypot(door[0] - x, door[1] - y), wrap(math.atan2(door[1] - y, door[0] - x) - yaw)


def test_find_door_measures_before_it_moves_and_centres_on_the_detected_bearing():
    r, sm, sp, cmds, pose, dist, rel = sim_find_door((0.0, 0.0, 0.0), None)         # the door is dead ahead: nothing to turn
    assert r.failed is None and r.phase == "DEPLOY"
    assert all(v == 0.0 and w == 0.0 for t, v, w, s in cmds if t < 1.1)                # still for the first hold: the old scan pulsed at t=0 and turned a centred door 23 deg away
    assert abs(rel) < 0.15 and abs(pose[2]) < 0.15


def test_find_door_turns_to_the_door_then_drives_to_the_stand_off_and_waits_for_the_flag():
    r, sm, sp, cmds, pose, dist, rel = sim_find_door((0.0, 0.0, 0.7), 2.25, door=(4.0, 0.0))   # the door 4 m ahead, the robot turned 40 deg away
    assert r.failed is None and sm.state == State.STANDBY and sp.played == ["place_camera", "camera_verified"]
    waited = [(v, w) for t, v, w, s in cmds if s == State.WAIT_CAMERA and t < 60.0]
    assert waited and set(waited) == {(0.0, 0.0)}                                      # stationary until the flag (tower + handshake)
    px, py, _ = [p for _, n, p in r.events if n == "VANTAGE_REACHED"][0]
    assert 1.9 <= math.hypot(4.0 - px, 0.0 - py) <= 2.5                                  # stopped near the stand-off, by the range estimate alone
    assert abs(wrap(math.atan2(0.0 - py, 4.0 - px) - r.found_pose[2])) < 0.2           # facing the door


def _drive_blind(r, obs, seconds=400.0, dt=1.0 / 30):
    """Step a runner whose detector always returns `obs` (None = nothing in view); the robot does not move in the world: only what the runner commands is counted."""
    t, path = 0.0, 0.0
    r.start(0.0)
    while t < seconds and not r.failed and r.phase != "DEPLOY":
        if obs is not None:
            r.observe_entrance(obs, t)
        v, w = r.step(t, (0.0, 0.0, 0.0), False)
        path += abs(v) * dt
        t += dt
    return path


def test_find_door_gives_up_with_a_reason_when_the_door_never_appears():
    from sentry.app.find_door_runner import FindDoorRunner
    r = FindDoorRunner(StateMachine(StateMachineConfig()), Speaker())
    _drive_blind(r, None)
    assert r.failed and "not found" in r.failed


def test_find_door_stops_on_a_distance_bound_when_the_range_estimate_never_drops():
    from sentry.app.find_door_runner import FindDoorRunner
    ref = (58464.0, 1.96)
    side = math.sqrt(ref[0] * (ref[1] / 4.0) ** 2) / 2.0                                 # an outline that always reads 4 m
    quad = [(-side, -side), (side, -side), (side, side), (-side, side)]
    r = FindDoorRunner(StateMachine(StateMachineConfig()), Speaker(), ref=ref, stand_off_m=2.25)
    path = _drive_blind(r, EntranceResult(True, 30, None, 0.0, quad))
    assert r.failed and "distance bound" in r.failed and path > 0 and r.driven_m < 4.0 - 2.25 + 1.0 + 0.5   # stops at about the bound (worst-case metres), not after 10 m


def test_find_door_ignores_a_degenerate_outline_and_bad_settings():
    from sentry.app.find_door_runner import FindDoorRunner
    ref = (58464.0, 1.96)
    r = FindDoorRunner(StateMachine(StateMachineConfig()), Speaker(), ref=ref, stand_off_m=2.25)
    _drive_blind(r, EntranceResult(True, 30, None, 0.0, [(0, 0), (1, 1), (0, 1), (1, 0)]), seconds=30.0)   # zero-area bow-tie: no ZeroDivisionError, no drive decision
    assert not r.measures
    for bad in (dict(exponent=0.0), dict(exponent=-2.0), dict(stand_off_m=float("nan"))):
        try:
            FindDoorRunner(StateMachine(StateMachineConfig()), Speaker(), ref=ref, **dict({"stand_off_m": 2.25}, **bad))
            assert False, bad
        except ValueError:
            pass
