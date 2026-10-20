"""T0 unit tests for sentry/net/mjpeg_rx.py (HTTP MJPEG receiver with auto-reconnect)."""
import io
import itertools
import threading
import time
import urllib.error

import cv2
import numpy as np
import pytest

from sentry.net.mjpeg_rx import MAX_JPEG, MJPEGReceiver, decode_jpeg, split_jpegs
from tools.esp_mjpeg_relay import make_server


def _make_jpeg(color=(20, 100, 220), w=64, h=48):
    img = np.full((h, w, 3), color, np.uint8)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    assert ok
    return buf.tobytes()


def test_split_jpegs_handles_midstream_eoi_and_runaway_buffer():
    j1 = _make_jpeg((10, 20, 30))
    j2 = _make_jpeg((40, 50, 60))
    # Stray EOI before the first SOI must be ignored
    stream = b"garbage\xff\xd9header" + j1 + b"\r\n--frame\r\n" + j2 + b"\xff\xd8partial"
    found, rest = split_jpegs(stream)
    assert found == [j1, j2]
    assert rest == b"\xff\xd8partial"

    # Runaway incomplete buffer larger than MAX_JPEG is dropped
    runaway = b"\xff\xd8" + (b"x" * (MAX_JPEG + 10))
    found2, rest2 = split_jpegs(runaway)
    assert found2 == [] and rest2 == b""


def test_decode_jpeg_returns_video_frame_and_rejects_bad_bytes():
    raw = _make_jpeg((30, 120, 210), w=80, h=60)
    vf = decode_jpeg(raw, seq=4, t_rx=10.5, clock=lambda: 10.502)
    assert (vf.seq, vf.t_cap, vf.t_rx, vf.t_decode) == (4, 10.5, 10.5, 10.502)
    assert (vf.w, vf.h) == (80, 60)
    assert vf.jpeg == raw
    assert np.max(np.abs(vf.frame_bgr[0, 0].astype(int) - [30, 120, 210])) <= 4

    with pytest.raises(ValueError):
        decode_jpeg(b"", 0, 1.0)
    with pytest.raises(ValueError):
        decode_jpeg(b"not a jpeg", 0, 1.0)
    with pytest.raises(ValueError):
        decode_jpeg(raw, -1, 1.0)


class _ChunkStream:
    """Fake HTTP response yielding a sequence of byte chunks and optionally raising an error."""

    def __init__(self, chunks, tail_exc=None):
        self._chunks = list(chunks)
        self._tail_exc = tail_exc

    def read(self, size=-1):
        if self._chunks:
            return self._chunks.pop(0)
        if self._tail_exc is not None:
            raise self._tail_exc
        return b""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass


def test_auto_reconnect_recovers_after_connection_failure_and_eof():
    j1 = _make_jpeg((15, 25, 35))
    j2 = _make_jpeg((115, 125, 135))
    attempts = []

    def fake_urlopen(req, timeout=None):
        idx = len(attempts)
        attempts.append((req.full_url, timeout))
        if idx == 0:
            raise urllib.error.URLError("board still booting")
        if idx == 1:
            # Sends one frame, then drops with ConnectionResetError
            return _ChunkStream([j1[:20], j1[20:]], tail_exc=ConnectionResetError("wifi drop"))
        if idx == 2:
            # Sends second frame, then clean EOF
            return _ChunkStream([j2])
        # Hold briefly once both frames are delivered
        time.sleep(0.02)
        return _ChunkStream([])

    with MJPEGReceiver(
        url="http://192.168.137.55:81/stream",
        reconnect_s=0.005,
        request_timeout_s=1.0,
        urlopen=fake_urlopen,
    ) as rx:
        f1 = rx.read(timeout=2.0)
        assert f1 is not None and f1.seq == 0 and f1.jpeg == j1
        f2 = rx.read(timeout=2.0)
        assert f2 is not None and f2.seq == 1 and f2.jpeg == j2
        bgr, fid, age = rx.latest()
        assert bgr is not None and not bgr.flags.writeable and fid == 1 and age >= 0.0
        assert rx.reconnects >= 2
        assert rx.frames == 2


def test_multiple_jpegs_in_one_chunk_keeps_newest_and_counts_skipped():
    j1 = _make_jpeg((10, 10, 10))
    j2 = _make_jpeg((90, 90, 90))
    j3 = _make_jpeg((200, 200, 200))
    delivered = threading.Event()

    def fake_urlopen(req, timeout=None):
        if not delivered.is_set():
            delivered.set()
            return _ChunkStream([j1 + j2 + j3])
        time.sleep(0.02)
        return _ChunkStream([])

    with MJPEGReceiver(
        url="http://127.0.0.1:81/stream",
        reconnect_s=0.01,
        chunk_size=1 << 20,
        urlopen=fake_urlopen,
    ) as rx:
        frame = rx.read(timeout=2.0)
        assert frame is not None
        assert frame.jpeg == j3
        assert rx.received == 3
        assert rx.frames == 1
        assert rx.skipped == 2


def test_loopback_with_esp_mjpeg_relay_server():
    class Source:
        def __init__(self):
            self.n = itertools.count(1)

        def latest(self):
            i = next(self.n)
            return np.full((60, 80, 3), (i * 30) % 240, np.uint8), i, 0.0

    srv = make_server(Source(), port=0, fps=60.0, host="127.0.0.1")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    try:
        with MJPEGReceiver("127.0.0.1", port=port, reconnect_s=0.05) as rx:
            f0 = rx.read(timeout=2.0)
            f1 = rx.read(timeout=2.0)
            assert f0 is not None and f1 is not None
            assert (f0.w, f0.h) == (80, 60)
            assert f1.seq > f0.seq
            bgr, fid, age = rx.latest()
            assert bgr.shape == (60, 80, 3) and fid == f1.seq and age < 2.0
    finally:
        srv.shutdown()


def test_validation_and_unstarted_receiver_errors():
    with pytest.raises(ValueError):
        MJPEGReceiver(url="http://127.0.0.1:81/stream", reconnect_s=-1)
    with pytest.raises(ValueError):
        MJPEGReceiver(url="http://127.0.0.1:81/stream", request_timeout_s=0)
    rx = MJPEGReceiver(url="http://127.0.0.1:81/stream")
    assert rx.latest() == (None, -1, float("inf"))
    with pytest.raises(RuntimeError):
        rx.read(timeout=0.1)
    rx.close()
    with pytest.raises(RuntimeError):
        rx.start()
