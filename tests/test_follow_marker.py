import math

from tools.follow_marker import PIController, simulate, veer_deg_per_m


def test_controller_signs_and_clamps():
    c = PIController()
    assert c.step(0.3, 0.1) > 0 and c.step(-0.3, 0.1) < c.step(0.3, 0.1)      # marker on the left -> turn left (w > 0)
    c = PIController(kp=10.0)
    assert c.step(1.0, 0.1) == c.w_max and c.step(-1.0, 0.1) == -c.w_max
    for _ in range(1000):
        c.step(1.0, 0.1)
    assert c.i == c.i_max                                                       # anti-windup


def test_closed_loop_learns_the_veer_and_keeps_the_marker_ahead():
    for bias in (0.12, -0.08):                                                  # rad/s, the robot veers left / right
        i, bearing = simulate(bias)
        assert abs(bearing) < math.radians(6)                                   # stays on the marker
        assert math.isclose(i, -bias / 7.2, rel_tol=0.35)                       # the integral is the steering that cancels it
        assert veer_deg_per_m(i, 0.7) * bias > 0                                # same sign as the veer
