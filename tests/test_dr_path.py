import math

from sentry.nav.wheel_model import WheelModel
from tools.dr_path import drive_seconds, end_error_m, replay


def _cmds(v, seconds, hz=30):
    return [(i / hz, v, 0.0) for i in range(int(seconds * hz) + 1)]


def test_replay_without_frames_is_plain_integration():
    v = 0.7
    cmds = _cmds(v, 5.0)
    speed = WheelModel().body_speeds(v, 0.0)[0]
    for correct in (False, True):
        x, y, th, n = replay(cmds, [], None, 1.0, correct)
        assert math.isclose(x, speed * 5.0, rel_tol=0.01) and abs(y) < 1e-6 and n == 0
    assert replay(cmds, [], None, 0.72, False)[0] < replay(cmds, [], None, 1.0, False)[0]


def test_drive_time_matches_the_model_and_the_error_metric():
    speed = WheelModel().body_speeds(0.7, 0.0)[0]
    assert math.isclose(drive_seconds(3.0, 0.7, 1.0), 3.0 / speed)
    assert drive_seconds(3.0, 0.7, 0.72) > drive_seconds(3.0, 0.7, 1.0)
    assert math.isclose(end_error_m((3.0, 0.0), (3.0, 0.1)), 0.1)
