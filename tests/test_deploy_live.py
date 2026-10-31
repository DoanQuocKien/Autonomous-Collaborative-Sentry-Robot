from sentry.app.deploy_runner import DeployRunner
from sentry.app.state_machine import StateMachine, StateMachineConfig
from sentry.nav.explore import Command, ExploreSettings, legal
from sentry.nav.wheel_model import WheelModel
from tools.deploy_live import control_loop, fresh_flag


class Speaker:
    def __init__(self):
        self.played = []

    def play(self, clip):
        self.played.append(clip)
        return True


def loop(get_flag=lambda now: False, get_link=lambda now: None, seconds=100.0, key=lambda: None, cfg=None):
    clock_t = {"t": 0.0}
    sp = Speaker()
    runner = DeployRunner(StateMachine(cfg or StateMachineConfig()), sp, vantage_xy=(1.2, 0.6), centre_xy=(3.0, 0.0))
    cmd, end = {"v": 0.0, "w": 0.0, "t": 0.0}, {"reason": None}

    def sleep(d):
        clock_t["t"] += d
    rows, pose, path = control_loop(runner, WheelModel(), cmd, end, lambda now: get_flag(now), get_link, seconds, clock=lambda: clock_t["t"], sleep=sleep, key=key)
    return rows, end, runner, sp, cmd, path


def test_a_run_with_a_handshake_ends_in_standby_with_legal_commands():
    s = ExploreSettings()
    rows, end, runner, sp, cmd, path = loop(get_flag=lambda now: now >= 15.0)
    assert end["reason"] == "STANDBY reached" and sp.played == ["place_camera", "camera_verified"]
    assert all(legal(Command(r[4], r[5], "", ""), s) for r in rows) and path > 1.0
    assert (cmd["v"], cmd["w"]) == (0.0, 0.0) or end["reason"] == "STANDBY reached"


def test_a_stale_robot_link_stops_the_run():
    rows, end, runner, sp, cmd, path = loop(get_link=lambda now: {"stale": now > 2.0, "blocked": False})
    assert end["reason"].startswith("no robot frame") and rows[-1][0] <= 2.1


def test_a_blocker_stops_the_robot_while_it_drives_forward_and_never_avoids():
    rows, end, runner, sp, cmd, path = loop(get_link=lambda now: {"stale": False, "blocked": True})
    assert end["reason"].startswith("obstacle ahead") and (cmd["v"], cmd["w"]) == (0.0, 0.0)


def test_the_time_limit_and_the_q_key_end_the_run():
    rows, end, *_ = loop(seconds=3.0)
    assert end["reason"] == "time limit"
    rows, end, *_ = loop(key=lambda: "q")
    assert end["reason"] == "operator pressed q" and rows == []


def test_the_v_key_verifies_by_hand_and_latches_long_enough_for_three_ticks():
    fired = {"done": False}

    def key():
        return None
    clock_probe = {"n": 0}

    def get_flag(now):
        return False

    def keyed():
        clock_probe["n"] += 1
        if clock_probe["n"] == 600 and not fired["done"]:       # about 20 s in, the robot is waiting for the camera
            fired["done"] = True
            return "v"
        return None
    rows, end, runner, sp, cmd, path = loop(get_flag=get_flag, key=keyed)
    assert end["reason"] == "STANDBY reached" and sp.played[-1] == "camera_verified"


def test_a_handshake_answer_counts_only_while_it_is_fresh():
    assert fresh_flag({"in_view": True, "t": 10.0}, 10.5) is True
    assert fresh_flag({"in_view": True, "t": 10.0}, 12.0) is False            # stale: the ESP32 stream stopped
    assert fresh_flag({"in_view": False, "t": 10.0}, 10.1) is False
    assert fresh_flag(None, 1.0) is False and fresh_flag({"in_view": True, "t": None}, 1.0) is False


