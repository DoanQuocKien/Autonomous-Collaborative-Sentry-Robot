"""Newest frame of an ESP32-CAM OV2640 HTTP MJPEG stream (http://<ip>:81/stream), Python 3.6, stdlib + cv2/numpy. Same latest() as espcam.TileReceiver."""
import threading
import time
import math
import http.client
import urllib.request
from urllib.parse import urlsplit

import cv2
import numpy as np


class MjpegLatest(object):
    MAX_BUFFER_BYTES = 2 * 1024 * 1024

    def __init__(self, url, reconnect_s=1.0, max_age_s=2.0):
        if urlsplit(url).scheme not in ("http", "https"):
            raise ValueError("HTTP(S) MJPEG URL required")
        if not all(math.isfinite(v) and v > 0 for v in (reconnect_s, max_age_s)):
            raise ValueError("positive finite reconnect and freshness limits required")
        self.url, self.reconnect_s = url, reconnect_s
        self.max_age_s = max_age_s
        self.frames = self.reconnects = 0
        self._frame, self._t, self._lock = None, 0.0, threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._buffer = b""

    def latest(self):
        """(BGR frame or None, frame count, seconds since decoded)."""
        with self._lock:
            age = time.monotonic() - self._t
            return (self._frame if age <= self.max_age_s else None), self.frames, age

    def _consume(self, chunk):
        self._buffer += chunk
        if len(self._buffer) > self.MAX_BUFFER_BYTES:
            self._buffer = b""
            raise ValueError("MJPEG frame exceeds bounded receive buffer")
        while True:
            a = self._buffer.find(b"\xff\xd8")
            if a < 0:
                self._buffer = self._buffer[-1:]
                return
            b = self._buffer.find(b"\xff\xd9", a + 2)
            if b < 0:
                self._buffer = self._buffer[a:]
                return
            img = cv2.imdecode(np.frombuffer(self._buffer[a:b + 2], np.uint8), cv2.IMREAD_COLOR)
            self._buffer = self._buffer[b + 2:]
            if img is not None:
                with self._lock:
                    self._frame, self._t = img, time.monotonic()
                    self.frames += 1

    def _run(self):
        while not self._stop.is_set():
            try:
                self._buffer = b""
                with urllib.request.urlopen(self.url, timeout=5) as r:
                    while not self._stop.is_set():
                        # read() can wait for 4096 bytes, delaying a small JPEG
                        # until the next frame. read1() returns available data.
                        chunk = r.read1(4096)
                        if not chunk:
                            break
                        self._consume(chunk)
            except (OSError, ValueError, http.client.HTTPException, cv2.error):
                pass
            self.reconnects += 1
            self._stop.wait(self.reconnect_s)

    def start(self):
        if self._thread is not None or self._stop.is_set():
            raise RuntimeError("MJPEG receiver can only be started once")
        self._thread = threading.Thread(target=self._run)
        self._thread.daemon = True
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=6)  # socket read timeout is at most 5 s
