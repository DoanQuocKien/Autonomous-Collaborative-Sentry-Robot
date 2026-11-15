"""Regression (audit 2026-11-12): speed_trial and turn_trial streamed the last command forever when the main thread died (non-daemon sender thread, no try/finally). All hardware faked."""
import sys
import threading
import time

import pytest

import sentry.net.discover as disc
from tools import jetbot_ssh

SENT = []


class FakeSender:
    period_s = 1 / 60.0

    def __init__(self, *a, **k):
        pass

    def send(self, v, w):
        SENT.append((time.time(), v, w))
        return True

    def close(self, stop=True):
        SENT.append((time.time(), "CLOSE", 0))


class FakeRx:
    n = 0

    def __enter__(self):
        FakeRx.n = 0
        return self

    def __exit__(self, *e):
        pass

    def read(self, timeout=None):
        FakeRx.n += 1
        time.sleep(0.01)
        if FakeRx.n > 40:
            raise RuntimeError("video receiver failed")            # what ZMQReceiver.read raises when its worker dies

        class F:
            frame_bgr = None
        return F


class FakeGeom:
    @staticmethod
    def from_files(*a):
        return None


@pytest.mark.parametrize("which", ["speed_trial", "turn_trial"])
def test_no_command_after_the_main_thread_dies(which, monkeypatch):
    SENT.clear()
    monkeypatch.setattr(disc, "resolve", lambda ip: "127.0.0.1")
    monkeypatch.setattr(jetbot_ssh, "connect", lambda *a, **k: object())
    monkeypatch.setattr(jetbot_ssh, "sudo", lambda *a, **k: "0xd25d")
    mod = __import__("tools." + which, fromlist=["x"])
    monkeypatch.setattr(mod, "UDPSender", FakeSender)
    monkeypatch.setattr(mod, "ZMQReceiver", FakeRx)
    monkeypatch.setattr(mod, "_sh", lambda c, cmd: "0" if "wc -l" in cmd else "yes")
    monkeypatch.setattr(mod, "beep", lambda *a: None, raising=False)
    monkeypatch.setattr(mod, "CameraGeometry", FakeGeom)
    if which == "speed_trial":
        monkeypatch.setattr(mod, "marker_range", lambda g, obj, img: (2.0, 0.0))
        monkeypatch.setattr(sys, "argv", ["x", "0.7", "4", "--password", "x", "--ip", "1.2.3.4"])
    else:
        monkeypatch.setattr(mod, "bearings_from_axle", lambda *a: {0: 0.0})
        monkeypatch.setattr(sys, "argv", ["x", "0.8", "1.0", "--password", "x", "--ip", "1.2.3.4"])
    err = []

    def run():
        try:
            mod.main()
        except BaseException as e:                                   # noqa: BLE001
            err.append(repr(e))
    t = threading.Thread(target=run)
    t.start()
    t.join(30)
    assert not t.is_alive() and err and "video receiver failed" in err[0], err
    t_dead = time.time()
    time.sleep(0.6)
    late = [s for s in SENT if s[0] > t_dead + 0.1]
    assert not late, "commands kept streaming after main() died: %d, last %r" % (len(late), late[-1][1:])
    assert not [th for th in threading.enumerate() if th.name.endswith("(sender)")]
