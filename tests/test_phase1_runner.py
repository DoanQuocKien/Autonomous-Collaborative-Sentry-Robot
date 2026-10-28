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
