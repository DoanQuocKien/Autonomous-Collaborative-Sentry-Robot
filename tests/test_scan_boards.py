import math
import json
import sys
import types

import numpy as np
import pytest

from tools.scan_boards import beep, camera_to_robot, pulse_angle, to_start_frame


def test_beep_runs_without_raising():
    beep(1000, 10)


def test_the_pulse_angle_is_the_fall_of_a_fixed_boards_bearing_median_over_boards():
    prev = {0: (math.radians(10), 3.0), 2: (math.radians(-50), 2.0), 5: (math.radians(80), 0.6)}      # id 5 is too near (0.6 m): ignored
    cur = {0: (math.radians(-15), 3.0), 2: (math.radians(-75), 2.0), 5: (math.radians(10), 0.6)}
    ang, n = pulse_angle(prev, cur)
    assert n == 2 and abs(math.degrees(ang) - 25.0) < 1e-9
    assert pulse_angle({0: (0.0, 3.0)}, {1: (0.0, 3.0)}) == (None, 0)                                  # no board in common
    ang, _ = pulse_angle({0: (math.radians(-165), 3.0)}, {0: (math.radians(170), 3.0)})                # across the +/-180 wrap
    assert abs(math.degrees(ang) - 25.0) < 1e-9


def test_a_point_ahead_of_a_robot_turned_left_goes_to_the_left_in_the_start_frame():
    x, y = to_start_frame(2.0, 0.0, math.radians(90))
    assert abs(x) < 1e-9 and abs(y - 2.0) < 1e-9
    x, y = to_start_frame(1.0, 1.0, 0.0)
    assert (x, y) == (1.0, 1.0)


def test_camera_frame_to_forward_and_left_with_a_pitched_camera():
    f, l = camera_to_robot([-0.5, 0.0, 2.0], 0.0)                              # 0.5 m to the right of the axis, 2 m ahead
    assert abs(f - 2.0) < 1e-9 and abs(l - 0.5) < 1e-9
    f, l = camera_to_robot([0.0, 0.0, 2.0], math.radians(-14))                 # looking up 14 deg: a point on the axis is nearer in forward
    assert abs(f - 2.0 * math.cos(math.radians(14))) < 1e-9


@pytest.mark.parametrize("duration", ["0.1", "0.3", "nan"])
def test_uncalibrated_pulse_is_rejected_before_robot_setup(monkeypatch, duration):
    from tools import scan_boards as scan
    monkeypatch.setattr(sys, "argv", ["scan_boards", "--label", "test", "--camera-pose", "missing.json", "--spin-s", duration])
    with pytest.raises(SystemExit):
        scan.main()


