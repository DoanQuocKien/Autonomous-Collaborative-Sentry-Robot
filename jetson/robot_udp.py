#!/usr/bin/env python3
"""Jetson: UDP (v, w) -> motors, plus audio clips and the clock echo.  Python 3.6.

DRAFT: logic is unit-tested on the laptop (tests/test_controller.py); the `jetbot`
motor call and `aplay` are NOT yet tested on the real robot.
Try it without touching hardware:   python3 jetson/robot_udp.py --dry-run
NOT implemented yet: gamepad hardware e-stop (needs the device path from the robot).

Safety: motors stop if no valid command arrives for --watchdog seconds, on exit,
and on any exception. --max-speed caps every wheel value (keep it low for first tests).
"""
import argparse
import json
import os
import select
import socket
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.mixing import deadzone, mix  # noqa: E402
from common.protocol import (PORT_CLOCK, PORT_CONTROL, SeqFilter, decode_clock_request,  # noqa: E402
                             decode_control, encode_clock_reply)


class Controller(object):
    """Pure logic (no sockets, no clock): easy to test."""

    def __init__(self, k=1.0, min_pwm=0.0, max_speed=0.5, watchdog_s=0.3):
        self.k, self.min_pwm, self.max_speed, self.watchdog_s = k, min_pwm, max_speed, watchdog_s
        self.seq = SeqFilter()
        self.last_cmd = None  # time of the last accepted motor command; None = motors already stopped

    def on_packet(self, data, now):
        """-> ("motors", (left, right)) | ("play", clip) | None (ignored packet)."""
        try:
            msg = decode_control(data)
        except ValueError:
            return None
        if not self.seq.accept(msg["seq"], now):
            return None
        if "play" in msg:
            return ("play", msg["play"])
        self.last_cmd = now
        left, right = mix(msg["v"], msg["w"], self.k)
        left, right = left * self.max_speed, right * self.max_speed
        return ("motors", (deadzone(left, self.min_pwm), deadzone(right, self.min_pwm)))

    def on_tick(self, now):
        """Watchdog: returns a stop command once when commands go quiet."""
        if self.last_cmd is not None and now - self.last_cmd > self.watchdog_s:
            self.last_cmd = None
            return ("motors", (0.0, 0.0))
        return None


def _clock_echo(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", port))
    while True:
        data, addr = sock.recvfrom(256)
        try:
            t0 = decode_clock_request(data)
        except ValueError:
            continue
        sock.sendto(encode_clock_reply(t0, time.monotonic()), addr)


def _make_robot():
    from jetbot import Robot  # provided by the JetBot SD image
    return Robot()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=PORT_CONTROL)
    ap.add_argument("--clock-port", type=int, default=PORT_CLOCK)
    ap.add_argument("--allow-ip", help="only accept control packets from this IP (the laptop)")
    ap.add_argument("--max-speed", type=float, default=0.5, help="cap on every wheel value, 0-1")
    ap.add_argument("--watchdog", type=float, default=0.3, help="seconds of silence before stopping")
    ap.add_argument("--calib", default="calib/motion.json", help='JSON {"k": .., "min_pwm": ..}')
    ap.add_argument("--audio-dir", default="assets/audio")
    ap.add_argument("--dry-run", action="store_true", help="print motor values instead of driving")
    args = ap.parse_args()

    calib = {}
    if os.path.exists(args.calib):
        with open(args.calib) as f:
            calib = json.load(f)
    ctl = Controller(calib.get("k", 1.0), calib.get("min_pwm", 0.0), args.max_speed, args.watchdog)
    robot = None if args.dry_run else _make_robot()

    def apply(action):
        kind, val = action
        if kind == "motors":
            if robot:
                robot.set_motors(val[0], val[1])
            else:
                print("motors %+.2f %+.2f" % val, flush=True)
        else:
            path = os.path.join(args.audio_dir, val + ".wav")
            if os.path.exists(path):  # ponytail: no zombie reaping / overlap control; fine for a few clips
                subprocess.Popen(["aplay", "-q", path])

    t = threading.Thread(target=_clock_echo, args=(args.clock_port,))
    t.daemon = True
    t.start()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", args.port))
    try:
        apply(("motors", (0.0, 0.0)))
        while True:
            if select.select([sock], [], [], 0.02)[0]:
                data, addr = sock.recvfrom(512)
                if not args.allow_ip or addr[0] == args.allow_ip:
                    action = ctl.on_packet(data, time.monotonic())
                    if action:
                        apply(action)
            action = ctl.on_tick(time.monotonic())
            if action:
                apply(action)
    finally:
        apply(("motors", (0.0, 0.0)))


if __name__ == "__main__":
    main()
