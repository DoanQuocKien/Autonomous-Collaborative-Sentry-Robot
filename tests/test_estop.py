from jetson.estop import EstopLogic, motor_cut, motor_rearm

R1, SELECT, START = 7, 10, 11


def arm(logic, t=0.0):
    """Hold Select+Start for the full time; returns the events of the final tick."""
    logic.button(SELECT, True, t)
    logic.button(START, True, t + 0.1)
    ev = logic.tick(t + 0.1 + 2.0)
    logic.button(SELECT, False, t + 2.2)
    logic.button(START, False, t + 2.2)
    return ev


def test_starts_hard_stopped_and_nothing_moves_until_armed():
    e = EstopLogic()
    assert e.hard and not e.motion_allowed
    assert e.button(R1, True, 0.0) == []          # holding R1 alone does nothing
    assert not e.motion_allowed
    assert e.button(4, True, 0.1) == []           # other buttons are no-ops while already hard-stopped


def test_arming_needs_both_buttons_held_for_the_full_time():
    e = EstopLogic(arm_hold_s=2.0)
    e.button(SELECT, True, 0.0)
    assert e.tick(5.0) == [] and e.hard           # one button is never enough
    e.button(START, True, 5.0)
    assert e.tick(6.9) == [] and e.hard           # not long enough
    assert e.tick(7.0) == ["ARM"] and not e.hard  # armed, but R1 not held yet, so still no motion
    assert not e.motion_allowed
    assert e.tick(8.0) == []                      # arms once


def test_releasing_the_chord_early_restarts_the_hold():
    e = EstopLogic(arm_hold_s=2.0)
    e.button(SELECT, True, 0.0)
    e.button(START, True, 0.0)
    e.button(START, False, 1.5)
    assert e.tick(2.5) == []
    e.button(START, True, 3.0)
    assert e.tick(4.9) == [] and e.tick(5.0) == ["ARM"]


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
    e.button(SELECT, True, 0.0)
    e.button(START, True, 0.0)
    assert e.tick(2.0) == ["ARM", "GO"] and e.motion_allowed


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
    e.button(SELECT, True, 6.0)
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


def test_single_key_arming_still_needs_the_full_hold_and_r1():
    e = EstopLogic(arm_buttons=(START,), arm_hold_s=1.5)
    e.button(START, True, 0.0)
    assert e.tick(1.4) == [] and e.hard           # not held long enough
    e.button(START, False, 1.45)
    e.button(START, True, 2.0)
    assert e.tick(3.6) == ["ARM"] and not e.motion_allowed   # armed, but R1 not held: no motion
    assert e.button(R1, True, 3.7) == ["GO"]
    assert e.button(4, True, 3.8) == ["STOP"] and e.hard     # any other key is still a hard stop

