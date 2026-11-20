from types import SimpleNamespace
import sys

import numpy as np
import pytest

from tools import tower_register


@pytest.mark.parametrize('estimate', ['no-frame', None, (-11.0, 1.0, 2, 0.2), (-11.0, 0.1, 1, 0.2)])
def test_registration_deadline_covers_missing_invalid_and_unstable_frames(monkeypatch, tmp_path, estimate):
    clock = {'t': 0.0, 'reads': 0, 'closed': False}

    class Receiver:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            clock['closed'] = True

        def read(self, timeout):
            clock['t'] += min(timeout, 0.1)
            clock['reads'] += 1
            assert clock['reads'] < 20
            return None if estimate == 'no-frame' else SimpleNamespace(frame_bgr=None)

    monkeypatch.setattr(sys, 'argv', ['tower_register', '--frames', '2', '--wait', '0.5', '--out', str(tmp_path)])
    monkeypatch.setattr(tower_register.time, 'time', lambda: clock['t'])
    monkeypatch.setattr(tower_register, 'beep', lambda *args: None)
    monkeypatch.setattr(tower_register, 'resolve', lambda value: '192.0.2.1')
    monkeypatch.setattr(tower_register, 'ZMQReceiver', Receiver)
    monkeypatch.setattr(tower_register, 'undistorter', lambda config: (np.eye(3), lambda image: image))
    monkeypatch.setattr(tower_register, 'detect_corners', lambda image: [(10, np.zeros((4, 2)))])
    monkeypatch.setattr(tower_register, 'face_pitch', lambda *args: estimate)
    tower_register.main()
    assert clock['closed'] and clock['t'] >= 0.5
    assert not list(tmp_path.glob('*.json'))
