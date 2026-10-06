from jetson.estop import EstopLogic, motor_cut, motor_rearm


def arm(logic, t=0.0):
    logic.button(10, True, t)
    logic.button(11, True, t + 0.1)
    return logic.tick(t + 0.1 + 2.0)


def test_starts_engaged_and_ignores_buttons_until_armed():
    e = EstopLogic()
    assert e.engaged
    assert e.button(4, True, 0.0) is None and e.button(4, False, 0.1) is None
    assert e.engaged


def test_arming_needs_both_buttons_held_for_the_full_time():
    e = EstopLogic(arm_hold_s=2.0)
    e.button(10, True, 0.0)
    assert e.tick(5.0) is None and e.engaged               # one button is never enough
    e.button(11, True, 5.0)
    assert e.tick(6.9) is None and e.engaged               # not long enough yet
    assert e.tick(7.0) == "ARM" and not e.engaged
    assert e.tick(8.0) is None                             # arms once


def test_releasing_early_restarts_the_hold():
    e = EstopLogic(arm_hold_s=2.0)
    e.button(10, True, 0.0)
    e.button(11, True, 0.0)
    e.button(11, False, 1.5)
    assert e.tick(2.5) is None
    e.button(11, True, 3.0)
    assert e.tick(4.9) is None and e.tick(5.0) == "ARM"


def test_any_button_press_stops_when_armed_and_release_does_not():
    e = EstopLogic()
    assert arm(e) == "ARM"
    assert e.button(10, False, 3.0) is None and e.button(11, False, 3.0) is None   # releasing the chord is fine
    assert e.button(7, True, 4.0) == "STOP" and e.engaged
    assert e.button(7, False, 4.1) is None


def test_pressing_a_chord_button_while_armed_also_stops():
    e = EstopLogic()
    arm(e)
    e.button(10, False, 3.0)
    e.button(11, False, 3.0)
    assert e.button(11, True, 5.0) == "STOP"


def test_device_lost_engages_once():
    e = EstopLogic()
    arm(e)
    assert e.device_lost() == "STOP" and e.engaged
    assert e.device_lost() is None
    e2 = EstopLogic()
    assert e2.device_lost() is None                        # already engaged


def test_cannot_be_armed_by_a_stale_chord_after_device_loss():
    e = EstopLogic()
    e.button(10, True, 0.0)
    e.button(11, True, 0.0)
    e.device_lost()                                        # held buttons are forgotten
    assert e.tick(10.0) is None and e.engaged


def test_motor_cut_and_rearm_write_the_expected_registers():
    calls = []

    def fake(cmd, **kw):
        calls.append(cmd[3:])  # skip "i2cset -y 1"? keep addr, reg, value
        return 0

    assert motor_cut(1, 0x60, fake)
    assert calls == [["0x60", "0xfd", "0x10"]]
    calls.clear()
    assert motor_rearm(1, 0x60, fake)
    assert calls == [["0x60", "0xfa", "0x0"], ["0x60", "0xfb", "0x0"], ["0x60", "0xfc", "0x0"], ["0x60", "0xfd", "0x0"]]
    assert not motor_cut(1, 0x60, lambda cmd, **kw: 1)     # an i2cset failure is reported
