"""Threaded HTTP MJPEG receiver for the ESP32-CAM (OV2640 sketch or tools/esp_mjpeg_relay.py) with auto-reconnect.

The GC2145 boards use the UDP tile stream in `sentry.espcam.TileReceiver` (frozen interface, docs/ESP32-CAM.md).
This module covers the HTTP MJPEG path (`http://<esp32-ip>:81/stream`) and exposes both:
  * `read(timeout=None) -> VideoFrame | None` (single-consumer contract, matching `ZMQReceiver`)
  * `latest() -> (frame_bgr, frame_id, age_s)` (shared read-only latest frame, matching `TileReceiver`)
"""
import http.client
import math
import threading
import time
import urllib.error
import urllib.request

import cv2
import numpy as np

from sentry.config import load
from sentry.net.discover import resolve_esp32
from sentry.net.frame import VideoFrame

MAX_JPEG = 2 << 20  # an MJPEG buffer that grows past this without a complete picture is resynchronised


def split_jpegs(buf):
    """-> (complete JPEGs (SOI ... EOI) in an MJPEG byte buffer, the bytes left over).

    The EOI is searched AFTER the SOI, so a stray EOI before it (joining mid-picture)
    cannot stall the parser; a runaway buffer is cut back.
    """
    out, pos = [], 0
    while True:
        a = buf.find(b"\xff\xd8", pos)
        b = buf.find(b"\xff\xd9", a + 2) if a >= 0 else -1
        if b < 0:
            rest = buf[a:] if a >= 0 else b""
            return out, (rest if len(rest) <= MAX_JPEG else b"")
        out.append(buf[a:b + 2])
        pos = b + 2


def decode_jpeg(jpeg_bytes, seq, t_rx, *, clock=time.perf_counter):
    """Decode one JPEG payload into a VideoFrame."""
    if seq < 0:
        raise ValueError("seq must be nonnegative")
    if not jpeg_bytes:
        raise ValueError("empty JPEG")
    image = cv2.imdecode(np.frombuffer(jpeg_bytes, np.uint8), cv2.IMREAD_COLOR)
    if image is None or image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("invalid JPEG bytes")
    t_decode = clock()
    return VideoFrame(seq, t_rx, t_rx, t_decode, image, bytes(jpeg_bytes))


class MJPEGReceiver:
    """HTTP MJPEG stream reader with automatic reconnect and latest-frame slot.

    When the stream drops, refuses connection, or times out, the background worker
    increments `reconnects`, waits `reconnect_s`, and reconnects until `close()`/`stop()`.
    """

    def __init__(
        self,
        ip=None,
        port=81,
        path="/stream",
        *,
        url=None,
        reconnect_s=1.0,
        request_timeout_s=5.0,
        chunk_size=4096,
        join_timeout_s=None,
        urlopen=urllib.request.urlopen,
        clock=time.perf_counter,
    ):
        cfg = load()["net"]
        if join_timeout_s is None:
            join_timeout_s = cfg["video_join_timeout_s"]
        if not math.isfinite(reconnect_s) or reconnect_s < 0:
            raise ValueError("reconnect_s must be nonnegative and finite")
        if not math.isfinite(request_timeout_s) or request_timeout_s <= 0:
            raise ValueError("request_timeout_s must be positive and finite")
        if int(chunk_size) <= 0:
            raise ValueError("chunk_size must be positive")
        if not math.isfinite(join_timeout_s) or join_timeout_s <= 0:
            raise ValueError("join_timeout_s must be positive and finite")

        if url is None:
            host = resolve_esp32(cfg["esp32_ip"] if ip is None else ip)
            if not path.startswith("/"):
                path = "/" + path
            url = "http://%s:%d%s" % (host, int(port), path)
        self.url = url
        self.reconnect_s = float(reconnect_s)
        self.request_timeout_s = float(request_timeout_s)
        self.chunk_size = int(chunk_size)
        self._join_s = float(join_timeout_s)
        self._urlopen = urlopen
        self._clock = clock

        self._condition = threading.Condition()
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread = None
        self._latest = None          # VideoFrame for single-consumer read()
        self._shared = (None, -1, 0.0)  # (read-only BGR, frame_id, t_decode) for latest()
        self._closed = False
        self._seq = 0

        self.received = 0
        self.frames = 0
        self.invalid = 0
        self.skipped = 0
        self.reconnects = 0
        self.last_error = None

    def start(self):
        if self._closed:
            raise RuntimeError("receiver is closed")
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="sentry-mjpeg", daemon=True)
            self._thread.start()
            if not self._ready.wait(self._join_s):
                self.close()
                raise TimeoutError("mjpeg receiver failed to start")
        return self

    def _store_frame(self, jpeg_bytes, t_rx):
        try:
            frame = decode_jpeg(jpeg_bytes, self._seq, t_rx, clock=self._clock)
        except (ValueError, cv2.error):
            self.invalid += 1
            return
        self._seq += 1
        self.frames += 1
        shared_bgr = frame.frame_bgr.copy()
        shared_bgr.setflags(write=False)
        with self._condition:
            if self._stop.is_set():
                return
            if self._latest is not None:
                self.skipped += 1
            self._latest = frame
            self._shared = (shared_bgr, frame.seq, frame.t_decode)
            self._condition.notify_all()

    def _run(self):
        self._ready.set()
        try:
            while not self._stop.is_set():
                try:
                    req = urllib.request.Request(self.url)
                    with self._urlopen(req, timeout=self.request_timeout_s) as stream:
                        buf = b""
                        while not self._stop.is_set():
                            chunk = stream.read(self.chunk_size)
                            if not chunk:
                                raise EOFError("MJPEG stream ended")
                            jpegs, buf = split_jpegs(buf + chunk)
                            if not jpegs:
                                continue
                            t_rx = self._clock()
                            self.received += len(jpegs)
                            if len(jpegs) > 1:
                                self.skipped += len(jpegs) - 1
                            self._store_frame(jpegs[-1], t_rx)
                except (OSError, urllib.error.URLError, http.client.HTTPException, EOFError, ValueError) as exc:
                    if self._stop.is_set():
                        break
                    self.last_error = exc
                    self.reconnects += 1
                    if self.reconnect_s > 0:
                        self._stop.wait(self.reconnect_s)
        finally:
            self._stop.set()
            self._ready.set()
            with self._condition:
                self._condition.notify_all()

    def read(self, timeout=None):
        """Wait for and consume the latest VideoFrame, or return None on timeout / stop."""
        if self._thread is None:
            raise RuntimeError("start the receiver before reading")
        if timeout is not None and (not np.isfinite(timeout) or timeout < 0):
            raise ValueError("timeout must be nonnegative and finite")
        with self._condition:
            self._condition.wait_for(
                lambda: self._latest is not None or self._stop.is_set(), timeout
            )
            frame, self._latest = self._latest, None
            return frame

    def latest(self):
        """Return (BGR frame, frame_id, age_s) like TileReceiver.latest()."""
        with self._condition:
            bgr, fid, t_decode = self._shared
            if bgr is None:
                return None, -1, float("inf")
            return bgr, fid, max(0.0, self._clock() - t_decode)

    def close(self):
        self._closed = True
        self._stop.set()
        with self._condition:
            self._latest = None
            self._condition.notify_all()
        if self._thread is not None:
            self._thread.join(self._join_s)
            if self._thread.is_alive():
                raise TimeoutError("mjpeg worker did not stop")

    def stop(self):
        """Alias for close() to match TileReceiver.stop()."""
        self.close()

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.close()
