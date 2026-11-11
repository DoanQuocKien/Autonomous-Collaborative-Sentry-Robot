import json
import sys
import time

import numpy as np
import pytest

import tools.link_cut_test as lc
from tools.link_cut_test import stop_time, threshold, validate_trial


def test_stop_time_is_the_first_moment_the_picture_stays_still_after_the_cut():
    series = [(0.0, 9.0), (0.1, 9.0), (0.2, 8.0), (0.3, 0.4), (0.4, 7.0), (0.5, 0.3), (0.6, 0.2), (0.7, 0.2)]
    thr = threshold(0.3, 9.0)                      # 0.3 + 25 % of the gap = 2.475
    assert abs(thr - 2.475) < 1e-9
    assert stop_time(series, 0.15, thr) == 0.5     # a single quiet frame (0.3 s) is not enough, two in a row are
    assert stop_time(series, 0.6, thr) == 0.6
    assert stop_time([(0.0, 9.0), (0.1, 9.0)], 0.0, thr) is None   # never stops


def test_a_trial_is_valid_only_with_samples_clear_motion_r1_held_and_a_confirmed_send():
    assert validate_trial(40, 40, 30, 0.9, 12.0, True, 100.0, True) == (True, "")
    assert not validate_trial(40, 40, 30, 0.9, 12.0, True, None, True)[0]            # no confirmed send
    assert not validate_trial(5, 40, 30, 0.9, 12.0, True, 100.0, True)[0]            # too few rest frames
    assert not validate_trial(40, 5, 30, 0.9, 12.0, True, 100.0, True)[0]            # too few spin frames
    assert not validate_trial(40, 40, 3, 0.9, 12.0, True, 100.0, True)[0]            # too few frames after the cut
    assert not validate_trial(40, 40, 30, 0.9, 1.5, True, 100.0, True)[0]            # the picture hardly moved before the cut: a "stop" would prove nothing
    ok, why = validate_trial(40, 40, 30, 0.9, 12.0, False, 100.0, True)
    assert not ok and "R1" in why                                              # R1 released at the cut: the stop may be the release (HNHL, trial 4)
    ok, why = validate_trial(40, 40, 30, 0.9, 12.0, True, 100.0, False)
    assert not ok and "unconfirmed" in why


# ---- the real main path with fakes: no robot, no network ----
class FakeSender:
    instances = []

    def __init__(self, ip, port, hz):
        self.last_send, self.stopped, self.closed, self.n = 0.0, False, False, 0
        FakeSender.instances.append(self)

    def send(self, v, w):
        self.n += 1
        if self.n % 3 == 0:
            return False                                                       # a rate-limited send: must not count as the cutoff
        FakeSender.last_send = time.time()
        return True

    def close(self, stop=False):
        self.closed, self.stopped = True, bool(stop)


class FakeFrame:
    def __init__(self, img):
        self.frame_bgr = img


class FakeRx:
    fail_at = None
    exc = RuntimeError

    def __init__(self, ip=None):
        self.n, self.rng = 0, np.random.default_rng(0)
        self.static = np.full((480, 640, 3), 90, dtype=np.uint8)

    def start(self):
        pass

    def read(self, timeout=0.2):
        time.sleep(0.02)
        self.n += 1
        if FakeRx.fail_at is not None and self.n >= FakeRx.fail_at:
            raise FakeRx.exc("injected")
        moving = time.time() - getattr(FakeSender, "last_send", 0.0) < 0.12      # the picture moves while packets keep arriving, and stops soon after they stop
        img = self.rng.integers(0, 255, (480, 640, 3), dtype=np.uint8) if moving else self.static
        return FakeFrame(img)

    def close(self):
        self.closed = True


