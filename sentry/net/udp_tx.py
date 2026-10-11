"""Non-blocking, rate-limited motor sender; caller owns the control loop.

Call send(v, w) at least at the configured rate (30 Hz). Calls made too soon
return False, so there is no backlog. No background heartbeat repeats stale
commands: if the control loop stops, the Jetson watchdog can stop the robot.
Use as a context manager to send an immediate zero command on exit.
"""
import math
import numbers
import socket
import time

from common.protocol import encode_control
from sentry.config import load
from sentry.net.discover import resolve


_EPS = 1e-6  # rounding overshoot a controller may produce; clamped, not an error


def _command(x):
    """Any real number (numpy float32 included) in [-1, 1] -> float; a value off by rounding is clamped; else ValueError."""
    if isinstance(x, bool) or not isinstance(x, numbers.Real) or not math.isfinite(x) or not -1 - _EPS <= x <= 1 + _EPS:
        raise ValueError("v and w must be finite numbers in [-1, 1], got %r" % (x,))
    return max(-1.0, min(1.0, float(x)))


class UDPSender:
    def __init__(self, ip=None, port=None, rate_hz=None, *, clock=time.perf_counter):
        cfg = load()["net"]
        self.address = (resolve(cfg["jetbot_ip"] if ip is None else ip),
                        cfg["control_port"] if port is None else port)
        rate_hz = cfg["control_rate_hz"] if rate_hz is None else rate_hz
        if not math.isfinite(rate_hz) or rate_hz <= 0:
            raise ValueError("rate_hz must be positive and finite")
        self.period_s = 1 / rate_hz
        self._clock = clock
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setblocking(False)
        self._last_attempt = None
        self._closed = False
        self.seq = 0
        self.sent = 0
        self.dropped = 0

    def _send(self, v, w):
        packet = encode_control(self.seq, v, w)
        self.seq += 1
        try:
            self._socket.sendto(packet, self.address)
        except BlockingIOError:
            self.dropped += 1
            return False
        self.sent += 1
        return True

    def send(self, v, w):
        if self._closed:
            raise RuntimeError("sender is closed")
        v, w = _command(v), _command(w)
        now = self._clock()
        if self._last_attempt is not None and now - self._last_attempt < self.period_s:
            return False
        self._last_attempt = now
        return self._send(v, w)

    def stop(self):
        """Immediate zero command bypasses rate limiting for a prompt stop."""
        if self._closed:
            raise RuntimeError("sender is closed")
        self._last_attempt = self._clock()
        return self._send(0.0, 0.0)

    def close(self, *, stop=True):
        if not self._closed:
            try:
                if stop:
                    self.stop()
            finally:
                self._socket.close()
                self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
