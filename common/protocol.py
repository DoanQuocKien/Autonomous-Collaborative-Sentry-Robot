"""Wire formats shared by the laptop and the Jetson.

Python 3.6-compatible and stdlib-only: this file is copied to the Jetson as-is.
Every decoder raises ValueError on bad input, so a malformed or hostile UDP
packet can never reach the motors.
"""
import hashlib
import hmac
import json
import math

PORT_VIDEO = 5555    # ZeroMQ PUB (Jetson) -> SUB (laptop)
PORT_CONTROL = 5556  # UDP laptop -> Jetson
PORT_CLOCK = 5557    # UDP echo, laptop <-> Jetson

def _num(x):
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise ValueError("not a finite number: %r" % (x,))
    try:
        value = float(x)
    except OverflowError:
        raise ValueError("number is outside the finite float range")
    if not math.isfinite(value):
        raise ValueError("not a finite number: %r" % (x,))
    return value


def _int(x):
    if isinstance(x, bool) or not isinstance(x, int):
        raise ValueError("not an int: %r" % (x,))
    return x


def _loads(data):
    msg = json.loads(data.decode("utf-8"))  # UnicodeDecodeError is a ValueError
    if not isinstance(msg, dict):
        raise ValueError("expected a JSON object")
    return msg


# ---- control (UDP, port 5556) ------------------------------------------------

def _mac(key, seq, v, w):
    """HMAC-SHA256 (first 32 hex digits) over the values as sent. key: bytes."""
    return hmac.new(key, json.dumps([seq, v, w]).encode("utf-8"), hashlib.sha256).hexdigest()[:32]


def encode_control(seq, v, w, key=None):
    msg = {"seq": seq, "v": v, "w": w}
    if key is not None:
        msg["mac"] = _mac(key, seq, v, w)
    return json.dumps(msg).encode("utf-8")


def decode_control(data, key=None):
    """-> {"seq", "v", "w"} (v, w clamped to [-1, 1]). With a key, a packet without the right "mac" is refused.
    The MAC stops other hosts on the network from driving the robot; it does not stop a replay of a captured packet
    once the SeqFilter has gone quiet (1 s)."""
    msg = _loads(data)
    seq = _int(msg.get("seq"))
    raw_v, raw_w = msg.get("v"), msg.get("w")
    v = max(-1.0, min(1.0, _num(raw_v)))
    w = max(-1.0, min(1.0, _num(raw_w)))
    if key is not None:
        mac = msg.get("mac")
        if not isinstance(mac, str) or not hmac.compare_digest(mac.encode("utf-8"), _mac(key, seq, raw_v, raw_w).encode("ascii")):
            raise ValueError("missing or wrong mac")
    return {"seq": seq, "v": v, "w": w}


class SeqFilter(object):
    """Drop duplicated or out-of-order UDP packets.

    After `quiet_s` seconds without an accepted packet the sender is assumed to have
    restarted (its seq starts again at 0), so any seq is accepted.
    While the stream is live, a jump of more than `max_jump` ahead is refused too: one stray
    or hostile packet with a huge seq must not lock out the real sender (30 Hz * 100 s = 3000).
    """

    def __init__(self, quiet_s=1.0, max_jump=3000):
        self.quiet_s = quiet_s
        self.max_jump = max_jump
        self.last = None
        self.last_time = None

    def accept(self, seq, now):
        if self.last is None or now - self.last_time > self.quiet_s or self.last < seq <= self.last + self.max_jump:
            self.last, self.last_time = seq, now
            return True
        return False


# ---- video header (first ZeroMQ frame, second frame is the JPEG) ---------------

def encode_video_header(seq, t_cap, w, h):
    """t_cap is the Jetson's time.monotonic() when the frame was read."""
    return json.dumps({"seq": seq, "t_cap": t_cap, "w": w, "h": h}).encode("utf-8")


def decode_video_header(data):
    msg = _loads(data)
    return {"seq": _int(msg.get("seq")), "t_cap": _num(msg.get("t_cap")),
            "w": _int(msg.get("w")), "h": _int(msg.get("h"))}


# ---- clock echo (UDP, port 5557) -----------------------------------------------

def encode_clock_request(t0):
    return json.dumps({"t0": t0}).encode("utf-8")


def decode_clock_request(data):
    return _num(_loads(data).get("t0"))


def encode_clock_reply(t0, t_jetson):
    return json.dumps({"t0": t0, "t_jetson": t_jetson}).encode("utf-8")


def decode_clock_reply(data):
    msg = _loads(data)
    return _num(msg.get("t0")), _num(msg.get("t_jetson"))
