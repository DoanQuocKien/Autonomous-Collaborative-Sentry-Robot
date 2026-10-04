"""Cristian clock sync. Offset is Jetson minus laptop, in monotonic seconds."""
from dataclasses import dataclass
import math
import socket
import time

from common.protocol import decode_clock_reply, encode_clock_request
from sentry.config import load


@dataclass(frozen=True)
class ClockSample:
    t0: float
    t_jetson: float
    t1: float

    def __post_init__(self):
        if not all(math.isfinite(t) for t in (self.t0, self.t_jetson, self.t1)):
            raise ValueError("clock timestamps must be finite")
        if self.t1 < self.t0:
            raise ValueError("receive time precedes send time")

    @property
    def rtt_s(self):
        return self.t1 - self.t0

    @property
    def offset_s(self):
        return self.t_jetson - (self.t0 + self.t1) / 2


@dataclass(frozen=True)
class ClockEstimate:
    offset_s: float
    rtt_s: float
    samples: int
    t_sync: float  # laptop monotonic time; resync after a Jetson restart

    def to_local(self, t_jetson):
        return t_jetson - self.offset_s


def estimate_clock(samples):
    """Choose the minimum RTT exchange, minimizing queueing bias.

    Path asymmetry remains unknown; RTT / 2 is the timing uncertainty bound,
    assuming the Jetson timestamp lies between the send and receive instants.
    """
    samples = list(samples)
    if not samples:
        raise ValueError("need at least one clock sample")
    best = min(samples, key=lambda s: s.rtt_s)
    return ClockEstimate(best.offset_s, best.rtt_s, len(samples), max(s.t1 for s in samples))


def synchronize(ip=None, port=None, samples=None, timeout_s=None):
    """Collect the configured number of valid echoes (20 by default).

    Each exchange has a deadline. Late echoes, malformed replies and wrong t0
    values are ignored. A failed exchange raises TimeoutError: no fake offset.
    The connected UDP socket only accepts replies from the selected peer.
    """
    cfg = load()["net"]
    ip = cfg["jetbot_ip"] if ip is None else ip
    port = cfg["clock_port"] if port is None else port
    samples = cfg["clock_samples"] if samples is None else samples
    timeout_s = cfg["clock_timeout_s"] if timeout_s is None else timeout_s
    if isinstance(samples, bool) or not isinstance(samples, int) or samples < 1:
        raise ValueError("samples must be a positive integer")
    if not math.isfinite(timeout_s) or timeout_s <= 0:
        raise ValueError("timeout_s must be positive and finite")
    collected = []
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.connect((ip, port))
        for _ in range(samples):
            t0 = time.perf_counter()
            sock.send(encode_clock_request(t0))
            deadline = t0 + timeout_s
            while True:
                remaining = deadline - time.perf_counter()
                if remaining <= 0:
                    raise TimeoutError("clock echo timed out; check Jetson clock port")
                sock.settimeout(remaining)
                try:
                    data = sock.recv(512)
                except socket.timeout as exc:
                    raise TimeoutError("clock echo timed out; check Jetson clock port") from exc
                t1 = time.perf_counter()
                try:
                    echoed_t0, remote = decode_clock_reply(data)
                except ValueError:
                    continue
                if echoed_t0 == t0:
                    collected.append(ClockSample(t0, remote, t1))
                    break
    return estimate_clock(collected)
