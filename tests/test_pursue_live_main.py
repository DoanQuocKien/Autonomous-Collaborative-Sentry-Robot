"""Main-path tests of tools.pursue_live with fakes for the robot, the video, the SSH link and the detector (no hardware): a normal run, an inference failure,
Ctrl+C and a failed end-of-run battery read must all stop the sender and keep the run evidence (HNHL review of PR #99)."""
import csv
import json
import math
import sys
import time

import numpy as np
import pytest

from sentry.perception.camera import GroundPoint
import tools.pursue_live as pl

W, H = 640, 480


class FakeGeom(object):
    size = (W, H)
    pitch = 0.0
    height_m = 0.1

    @classmethod
    def from_files(cls, *a):
        return cls()

    def undistort_points(self, pts):
        return [tuple(p) for p in pts]

    def ground_point(self, u, v):
        if v <= 210:
            return None
        fwd = 150.0 / (v - 200.0)
        return GroundPoint(fwd, (320.0 - u) / 320.0 * fwd * 0.5)


class Frame(object):
    def __init__(self, seq):
        self.seq = seq
        self.frame_bgr = np.zeros((H, W, 3), dtype=np.uint8)


class FakeRx(object):
    def __init__(self, ip=None):
        self.n = 0

    def start(self):
        pass

    def read(self, timeout=0.5):
        time.sleep(0.02)
        self.n += 1
        return Frame(self.n)

    def close(self):
        pass


class FakeSender(object):
    instances = []

    def __init__(self, ip, port, hz):
        self.sent, self.stopped = [], False
        FakeSender.instances.append(self)

    def send(self, v, w):
        self.sent.append((v, w))

    def close(self, stop=False):
        self.stopped = bool(stop)


def box(dist_m=2.0, u=320.0, h=200.0):
    v = 200.0 + 150.0 / dist_m
    return (u - h / 4, v - h, u + h / 4, v)


def run_main(monkeypatch, tmp_path, perceive_fail_at=None, fail_with=RuntimeError, battery_fails_at_end=False):
    calls = {"n": 0, "volts": 0}

    def make_perception(device_cfg=None):
        def run(frame):
            calls["n"] += 1
            if perceive_fail_at is not None and calls["n"] >= perceive_fail_at:
                raise fail_with("injected")
            return [(1, box())]
        return run

    def volts(_raw):
        calls["volts"] += 1
        if battery_fails_at_end and calls["volts"] >= 2:
            raise OSError("ssh dropped")
        return 12.0

    FakeSender.instances = []
    monkeypatch.setattr(pl, "make_perception", make_perception)
    monkeypatch.setattr("sentry.perception.camera.CameraGeometry.from_files", FakeGeom.from_files)
    monkeypatch.setattr("sentry.net.zmq_rx.ZMQReceiver", FakeRx)
    monkeypatch.setattr("sentry.net.udp_tx.UDPSender", FakeSender)
    monkeypatch.setattr("sentry.net.discover.resolve", lambda ip: "127.0.0.1")
    monkeypatch.setattr("tools.jetbot_ssh.password", lambda p: "x")
    monkeypatch.setattr("tools.jetbot_ssh.connect", lambda *a, **k: object())
    monkeypatch.setattr("tools.jetbot_ssh.sudo", lambda *a, **k: "raw")
    monkeypatch.setattr("tools.calibrate_motion._sh", lambda ssh, cmd: "yes")      # R1 held, latch absent
    monkeypatch.setattr("tools.jetbot_status.ina219_bus_volts", volts)
    monkeypatch.setattr(sys, "argv", ["pursue_live", "--label", "t", "--camera-pose", "x.json", "--seconds", "0.4", "--wait", "5", "--out", str(tmp_path)])
    pl.main()


def saved(tmp_path):
    d = tmp_path / "t_1"
    assert (d / "log.csv").exists() and (d / "summary.json").exists()
    return list(csv.DictReader(open(d / "log.csv"))), json.load(open(d / "summary.json"))


def test_a_normal_run_stops_the_sender_and_saves_the_evidence_with_the_effective_config(monkeypatch, tmp_path):
    run_main(monkeypatch, tmp_path)
    rows, summary = saved(tmp_path)
    assert rows and summary["end_reason"] == "time limit" and summary["battery_v_end"] == 12.0
    assert FakeSender.instances[0].stopped and FakeSender.instances[0].sent                  # commands went out, then the stop at close
    assert summary["config"]["pursuit"]["kp_distance"] > 0 and "dwell_time_s" in summary["config"]["hold_detector"]
    assert "NOT EVALUATED" in summary["acceptance"]


def test_the_config_toml_values_reach_the_controller(monkeypatch, tmp_path):
    import sentry.nav.controllers as c
    real = c.PursuitConfig.from_toml.__func__
    monkeypatch.setattr(c.PursuitConfig, "from_toml", classmethod(lambda cls, path=None: __import__("dataclasses").replace(real(cls), kp_distance=0.123)))
    run_main(monkeypatch, tmp_path)
    _, summary = saved(tmp_path)
    assert math.isclose(summary["config"]["pursuit"]["kp_distance"], 0.123)


def test_an_inference_failure_still_stops_the_sender_and_keeps_the_rows_and_the_reason(monkeypatch, tmp_path):
    with pytest.raises(RuntimeError):
        run_main(monkeypatch, tmp_path, perceive_fail_at=8)                                  # 3 warm-up calls, then a few frames
    rows, summary = saved(tmp_path)
    assert rows and summary["end_reason"].startswith("error: RuntimeError")
    assert FakeSender.instances[0].stopped


def test_ctrl_c_keeps_the_evidence_and_stops_the_sender(monkeypatch, tmp_path):
    with pytest.raises(KeyboardInterrupt):
        run_main(monkeypatch, tmp_path, perceive_fail_at=8, fail_with=KeyboardInterrupt)
    rows, summary = saved(tmp_path)
    assert rows and summary["end_reason"].startswith("error: KeyboardInterrupt")
    assert FakeSender.instances[0].stopped


def test_a_failed_end_battery_read_is_written_as_null_and_nothing_is_lost(monkeypatch, tmp_path):
    run_main(monkeypatch, tmp_path, battery_fails_at_end=True)
    rows, summary = saved(tmp_path)
    assert rows and summary["battery_v_end"] is None and summary["battery_v_start"] == 12.0
    assert FakeSender.instances[0].stopped
