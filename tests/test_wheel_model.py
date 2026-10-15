from sentry.nav.wheel_model import WheelModel

M = WheelModel()


def test_forward_speeds_match_the_marker_measurements_of_2026_10_15():
    measured = {0.4: 0.139, 0.5: 0.185, 0.6: 0.238, 0.7: 0.276, 0.85: 0.357, 1.0: 0.435}      # steady speeds, m/s
    for v, s in measured.items():
        got = M.body_speeds(v, 0.0)[0]
        assert abs(got - s) / s < 0.06, (v, got, s)
    assert M.body_speeds(0.3, 0.0) == (0.0, 0.0)                    # below v 0.4 the dead zone stops the robot, as measured on 2026-10-11
    old = 0.4135 * 0.4                                              # the proportional model over-predicts by about 19 % at v 0.4
    assert old / M.body_speeds(0.4, 0.0)[0] > 1.15


def test_turn_rates_match_the_marker_measurements_of_2026_10_15():
    measured = {0.4: 1.98, 0.5: 2.62, 1.0: 6.27}                    # rad/s per wheel second
    for w, r in measured.items():
        v, om = M.body_speeds(0.0, w)
        assert v == 0.0 and abs(om - r) / r < 0.08, (w, om, r)
    assert M.body_speeds(0.0, -0.5)[1] < 0                          # right turn
    assert M.body_speeds(0.0, 0.3) == (0.0, 0.0)                    # wheels at 0.09: below min_pwm, stands still


def test_steering_while_driving_keeps_its_turn_and_the_wheel_dead_zone_acts_per_wheel():
    v, om = M.body_speeds(0.6, 0.065)                               # both wheels above the dead zone: the small turn is real (+24 deg/s on 2026-10-14)
    assert abs(v - 0.2325) < 0.01 and om > 0.3
    v, om = M.body_speeds(0.5, 0.15)                                # left wheel 0.35 * 0.3 = 0.105 stops: an arc, faster turn than the command alone
    assert v < M.body_speeds(0.5, 0.0)[0] and om > 1.5
    assert M.body_speeds(0.7, 0.0)[0] > 0 and M.body_speeds(-0.7, 0.0)[0] < 0   # reverse is symmetric


def test_scale_and_offset_are_the_online_knobs():
    slow = WheelModel(scale=0.8)
    assert abs(slow.body_speeds(0.7, 0.0)[0] - 0.8 * M.body_speeds(0.7, 0.0)[0]) < 1e-9
    assert WheelModel(m0=0.044).body_speeds(0.4, 0.0)[0] < M.body_speeds(0.4, 0.0)[0]       # a bigger offset (low battery) slows the low speeds most
