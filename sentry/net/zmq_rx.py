"""Threaded multipart video receiver, with a single latest decoded frame slot.

Do NOT set ZMQ_CONFLATE: libzmq does not support it for multipart messages.
Instead use a bounded queue and drain complete messages before decoding. The
worker owns its socket throughout its lifetime; no socket crosses threads.
"""
import threading
import time

import cv2
import numpy as np
import zmq

from common.protocol import decode_video_header
from sentry.config import load
from sentry.net.frame import VideoFrame


def decode_frame(parts, t_rx, *, clock=time.perf_counter):
    if len(parts) != 2:
        raise ValueError("expected [header_json, jpeg_bytes]")
    header = decode_video_header(parts[0])
    if header["seq"] < 0 or header["w"] <= 0 or header["h"] <= 0:
        raise ValueError("invalid sequence or frame dimensions")
    if not parts[1]:
        raise ValueError("empty JPEG")
    image = cv2.imdecode(np.frombuffer(parts[1], np.uint8), cv2.IMREAD_COLOR)
    if image is None or image.shape[:2] != (header["h"], header["w"]):
        raise ValueError("invalid JPEG or dimensions differ from header")
    return VideoFrame(header["seq"], header["t_cap"], t_rx, clock(), image, parts[1])


class ZMQReceiver:
    """Single consumer: read() waits, consumes the latest frame, or returns None.

    Frames deliberately skipped by the consumer are not queued. seq and t_cap
    preserve source values, including resets when the publisher restarts.
    A stopped/failed worker wakes readers; failures raise RuntimeError.
    """
    def __init__(self, ip=None, port=None, *, endpoint=None):
        cfg = load()["net"]
        self.endpoint = endpoint or "tcp://%s:%d" % (
            cfg["jetbot_ip"] if ip is None else ip,
            cfg["video_port"] if port is None else port)
        self._hwm = cfg["video_rcvhwm"]
        self._poll_ms = cfg["video_poll_ms"]
        self._drain_limit = cfg["video_drain_limit"]
        self._join_s = cfg["video_join_timeout_s"]
        if min(self._hwm, self._poll_ms, self._drain_limit, self._join_s) <= 0:
            raise ValueError("receiver bounds must be positive")
        self._condition = threading.Condition()
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread = None
        self._latest = None
        self._error = None
        self._closed = False
        self.received = 0
        self.invalid = 0
        self.skipped = 0

    def start(self):
        if self._closed:
            raise RuntimeError("receiver is closed")
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="sentry-video", daemon=True)
            self._thread.start()
            if not self._ready.wait(self._join_s):
                self.close()
                raise TimeoutError("video receiver failed to start")
        self._raise_error()
        return self

    def _raise_error(self):
        if self._error is not None:
            raise RuntimeError("video receiver failed") from self._error

    def _run(self):
        ctx = sock = None
        try:
            ctx = zmq.Context()
            sock = ctx.socket(zmq.SUB)
            sock.setsockopt(zmq.LINGER, 0)
            sock.setsockopt(zmq.RCVHWM, self._hwm)
            sock.setsockopt(zmq.SUBSCRIBE, b"")
            sock.connect(self.endpoint)
            self._ready.set()
            while not self._stop.is_set():
                if not sock.poll(self._poll_ms):
                    continue
                parts = sock.recv_multipart()
                t_rx = time.perf_counter()
                self.received += 1
                for _ in range(self._drain_limit - 1):
                    try:
                        newer = sock.recv_multipart(zmq.NOBLOCK)
                    except zmq.Again:
                        break
                    parts, t_rx = newer, time.perf_counter()
                    self.received += 1
                    self.skipped += 1
                try:
                    frame = decode_frame(parts, t_rx)
                except (ValueError, cv2.error):
                    self.invalid += 1
                    continue
                with self._condition:
                    if self._stop.is_set():
                        break
                    if self._latest is not None:
                        self.skipped += 1
                    self._latest = frame
                    self._condition.notify_all()
        except Exception as exc:
            self._error = exc
        finally:
            try:
                try:
                    if sock is not None:
                        sock.close(linger=0)
                finally:
                    if ctx is not None:
                        ctx.term()
            except Exception as exc:
                if self._error is None:
                    self._error = exc
            finally:
                self._stop.set()
                self._ready.set()
                with self._condition:
                    self._condition.notify_all()

    def read(self, timeout=None):
        if self._thread is None:
            raise RuntimeError("start the receiver before reading")
        if timeout is not None and (not np.isfinite(timeout) or timeout < 0):
            raise ValueError("timeout must be nonnegative and finite")
        with self._condition:
            self._condition.wait_for(
                lambda: self._latest is not None or self._stop.is_set(), timeout)
            self._raise_error()
            frame, self._latest = self._latest, None
            return frame

    def close(self):
        self._closed = True
        self._stop.set()
        with self._condition:
            self._latest = None
            self._condition.notify_all()
        if self._thread is not None:
            self._thread.join(self._join_s)
            if self._thread.is_alive():
                raise TimeoutError("video worker did not stop")

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.close()
