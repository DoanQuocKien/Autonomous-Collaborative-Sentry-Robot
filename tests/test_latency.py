import csv

import numpy as np
import pytest

from sentry.net.clock_sync import ClockEstimate
from sentry.net.frame import VideoFrame
from sentry.net.latency import LatencyLogger, percentile


def frame(seq, local_cap, decode_delay=0.02):
    return VideoFrame(seq, local_cap + 100, local_cap + 0.01,
                      local_cap + decode_delay, np.zeros((2, 2, 3), np.uint8), b"jpeg")


def test_latency_clock_sign_raw_csv_fps_and_sequence_gaps(tmp_path):
    path = tmp_path / "latency.csv"
    with LatencyLogger(path, ClockEstimate(100, 0.002, 20, 10)) as log:
        for seq, t in [(0, 10), (2, 10.04), (3, 10.08)]:
            log.write(frame(seq, t))
        metrics = log.summary()
    assert metrics["decoded_latency_p95_ms"] == pytest.approx(20)
    assert metrics["delivered_fps"] == pytest.approx(25)
    assert metrics["sequence_gaps"] == 1
    assert metrics["clock_uncertainty_ms"] == 1
    assert metrics["pass"]
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    assert len(rows) == 3
    assert float(rows[0]["receive_latency_ms"]) == pytest.approx(10)


def test_negative_latency_and_source_restart_cannot_pass(tmp_path):
    with LatencyLogger(tmp_path / "x.csv", ClockEstimate(100, 0.01, 20, 0)) as log:
        log.write(frame(100, 10, -0.01))
        log.write(frame(0, 10.04))
        result = log.summary()
    assert result["negative_latency_frames"] == 1
    assert result["sequence_resets"] == 1
    assert not result["pass"]


def test_empty_run_cannot_pass(tmp_path):
    with LatencyLogger(tmp_path / "x.csv", ClockEstimate(0, 0, 20, 0)) as log:
        assert log.summary()["decoded_latency_p95_ms"] is None
        assert not log.summary()["pass"]


def test_negative_receive_time_is_flagged_even_if_decode_is_positive(tmp_path):
    with LatencyLogger(tmp_path / "x.csv", ClockEstimate(100, 0.01, 20, 0)) as log:
        item = frame(0, 10)
        item = VideoFrame(item.seq, item.t_cap, 9.99, item.t_decode, item.frame_bgr, item.jpeg)
        log.write(item)
        log.write(frame(1, 10.04))
        assert log.summary()["negative_latency_frames"] == 1
        assert not log.summary()["pass"]


def test_percentile_interpolation():
    assert percentile([10, 0, 20], 0.95) == pytest.approx(19)
    assert percentile([7], 0.95) == 7
