"""Wire formats shared by the laptop and the Jetson.

Python 3.6-compatible and stdlib-only: this file is copied to the Jetson as-is.
Every decoder raises ValueError on bad input, so a malformed or hostile UDP
packet can never reach the motors.
"""
import json
import math
import re

PORT_VIDEO = 5555    # ZeroMQ PUB (Jetson) -> SUB (laptop)
PORT_CONTROL = 5556  # UDP laptop -> Jetson
PORT_CLOCK = 5557    # UDP echo, laptop <-> Jetson

_CLIP = re.compile(r"^[a-z0-9_]{1,32}$")  # audio clip names; never reaches a shell


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

def encode_control(seq, v, w):
    return json.dumps({"seq": seq, "v": v, "w": w}).encode("utf-8")


def encode_play(seq, clip):
    return json.dumps({"seq": seq, "play": clip}).encode("utf-8")


def decode_control(data):
    """-> {"seq", "v", "w"} (v, w clamped to [-1, 1]) or {"seq", "play"}."""
    msg = _loads(data)
    seq = _int(msg.get("seq"))
    if "play" in msg:
        clip = msg["play"]
        if not isinstance(clip, str) or not _CLIP.match(clip):
            raise ValueError("bad clip name")
        return {"seq": seq, "play": clip}
    v = max(-1.0, min(1.0, _num(msg.get("v"))))
    w = max(-1.0, min(1.0, _num(msg.get("w"))))
    return {"seq": seq, "v": v, "w": w}


class SeqFilter(object):
    """Drop duplicated or out-of-order UDP packets.

    After `quiet_s` seconds without an accepted packet the sender is assumed to have
    restarted (its seq starts again at 0), so any seq is accepted.
    """

    def __init__(self, quiet_s=1.0):
        self.quiet_s = quiet_s
        self.last = None
        self.last_time = None

    def accept(self, seq, now):
        if self.last is None or now - self.last_time > self.quiet_s or seq > self.last:
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
