"""Newest frame of an ESP32-CAM OV2640 HTTP MJPEG stream (http://<ip>:81/stream), Python 3.6, stdlib + cv2/numpy. Same latest() as espcam.TileReceiver."""
import threading
import time
import urllib.request

import cv2
import numpy as np


class MjpegLatest(object):
    def __init__(self, url, reconnect_s=1.0):
        self.url, self.reconnect_s = url, reconnect_s
        self.frames = self.reconnects = 0
        self._frame, self._t, self._lock = None, 0.0, threading.Lock()
        self._stop = threading.Event()
        self._thread = None

    def latest(self):
        """(BGR frame or None, frame count, seconds since decoded)."""
        with self._lock:
            return self._frame, self.frames, time.monotonic() - self._t

    def _run(self):
        while not self._stop.is_set():
            try:
                buf = b""
                with urllib.request.urlopen(self.url, timeout=5) as r:
                    while not self._stop.is_set():
                        chunk = r.read(4096)
                        if not chunk:
                            break
                        buf += chunk
                        a = buf.find(b"\xff\xd8")
                        b = buf.find(b"\xff\xd9", a + 2) if a >= 0 else -1
                        while a >= 0 and b >= 0:
                            img = cv2.imdecode(np.frombuffer(buf[a:b + 2], np.uint8), cv2.IMREAD_COLOR)
                            buf = buf[b + 2:]
                            if img is not None:
                                with self._lock:
                                    self._frame, self._t = img, time.monotonic()
                                    self.frames += 1
                            a = buf.find(b"\xff\xd8")
                            b = buf.find(b"\xff\xd9", a + 2) if a >= 0 else -1
                        if a < 0:
                            buf = buf[-1:]         # keep a possible split SOI marker
            except Exception:
                pass
            self.reconnects += 1
            self._stop.wait(self.reconnect_s)

    def start(self):
        self._thread = threading.Thread(target=self._run)
        self._thread.daemon = True
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