def run_main(monkeypatch, tmp_path, ssh_fail=False, r1_after_cut=True, trials=2, ack=True):
    FakeSender.instances, FakeSender.last_send = [], 0.0
    state = {"r1": 0}

    def sh(ssh_, cmd):
        if ssh_fail and state["r1"] >= 4:
            raise OSError("ssh dropped")
        state["r1"] += 1
        if not r1_after_cut and FakeSender.instances and time.time() - FakeSender.last_send > 0.3:
            return "no"
        return "yes"

    monkeypatch.setattr("winsound.Beep", lambda *a: None)
    monkeypatch.setattr("sentry.net.discover.resolve", lambda ip: "127.0.0.1")
    monkeypatch.setattr("sentry.net.zmq_rx.ZMQReceiver", FakeRx)
    monkeypatch.setattr("sentry.net.udp_tx.UDPSender", FakeSender)
    monkeypatch.setattr("tools.jetbot_ssh.password", lambda p: "x")
    monkeypatch.setattr("tools.jetbot_ssh.connect", lambda *a, **k: object())
    monkeypatch.setattr("tools.jetbot_ssh.sudo", lambda *a, **k: "raw")
    monkeypatch.setattr("tools.calibrate_motion._sh", sh)
    monkeypatch.setattr("tools.jetbot_status.ina219_bus_volts", lambda raw: 12.0)
    argv = ["link_cut_test", "--label", "t", "--trials", str(trials), "--spin-s", "0.6", "--rest-s", "0.6", "--post-s", "0.5", "--pause", "0", "--wait", "5", "--out", str(tmp_path)]
    if ack:
        argv.append("--wheels-on-ground-ack")
    monkeypatch.setattr(sys, "argv", argv)
    lc.main()


def saved(tmp_path):
    d = tmp_path / "t_1"
    assert (d / "summary.json").exists()
    return d, json.loads((d / "summary.json").read_text())


def test_without_the_wheels_on_ground_acknowledgement_nothing_starts(monkeypatch, tmp_path):
    with pytest.raises(SystemExit):
        run_main(monkeypatch, tmp_path, ack=False)
    assert FakeSender.instances == [] and list(tmp_path.iterdir()) == []


def test_a_normal_run_counts_only_valid_trials_stops_every_sender_and_keeps_the_evidence(monkeypatch, tmp_path):
    FakeRx.fail_at = None
    run_main(monkeypatch, tmp_path)
    d, summary = saved(tmp_path)
    assert summary["trials"] == 2 and summary["valid_trials"] == 2 and summary["end_reason"] == "completed"
    assert all(0.0 < x < 0.6 for x in summary["upper_bound_s"])
    assert len(FakeSender.instances) == 2 and all(s.closed and s.stopped for s in FakeSender.instances)
    assert (d / "trials.csv").exists()


@pytest.mark.parametrize("exc", [KeyboardInterrupt, RuntimeError])
def test_an_interrupt_or_receiver_error_still_stops_and_closes_the_sender_and_keeps_partial_evidence(monkeypatch, tmp_path, exc):
    FakeRx.fail_at, FakeRx.exc = 60, exc                                        # fails during the first trial's spin
    try:
        with pytest.raises(exc):
            run_main(monkeypatch, tmp_path)
    finally:
        FakeRx.fail_at, FakeRx.exc = None, RuntimeError
    _, summary = saved(tmp_path)
    assert summary["end_reason"].startswith("error: " + exc.__name__) and summary["valid_trials"] == 0
    assert FakeSender.instances and all(s.closed and s.stopped for s in FakeSender.instances)


def test_an_ssh_failure_at_the_r1_check_still_cleans_up(monkeypatch, tmp_path):
    FakeRx.fail_at = None
    with pytest.raises(OSError):
        run_main(monkeypatch, tmp_path, ssh_fail=True)
    _, summary = saved(tmp_path)
    assert summary["end_reason"].startswith("error: OSError")
    assert FakeSender.instances and all(s.closed and s.stopped for s in FakeSender.instances)


def test_r1_release_before_end_check_is_not_a_valid_watchdog_trial(monkeypatch, tmp_path):
    FakeRx.fail_at = None
    run_main(monkeypatch, tmp_path, r1_after_cut=False, trials=1)
    _, summary = saved(tmp_path)
    assert summary['trials'] == 1 and summary['valid_trials'] == 0
    assert summary['upper_bound_s'] == []
    assert 'unconfirmed' in summary['invalid_trials'][0][1]
    assert all(s.closed and s.stopped for s in FakeSender.instances)


def test_run_directories_are_never_overwritten(monkeypatch, tmp_path):
    FakeRx.fail_at = None
    (tmp_path / "t_1").mkdir()
    (tmp_path / "t_1" / "summary.json").write_text("OLD EVIDENCE")
    run_main(monkeypatch, tmp_path, trials=1)
    assert (tmp_path / "t_1" / "summary.json").read_text() == "OLD EVIDENCE" and (tmp_path / "t_2" / "summary.json").exists()
