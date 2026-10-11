import math

import pytest

from common.protocol import encode_control, encode_play
from tools.sim_robot import SimRobot


def run(robot, seconds, dt=0.02, t0=0.0, v=None, w=None, seq=None):
    """Feed one command per step (like a 50 Hz controller) for `seconds`; -> the time after the run."""
    t = t0
    for i in range(int(round(seconds / dt))):
        if v is not None:
            robot.on_packet(encode_control(seq + i, v, w), t)
        robot.step(t, dt)
        t += dt
    return t


def test_straight_and_left_turn():
    r = SimRobot(v_max=0.5, w_max=2.0)
    run(r, 2.0, v=1.0, w=0.0, seq=0)
    assert math.isclose(r.x, 1.0, abs_tol=1e-9) and abs(r.y) < 1e-9
    r = SimRobot(v_max=0.5, w_max=2.0)
    run(r, math.pi / 4, dt=math.pi / 400, v=0.0, w=1.0, seq=0)   # 2 rad/s for pi/4 s
    assert math.isclose(r.theta, math.pi / 2, abs_tol=1e-6)        # positive w turns left (counter-clockwise)


def test_closed_square_returns_to_the_origin():
    r = SimRobot(v_max=0.5, w_max=2.0)
    t, seq = 0.0, 0
    for _ in range(4):
        t = run(r, 2.0, t0=t, v=1.0, w=0.0, seq=seq)
        seq += 1000
        t = run(r, math.pi / 4, dt=math.pi / 400, t0=t, v=0.0, w=1.0, seq=seq)
        seq += 1000
    assert math.hypot(r.x, r.y) < 1e-6 and abs(r.theta) < 1e-6


def test_watchdog_stops_after_silence():
    r = SimRobot(watchdog_s=0.3)
    r.on_packet(encode_control(1, 1.0, 0.0), 0.0)
    assert not r.step(0.25, 0.25) and r.moving
    assert r.step(0.31, 0.06) and not r.moving
    x = r.x
    r.step(1.0, 0.5)
    assert r.x == x


@pytest.mark.parametrize("packet", [
    b'{"seq": 2, "v": NaN, "w": 0}',      # the old sim clamped NaN to full speed
    b'{"seq": 2, "v": "1", "w": 0}', b"garbage",
    encode_control(1, 1.0, 0.0),          # duplicate seq
    encode_control(0, 1.0, 0.0),          # out of order
])
def test_rejects_what_the_robot_rejects(packet):
    r = SimRobot()
    r.on_packet(encode_control(1, 0.2, 0.0), 0.0)
    assert r.on_packet(packet, 0.01) is None
    assert (r.v, r.w) == (0.2, 0.0)


def test_play_is_reported_and_does_not_move():
    r = SimRobot()
    assert r.on_packet(encode_play(1, "guard_ready"), 0.0) == {"seq": 1, "play": "guard_ready"}
    assert not r.moving and r.last_cmd is None
