import subprocess

from jetson.estop import EstopLogic, i2c_write, motor_cut, motor_rearm, write_heartbeat
from jetson.robot_udp import estop_engaged

R1, SELECT, START = 7, 10, 11


def arm(logic, t=0.0):
    """Hold Start (the default arm key) for the full time; returns the events of the final tick."""
    logic.button(START, True, t)
    ev = logic.tick(t + 1.5)
    logic.button(START, False, t + 1.7)
    return ev


def test_starts_hard_stopped_and_nothing_moves_until_armed():
    e = EstopLogic()
    assert e.hard and not e.motion_allowed
    assert e.button(R1, True, 0.0) == []          # holding R1 alone does nothing
    assert not e.motion_allowed
    assert e.button(4, True, 0.1) == []           # other buttons are no-ops while already hard-stopped


def test_arming_needs_start_held_for_the_full_time():
    e = EstopLogic()
    e.button(SELECT, True, 0.0)
    assert e.tick(5.0) == [] and e.hard           # Select alone never arms
    e.button(START, True, 5.0)
    assert e.tick(6.4) == [] and e.hard           # not long enough
    assert e.tick(6.5) == ["ARM"] and not e.hard  # armed, but R1 not held yet, so still no motion
    assert not e.motion_allowed
    assert e.tick(8.0) == []                      # arms once


def test_releasing_the_arm_key_early_restarts_the_hold():
    e = EstopLogic()
    e.button(START, True, 0.0)
    e.button(START, False, 1.0)
    assert e.tick(2.5) == []
    e.button(START, True, 3.0)
    assert e.tick(4.4) == [] and e.tick(4.5) == ["ARM"]


def test_a_two_key_chord_is_still_possible():
    e = EstopLogic(arm_buttons=(SELECT, START), arm_hold_s=2.0)
    e.button(SELECT, True, 0.0)
    assert e.tick(5.0) == [] and e.hard           # one button is never enough
    e.button(START, True, 5.0)
    assert e.tick(6.9) == [] and e.hard and e.tick(7.0) == ["ARM"]


def test_dead_man_hold_allows_motion_and_release_stops_it():
    e = EstopLogic()
    assert arm(e) == ["ARM"]
    assert e.button(R1, True, 5.0) == ["GO"] and e.motion_allowed
    assert e.button(R1, False, 6.0) == ["STOP"] and not e.motion_allowed and e.reason == "R1 released"
    assert not e.hard                              # a soft stop: no chord needed to resume
    assert e.button(R1, True, 7.0) == ["GO"]       # hold again, moves again


def test_arming_while_holding_r1_goes_straight_to_motion():
    e = EstopLogic()
    e.button(R1, True, 0.0)
    e.button(START, True, 0.0)
    assert e.tick(1.5) == ["ARM", "GO"] and e.motion_allowed


def test_any_other_button_is_a_hard_stop_that_needs_the_chord_again():
    e = EstopLogic()
    arm(e)
    e.button(R1, True, 5.0)
    assert e.button(4, True, 6.0) == ["STOP"] and e.hard and e.reason == "button 4 pressed"
    assert e.button(4, False, 6.1) == []                       # release is not an event
    assert e.button(R1, False, 6.2) == [] and e.button(R1, True, 7.0) == []   # R1 no longer enough
    assert not e.motion_allowed
    assert arm(e, 10.0) == ["ARM", "GO"]                        # chord while R1 is still held: moves again


def test_pressing_a_chord_button_while_armed_is_a_hard_stop():
    e = EstopLogic()
    arm(e)
    assert e.button(START, True, 5.0) == [] and e.hard          # armed but R1 not held: still a hard stop, no event
    e2 = EstopLogic()
    arm(e2)
    e2.button(R1, True, 5.0)
    assert e2.button(START, True, 6.0) == ["STOP"]


def test_a_dying_pad_that_reports_a_release_stops_the_robot():
    # measured on the real pad: switching it off while R1 is held makes the receiver emit a release
    e = EstopLogic()
    arm(e)
    e.button(R1, True, 5.0)
    assert e.button(R1, False, 9.0) == ["STOP"]


def test_device_lost_is_a_hard_stop_and_forgets_held_buttons():
    e = EstopLogic()
    arm(e)
    e.button(R1, True, 5.0)
    assert e.device_lost() == ["STOP"] and e.hard and e.reason == "gamepad lost"
    assert e.device_lost() == []                                # nothing more to report
    e.button(START, True, 6.0)
    e.device_lost()                                             # held buttons are forgotten
    assert e.tick(20.0) == [] and e.hard


def test_a_stale_r1_after_pad_loss_cannot_start_the_robot_later():
    e = EstopLogic()
    arm(e)
    e.button(R1, True, 5.0)
    e.device_lost()                                             # pad died while R1 was held
    assert not e.dead_held
    assert arm(e, 10.0) == ["ARM"]                              # re-arming alone must NOT move the robot
    assert not e.motion_allowed
    assert e.button(R1, True, 20.0) == ["GO"]                   # only a fresh R1 hold does


def test_motor_cut_and_rearm_write_the_expected_registers():
    calls = []

    def fake(cmd, **kw):
        calls.append(cmd[3:])
        return 0

    assert motor_cut(1, 0x60, fake)
    assert calls == [["0x60", "0xfd", "0x10"]]
    calls.clear()
    assert motor_rearm(1, 0x60, fake)
    assert calls == [["0x60", "0xfa", "0x0"], ["0x60", "0xfb", "0x0"], ["0x60", "0xfc", "0x0"], ["0x60", "0xfd", "0x0"]]
    assert not motor_cut(1, 0x60, lambda cmd, **kw: 1)          # an i2cset failure is reported


def test_a_hung_i2c_bus_is_a_failed_write_not_a_hang():
    def hung(cmd, **kw):
        assert kw["timeout"] > 0
        raise subprocess.TimeoutExpired(cmd, kw["timeout"])

    assert not i2c_write(1, 0x60, 0xFD, 0x10, hung)
    assert not motor_cut(1, 0x60, lambda cmd, **kw: (_ for _ in ()).throw(FileNotFoundError("i2cset")))


def test_heartbeat_interlock(tmp_path):
    latch, alive = str(tmp_path / "ESTOP"), str(tmp_path / "ESTOP_ALIVE")
    assert estop_engaged(latch, alive, 100.0)                   # no e-stop program: engaged
    write_heartbeat(alive, 100.0)
    assert not estop_engaged(latch, alive, 101.0)               # fresh heartbeat, no latch: released
    assert estop_engaged(latch, alive, 102.5)                   # stale
    assert estop_engaged(latch, alive, 98.0)                    # from the future (old wall-clock writer, clock jump)
    (tmp_path / "ESTOP_ALIVE").write_text("")
    assert estop_engaged(latch, alive, 100.0)                   # unreadable
    write_heartbeat(alive, 100.0)
    (tmp_path / "ESTOP").write_text("R1 released")
    assert estop_engaged(latch, alive, 100.1)                   # latch always wins
    assert not (tmp_path / "ESTOP_ALIVE.tmp").exists()