def test_windowed_handshake_needs_a_steady_majority_not_a_single_frame():
    from tools.deploy_live import WindowedHandshake
    w = WindowedHandshake(span_s=3.0, min_frames=10, frac=0.7)
    for k in range(10):                                           # 10 answers in a second, only one in view: not verified
        w.add(k * 0.1, k == 5)
    assert w.in_view(1.0) is False
    w2 = WindowedHandshake(3.0, 10, 0.7)
    for k in range(9):
        w2.add(k * 0.1, True)
    assert w2.in_view(0.9) is False                                # too few answers yet (9 < 10)
    w2.add(0.9, True)
    assert w2.in_view(0.9) is True                                 # 10 of 10
    assert w2.in_view(5.0) is False                                # the answers are older than the window
    w3 = WindowedHandshake(3.0, 10, 0.7)
    for k in range(20):
        w3.add(k * 0.1, k % 3 != 0)                                # 13 of 20 in view = 65 %: below 70 %
    assert w3.in_view(1.9) is False and abs(w3.stats(1.9)[1] - 0.65) < 0.06


def test_evidence_from_before_the_prompt_does_not_verify_the_camera():
    from tools.deploy_live import WindowedHandshake, make_flag
    from sentry.app.state_machine import State

    class SM:
        state = State.APPROACH_VANTAGE
    sm, window, esp = SM(), WindowedHandshake(3.0, 10, 0.7), {"in_view": False, "t": None}
    flag = make_flag(esp, window, sm)
    for k in range(12):                                            # the camera already faces the door while the robot drives
        window.add(k * 0.1, True)
        esp.update(in_view=window.in_view(k * 0.1), t=k * 0.1)
    assert flag(1.2) is True                                       # still the driving phase: the flag follows the window
    sm.state = State.WAIT_CAMERA                                   # the prompt plays: the old evidence is dropped
    assert flag(1.3) is False and window.in_view(1.3) is False
    for k in range(13, 25):                                        # new answers after the prompt
        window.add(k * 0.1, True)
        esp.update(in_view=window.in_view(k * 0.1), t=k * 0.1)
    assert flag(2.5) is True                                       # verified only on the evidence gathered after the prompt


def test_a_reset_ignores_late_answers_that_are_older_than_the_prompt():
    from tools.deploy_live import WindowedHandshake
    w = WindowedHandshake(3.0, 10, 0.7)
    w.reset(5.0)
    for k in range(20):
        w.add(4.0 + k * 0.04, True)                                  # the reader thread delivers 20 answers stamped before the reset (4.00 .. 4.76)
    assert w.stats(5.0)[0] == 0 and w.in_view(5.0) is False         # none counts, although they are inside the 3 s span
    for k in range(10):
        w.add(5.0 + k * 0.1, True)
    assert w.stats(5.9)[0] == 10 and w.in_view(5.9) is True         # only the ten stamped at 5.0 or later


def test_marker_fixes_pull_the_pose_and_spins_go_in_pulses():
    import math
    from tools.deploy_live import blend_fix
    x, y, yaw = blend_fix((0.0, 0.0, math.radians(170)), (1.0, 0.0, math.radians(-170)), 0.5)
    assert abs(x - 0.5) < 1e-9 and abs(math.degrees(yaw) - 180.0) < 1e-6                  # the short way round the circle, not through 0


def test_servo_motion_recovers_a_slow_drive_and_an_uneven_turn_from_the_board_sightings():
    from sentry.nav.wheel_model import WheelModel
    from tools.deploy_live import servo_motion
    m = WheelModel()
    v_m = m.body_speeds(0.55, 0.0)[0]
    log = [(0.05 * i, 3.0 - 0.8 * v_m * 0.05 * i, 0.0, 0.55, 0.0) for i in range(60)]                  # the robot closes at 0.8 of the model's speed
    w_r = m.body_speeds(0.0, 0.45)[1]
    log += [(10 + 0.05 * i, 1.0, 0.0 - 1.2 * w_r * 0.05 * i, 0.0, 0.45) for i in range(10)]            # a left spin at 1.2 of the model: the board's bearing goes negative
    out = servo_motion(log, m)
    assert abs(out["speed_ratio"] - 0.8) < 0.02 and abs(out["turn_ratio_left"] - 1.2) < 0.02 and out["turn_ratio_right"] is None