@pytest.fixture
def scan_main(monkeypatch, tmp_path):
    from tools import scan_boards as scan

    class Clock:
        t = 100.0
        def time(self):
            self.t += 0.01
            return self.t
        def perf_counter(self):
            return self.t
        def sleep(self, seconds):
            self.t += seconds
        def strftime(self, fmt):
            return "2026-11-11"

    clock = Clock()
    state = dict(mode="fresh", reads=0, commands=[], closed=False, stopped=False, rx_closed=False, started=False)

    class Receiver:
        def __init__(self, **kwargs): pass
        def start(self):
            state["started"] = True
        def read(self, timeout):
            state["reads"] += 1
            clock.sleep(0.05)
            if state["mode"] == "interrupt" and state["reads"] > 6:
                raise KeyboardInterrupt()
            if state["mode"] == "error" and state["reads"] > 6:
                raise RuntimeError("injected receiver error")
            if (state["mode"] == "none"
                    or state["mode"] == "lost" and state["reads"] > 6
                    or state["mode"] == "partial" and state["reads"] > 3):
                return None
            age = 5.0 if state["mode"] == "stale" else 0.0
            return types.SimpleNamespace(t_rx=clock.perf_counter() - age, frame_bgr=np.zeros((10, 10, 3), np.uint8))
        def close(self):
            state["rx_closed"] = True

    class Sender:
        def __init__(self, *args): pass
        def send(self, v, w):
            state["commands"].append((v, w))
        def stop(self):
            state["commands"].append((0.0, 0.0))
        def close(self, stop=True):
            state["closed"], state["stopped"] = True, stop

    def detect(frame):
        if state["mode"] == "slow":
            clock.sleep(0.6)
        return []

    monkeypatch.setattr(scan, "time", clock)
    monkeypatch.setitem(sys.modules, "winsound", types.SimpleNamespace(Beep=lambda *args: None))
    monkeypatch.setattr("sentry.net.discover.resolve", lambda ip: "fake")
    monkeypatch.setattr("sentry.net.zmq_rx.ZMQReceiver", Receiver)
    monkeypatch.setattr("sentry.net.udp_tx.UDPSender", Sender)
    monkeypatch.setattr("sentry.nav.localization.LocalizationTracker", lambda **kwargs: types.SimpleNamespace(detect_markers=detect))
    monkeypatch.setattr("tools.jetbot_ssh.password", lambda p: "fake")
    monkeypatch.setattr("tools.jetbot_ssh.connect", lambda *args: object())
    monkeypatch.setattr("tools.jetbot_ssh.sudo", lambda *args: "raw")
    monkeypatch.setattr("tools.calibrate_motion._sh", lambda *args: "yes")
    monkeypatch.setattr("tools.jetbot_status.ina219_bus_volts", lambda *args: 12.0)
    pose = tmp_path / "pose.json"
    pose.write_text('{"pitch_down_deg": 0}')

    def run(mode="fresh", dry=False):
        state["mode"] = mode
        argv = ["scan_boards", "--label", "test", "--camera-pose", str(pose), "--max-pulses", "1", "--out", str(tmp_path)]
        if dry:
            argv.append("--dry-run")
        monkeypatch.setattr(sys, "argv", argv)
        scan.main()

    return run, state, tmp_path


@pytest.mark.parametrize("mode", ["none", "stale", "partial", "slow"])
def test_no_spin_without_a_complete_fresh_video_sample(scan_main, mode):
    run, state, out = scan_main
    with pytest.raises(RuntimeError, match="video"):
        run(mode)
    assert not any(w != 0 for v, w in state["commands"])
    assert state["closed"] and state["stopped"] and state["rx_closed"]
    summary = json.loads((out / "test_1/summary.json").read_text())
    assert summary["end_reason"].startswith("error:") and summary["pulses"] == 0


@pytest.mark.parametrize("mode,exc", [("lost", RuntimeError), ("interrupt", KeyboardInterrupt), ("error", RuntimeError)])
def test_video_failure_after_one_pulse_stops_and_preserves_partial_evidence(scan_main, mode, exc):
    run, state, out = scan_main
    with pytest.raises(exc):
        run(mode)
    assert any(w != 0 for v, w in state["commands"])
    assert state["commands"][-1] == (0.0, 0.0)
    assert state["closed"] and state["stopped"] and state["rx_closed"]
    assert json.loads((out / "test_1/summary.json").read_text())["end_reason"].startswith("error:")


def test_fresh_video_without_markers_can_use_the_calibrated_prior(scan_main):
    run, state, out = scan_main
    run()
    summary = json.loads((out / "test_1/summary.json").read_text())
    assert any(w != 0 for v, w in state["commands"])
    assert summary["pulses"] == 1 and summary["pulses_measured"] == 0
    assert summary["total_heading_deg"] == 25.1 and summary["spin_s"] == 0.2
    assert state["closed"] and state["stopped"]


def test_dry_scan_samples_video_without_sending_motor_commands(scan_main):
    run, state, out = scan_main
    run(dry=True)
    assert state["commands"] == [] and state["rx_closed"]
    assert json.loads((out / "test_1/summary.json").read_text())["end_reason"] == "dry run"
