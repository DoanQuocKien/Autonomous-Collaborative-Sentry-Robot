import math

import pytest

from tools.locate_door import locate


def scan(boards, door, pos, heading):
    """What scan_boards would report for a robot at pos (world frame) with the given heading: boards and door in its own start frame."""
    c, s = math.cos(-heading), math.sin(-heading)

    def own(w):
        dx, dy = w[0] - pos[0], w[1] - pos[1]
        return c * dx - s * dy, s * dx + c * dy
    out = {k: dict(x_m=own(v)[0], y_m=own(v)[1]) for k, v in boards.items()}
    dx, dy = own(door)
    return dict(boards=out, door_bearing_deg=math.degrees(math.atan2(dy, dx)))


BOARDS = {"0": (3.7, 0.1), "1": (0.0, -1.8), "2": (-0.1, 1.5)}


def test_recovers_the_door_from_a_second_spot_with_a_different_heading():
    door = (3.9, -1.6)
    r = locate(scan(BOARDS, door, (0, 0), 0.0), scan(BOARDS, door, (1.0, 0.2), math.radians(12)))
    assert (r["door_x_m"], r["door_y_m"]) == pytest.approx(door, abs=0.02)
    assert r["second_position_in_first_frame"] == pytest.approx([1.0, 0.2], abs=0.01)
    assert r["board_fit_rms_m"] < 0.001


def test_errors_are_loud():
    door = (3.9, -1.6)
    a = scan(BOARDS, door, (0, 0), 0.0)
    with pytest.raises(ValueError):          # one common board only
        locate(a, dict(boards={"0": a["boards"]["0"]}, door_bearing_deg=-20.0))
    with pytest.raises(ValueError):          # door not seen the second time
        locate(a, dict(boards=a["boards"], door_bearing_deg=None))
    with pytest.raises(ValueError):          # no baseline: parallel rays
        locate(a, scan(BOARDS, door, (0, 0), 0.0))


def test_door_and_sweet_spot_in_the_final_frame():
    door = (3.9, -1.6)
    heading, pos = math.radians(50), (0.4, -1.3)
    r = locate(scan(BOARDS, door, (0, 0), 0.0), scan(BOARDS, door, pos, heading), stand_off_m=2.0)
    s = scan(BOARDS, door, pos, heading)                 # what the second robot itself would see of the door: bearing + range
    dx, dy = door[0] - pos[0], door[1] - pos[1]
    rng = math.hypot(dx, dy)
    assert r["door_in_second_frame"] == pytest.approx([rng * math.cos(math.radians(s["door_bearing_deg"])), rng * math.sin(math.radians(s["door_bearing_deg"]))], abs=0.03)
    assert math.hypot(*r["sweet_spot_in_second_frame"]) == pytest.approx(rng - 2.0, abs=0.03)
