import math

from sentry.app.deploy_runner import DeployRunner, DeploySettings, face_command, goto_command, wrap
from sentry.app.state_machine import State, StateMachine, StateMachineConfig
from sentry.nav.explore import Command, ExploreSettings, legal
from sentry.nav.wheel_model import WheelModel

DT = 1.0 / 30.0                     # the live control loop rate: one spin tick turns the robot about 0.07 rad


class Speaker:
    def __init__(self):
        self.played = []

    def play(self, clip):
        self.played.append(clip)
        return True


def run(handshake_at=None, blocked=False, seconds=200.0, cfg=None, start=(0.0, 0.0, 0.0), vantage=(1.2, 0.6), centre=(3.0, 0.0)):
    """Closed loop with the real wheel model (dead zone included): the robot only moves when the command is legal for the motors."""
    model = WheelModel()
    x, y, yaw = start
    sp = Speaker()
    sm = StateMachine(cfg or StateMachineConfig())
    r = DeployRunner(sm, sp, vantage_xy=vantage, centre_xy=centre)
    r.start(0.0, 0.0)
    cmds, t = [], 0.0
    while t < seconds:
        v, w = r.step(t, (x, y, yaw), handshake_at is not None and t >= handshake_at)
        cmds.append((v, w))
        if not blocked:
            v_m, w_r = model.body_speeds(v, w)
            x += v_m * math.cos(yaw) * DT
            y += v_m * math.sin(yaw) * DT
            yaw = wrap(yaw + w_r * DT)
        t += DT
        if sm.state == State.STANDBY:
            break
    return (x, y, yaw), sm, r, sp, cmds, t


def event_pose(r, name):
    return [p for _, n, p in r.events if n == name][0]


def test_every_command_is_legal_for_the_motors_and_the_dead_zone_does_not_stall_the_robot():
    s = ExploreSettings()
    ok = (s.v_forward, s.w_spin)
    assert goto_command((0.0, 0.0, 0.0), (0.0, 2.0)) == (0.0, 0.45, False)       # goal 90 deg left: spin, never a slow turn
    assert goto_command((0.0, 0.0, 0.0), (2.0, 0.0)) == (0.55, 0.0, False)
    v, w, _ = goto_command((0.0, 0.0, 0.1), (2.0, 0.0))                           # a small error steers, but only as much as the slower wheel allows
    assert v == ok[0] and -0.14 <= w < 0 and legal(Command(v, w, "", ""), s)
    assert goto_command((0.0, 0.0, 0.0), (0.1, 0.0))[2] is True
    w, done = face_command((0.0, 0.0, 0.0), (1.0, 1.0))
    assert w == 0.45 and not done and face_command((0.0, 0.0, 0.0), (1.0, 0.0)) == (0.0, True)
    final, sm, r, sp, cmds, t = run(handshake_at=20.0)
    assert all(legal(Command(v, w, "", ""), s) for v, w in cmds)


def test_full_deployment_reaches_the_vantage_prompts_faces_the_centre_verifies_and_backs_up_to_standby():
    final, sm, r, sp, cmds, t = run(handshake_at=20.0)
    assert sm.state == State.STANDBY and t < 60.0
    assert [s for _, s in r.log] == ["APPROACH_VANTAGE", "WAIT_CAMERA", "RETRACT", "STANDBY"]
    assert sp.played == ["place_camera", "camera_verified"]
    px, py, pyaw = event_pose(r, "VANTAGE_REACHED")
    assert math.hypot(px - 1.2, py - 0.6) <= 0.14                                  # stopped on the vantage point
    qx, qy, qyaw = event_pose(r, "ESP32_VERIFIED")
    assert abs(wrap(math.atan2(0.0 - qy, 3.0 - qx) - qyaw)) <= 0.2                 # it was facing the room centre when the camera was verified
    assert 0.2 < math.hypot(final[0] - qx, final[1] - qy) < 0.45                   # it reversed: 2 s at about 0.16 m/s


def test_no_handshake_prompts_again_at_the_machines_timeout():
    cfg = StateMachineConfig(handshake_timeout_s=30.0)
    final, sm, r, sp, cmds, t = run(handshake_at=None, seconds=90.0, cfg=cfg)
    assert sm.state == State.WAIT_CAMERA and sp.played.count("place_camera") >= 2 and "camera_verified" not in sp.played


def test_a_blocked_robot_gives_up_the_approach_and_goes_back_to_exploring():
    cfg = StateMachineConfig(approach_timeout_s=5.0)
    final, sm, r, sp, cmds, t = run(blocked=True, seconds=10.0, cfg=cfg)
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


def test_a_failing_speaker_cannot_stop_the_deployment():
    class Broken:
        def play(self, clip):
            raise OSError("no sound card")
    sm = StateMachine(StateMachineConfig())
    r = DeployRunner(sm, Broken(), vantage_xy=(0.0, 0.0), centre_xy=(1.0, 0.0))
    r.start(0.0)
    r.step(0.1, (0.0, 0.0, 0.0), False)
    assert sm.state == State.WAIT_CAMERA and r.prompts == ["place_camera"]


def test_servo_command_turns_toward_a_board_then_drives_and_stops_at_the_range():
    from sentry.app.deploy_runner import servo_command
    assert servo_command(2.0, 0.8, 0.87) == (0.0, 0.45, False)            # board far to the left: spin left
    assert servo_command(2.0, -0.8, 0.87) == (0.0, -0.45, False)
    v, w, done = servo_command(2.0, 0.1, 0.87)
    assert v > 0 and 0 < w < 0.2 and not done                           # roughly ahead: drive and steer left
    assert servo_command(0.85, 0.0, 0.87) == (0.0, 0.0, True)


def test_board_following_arrival_resets_the_pose_to_the_vantage_facing_the_board():
    import math
    from sentry.app.deploy_runner import DeployRunner
    sm = StateMachine(StateMachineConfig())
    r = DeployRunner(sm, None, vantage_xy=(0.0, -1.8), centre_xy=(-2.0, -1.8), servo=lambda t: (0.85, 0.1), servo_stop_m=0.87, servo_board_xy=(0.0, -2.67))
    r.start(0.0, 0.0)
    r.step(0.1, (5.0, 5.0, 0.0))                                           # dead reckoning is wrong, the board says arrived
    x, y, yaw = r.pose_reset
    assert (x, y) == (0.0, -1.8) and abs(yaw - (-math.pi / 2 - 0.1)) < 1e-9
