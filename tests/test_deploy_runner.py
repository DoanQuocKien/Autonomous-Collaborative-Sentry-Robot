import math

from sentry.app.deploy_runner import DeployRunner, face_command, goto_command, wrap
from sentry.app.state_machine import State, StateMachine, StateMachineConfig
from tools.sim_robot import SimRobot


class Speaker:
    def __init__(self):
        self.played = []

    def play(self, clip):
        self.played.append(clip)
        return True


def run(handshake_at=None, blocked=False, seconds=200.0, cfg=None, start=(0.0, 0.0, 0.0), vantage=(1.2, 0.6), centre=(3.0, 0.0), dt=0.05):
    sim = SimRobot()
    sim.x, sim.y, sim.theta = start
    sp = Speaker()
    sm = StateMachine(cfg or StateMachineConfig())
    r = DeployRunner(sm, sp, vantage_xy=vantage, centre_xy=centre)
    r.start(0.0, 0.0)
    t = 0.0
    snap = {}
    while t < seconds:
        pose = (sim.x, sim.y, sim.theta)
        in_view = handshake_at is not None and t >= handshake_at
        v, w = r.step(t, pose, in_view)
        if not blocked:
            sim.v, sim.w, sim.last_cmd = v, w, t
        sim.step(t, dt)
        if sm.state == State.WAIT_CAMERA and "wait" not in snap:
            snap["wait"] = (sim.x, sim.y, sim.theta)
        t += dt
        if sm.state == State.STANDBY:
            break
    return sim, sm, r, sp, snap


def test_goto_turns_first_then_drives_and_stops_in_the_tolerance():
    v, w, arrived = goto_command((0.0, 0.0, 0.0), (0.0, 2.0))             # goal 90 deg left: turn in place
    assert v == 0.0 and w > 0 and not arrived
    v, w, arrived = goto_command((0.0, 0.0, 0.0), (2.0, 0.0))
    assert v > 0 and abs(w) < 1e-9 and not arrived
    assert goto_command((0.0, 0.0, 0.0), (0.1, 0.0))[2] is True
    assert abs(wrap(3 * math.pi) - math.pi) < 1e-9 or abs(wrap(3 * math.pi) + math.pi) < 1e-9
    w, done = face_command((0.0, 0.0, 0.0), (1.0, 1.0))
    assert w > 0 and not done and face_command((0.0, 0.0, 0.0), (1.0, 0.0)) == (0.0, True)


def test_full_deployment_reaches_the_vantage_prompts_waits_verifies_and_backs_up_to_standby():
    sim, sm, r, sp, snap = run(handshake_at=20.0)
    assert sm.state == State.STANDBY
    assert [s for _, s in r.log] == ["APPROACH_VANTAGE", "WAIT_CAMERA", "RETRACT", "STANDBY"]
    assert sp.played == ["place_camera", "camera_verified"]
    x, y, th = snap["wait"]                                               # where it stopped for the camera
    assert math.hypot(x - 1.2, y - 0.6) <= 0.2
    # it faced the room centre while waiting: heading toward (3, 0) at verification time (the retract moved it back along that heading)
    assert abs(wrap(math.atan2(0.0 - y, 3.0 - x) - th)) < 0.25 or abs(wrap(math.atan2(0.0 - sim.y, 3.0 - sim.x) - sim.theta)) < 0.35
    assert math.hypot(sim.x - x, sim.y - y) > 0.2                         # it reversed (retract is time based, 2 s at the retract speed)


def test_no_handshake_prompts_again_at_the_machines_timeout():
    cfg = StateMachineConfig(handshake_timeout_s=30.0)
    sim, sm, r, sp, snap = run(handshake_at=None, seconds=90.0, cfg=cfg)
    assert sm.state == State.WAIT_CAMERA and sp.played.count("place_camera") >= 2 and "camera_verified" not in sp.played


def test_a_blocked_robot_gives_up_the_approach_and_goes_back_to_exploring():
    cfg = StateMachineConfig(approach_timeout_s=5.0)
    sim, sm, r, sp, snap = run(blocked=True, seconds=10.0, cfg=cfg)
    assert sm.state == State.EXPLORE and sp.played == []


def test_flickering_handshake_does_not_verify_until_three_frames_in_a_row():
    sm = StateMachine(StateMachineConfig())
    sp = Speaker()
    r = DeployRunner(sm, sp, vantage_xy=(0.0, 0.0), centre_xy=(1.0, 0.0))
    r.start(0.0)
    r.step(0.1, (0.0, 0.0, 0.0), False)                                   # at the vantage: VANTAGE_REACHED, now waiting
    assert sm.state == State.WAIT_CAMERA
    for k, flag in enumerate([True, True, False, True, True]):
        r.step(0.2 + 0.1 * k, (0.0, 0.0, 0.0), flag)
    assert sm.state == State.WAIT_CAMERA                                  # never 3 in a row
    r.step(1.0, (0.0, 0.0, 0.0), True)                                    # the run since the False is now 3: verified
    assert sm.state == State.RETRACT and sp.played[-1] == "camera_verified"
