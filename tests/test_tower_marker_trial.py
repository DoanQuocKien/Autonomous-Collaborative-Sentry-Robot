import cv2
import numpy as np
import pytest

from sentry.perception.camera import CameraGeometry
from sentry.perception.camera_pose import DICT
from tools.tower_marker_trial import drive_seconds, look


def _frame(marker_id, side=40):
    img = np.full((480, 640), 255, np.uint8)
    m = cv2.aruco.generateImageMarker(cv2.aruco.getPredefinedDictionary(DICT), marker_id, side)
    img[200:200 + side, 300:300 + side] = m
    return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)


def test_look_only_tower_ids():
    g = CameraGeometry.from_files("calib/camera.json", "calib/camera_pose_nowedge.json")
    obj = np.array([[-.025, .025, 0], [.025, .025, 0], [.025, -.025, 0], [-.025, -.025, 0]], np.float64)
    assert look(g, obj, _frame(0)) is None                   # a room board is not the tower
    r = look(g, obj, _frame(11))
    assert r is not None and r[0] == 11 and 30 < r[3] < 50


def test_drive_seconds_keeps_the_floor():
    gain, v = 0.4135, 0.5
    t = drive_seconds(1.4, v, gain)
    assert t * gain * v * 1.15 <= 1.4 + 1e-9 and drive_seconds(-1, v, gain) == 0.0


def test_nonfinite_battery_limit_is_rejected_before_connecting(monkeypatch):
    import sys
    from tools import tower_marker_trial as trial
    monkeypatch.setattr(sys, 'argv', ['tower_marker_trial', 'approach', '1.5', '--min-battery', 'nan'])
    with pytest.raises(SystemExit) as exc:
        trial.main()
    assert exc.value.code == 2


@pytest.mark.parametrize('v,w,expiry', [(0.5, 0.0, 0.26), (0.0, 0.5, 0.09)])
def test_sender_expires_commands_without_another_video_frame(monkeypatch, v, w, expiry):
    import threading
    from tools import tower_marker_trial as trial
    done = threading.Event()
    sent, closed = [], []

    class Sender:
        period_s = 0

        def __init__(self, *args):
            pass

        def send(self, v, w):
            sent.append((v, w))
            if len(sent) == 3:
                done.set()

        def close(self, stop):
            closed.append(stop)

    monkeypatch.setattr(trial, 'UDPSender', Sender)
    times = iter([100.0, 100.01, 100.0 + expiry])
    trial.send_commands({'v': v, 'w': w, 't': 100.0}, done, '192.0.2.1', 5555, clock=times.__next__)
    assert sent == [(v, w), (v, w), (0.0, 0.0)]
    assert closed == [True]


@pytest.mark.parametrize('battery', [10.0, 12.0])
def test_main_checks_battery_before_starting_and_uses_selected_video_ip(monkeypatch, battery):
    import sys
    from sentry.net import discover
    from tools import tower_marker_trial as trial
    selected, started = [], []
    monkeypatch.setattr(sys, 'argv', ['tower_marker_trial', 'approach', '1.5', '--ip', '192.0.2.1', '--password', 'fixture'])
    monkeypatch.setattr(discover, 'resolve', lambda ip: ip)
    monkeypatch.setattr(trial.jetbot_ssh, 'password', lambda value: value)
    monkeypatch.setattr(trial.jetbot_ssh, 'connect', lambda *args: object())
    monkeypatch.setattr(trial.jetbot_ssh, 'sudo', lambda *args: 'fixture')
    monkeypatch.setattr(trial, 'ina219_bus_volts', lambda value: battery)
    monkeypatch.setattr(trial, '_sh', lambda *args: '0')

    class Thread:
        def __init__(self, **kwargs):
            pass

        def start(self):
            started.append(True)

        def join(self, *args, **kwargs):
            pass

    def receiver(**kwargs):
        selected.append(kwargs['ip'])
        raise RuntimeError('fixture video abort')

    monkeypatch.setattr(trial.threading, 'Thread', Thread)
    monkeypatch.setattr(trial, 'ZMQReceiver', receiver)
    if battery < 11.1:
        with pytest.raises(SystemExit, match='battery'):
            trial.main()
        assert not started and not selected
    else:
        with pytest.raises(RuntimeError, match='fixture video abort'):
            trial.main()
        assert started == [True] and selected == ['192.0.2.1']
