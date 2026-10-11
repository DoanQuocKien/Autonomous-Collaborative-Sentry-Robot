#!/usr/bin/env python3
"""Jetson: UDP (v, w) -> motors, plus audio clips and the clock echo.  Python 3.6.

Logic is unit-tested on the laptop (tests/test_controller.py); motors and the e-stop interlock were tested on
the robot (docs/JetBot Notes.md). `aplay` is NOT yet tested on the real robot.
Try it without touching hardware:   python3 jetson/robot_udp.py --dry-run

Safety: motors stop if no valid command arrives for --watchdog seconds, on exit, on any exception, and whenever
jetson/estop.py is not running, not armed, or R1 is released. --max-speed caps every wheel value; commands map onto
[min_pwm, max_speed] (dead-zone compensation, common.mixing.to_pwm). Out-of-range settings refuse to start.
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
from common.mixing import DEADBAND, check_drive, mix, to_pwm  # noqa: E402
from common.protocol import (PORT_CLOCK, PORT_CONTROL, SeqFilter, decode_clock_request,  # noqa: E402
                             decode_control, encode_clock_reply)


class Controller(object):
    """Pure logic (no sockets, no clock): easy to test."""

    def __init__(self, k=1.0, min_pwm=0.0, max_speed=0.5, watchdog_s=0.3, deadband=DEADBAND):
        check_drive(max_speed, min_pwm, k)
        if isinstance(watchdog_s, bool) or not isinstance(watchdog_s, (int, float)) or not 0 < watchdog_s <= 1.0:
            raise ValueError("watchdog_s must be in (0, 1] s, got %r" % (watchdog_s,))
        if isinstance(deadband, bool) or not isinstance(deadband, (int, float)) or not 0 <= deadband < 1:
            raise ValueError("deadband must be in [0, 1), got %r" % (deadband,))
        self.k, self.min_pwm, self.max_speed, self.watchdog_s, self.deadband = k, min_pwm, max_speed, watchdog_s, deadband
        self.seq = SeqFilter()
        self.peer = None  # source address of the stream being obeyed; another sender is ignored until it goes quiet
        self.last_cmd = None  # time of the last accepted motor command; None = motors already stopped
        self._estop_sent = None  # time we last sent a stop because the e-stop was engaged
        self.stats = {"received": 0, "malformed": 0, "stale": 0, "foreign": 0, "accepted": 0}  # for packet-loss tests

    def on_packet(self, data, now, estop=False, src=None):
        """-> ("motors", (left, right)) | ("play", clip) | None (ignored packet). While estop is engaged, motor commands are ignored.

        src (the sender's address) locks the controller onto one sender: packets from anyone else are ignored until the
        locked sender has been quiet for the SeqFilter's quiet time (a restarted laptop with a new IP is then obeyed)."""
        self.stats["received"] += 1
        try:
            msg = decode_control(data)
        except ValueError:
            self.stats["malformed"] += 1
            return None
        live = self.seq.last_time is not None and now - self.seq.last_time <= self.seq.quiet_s
        if src is not None and live and self.peer is not None and src != self.peer:
            self.stats["foreign"] += 1
            return None
        if not self.seq.accept(msg["seq"], now):
            self.stats["stale"] += 1
            return None
        self.stats["accepted"] += 1
        if src is not None:
            self.peer = src
        if "play" in msg:
            return ("play", msg["play"])
        if estop:
            return None
        self.last_cmd = now
        left, right = mix(msg["v"], msg["w"], self.k)
        return ("motors", (to_pwm(left, self.max_speed, self.min_pwm, self.deadband),
                           to_pwm(right, self.max_speed, self.min_pwm, self.deadband)))

    def on_tick(self, now, estop=False):
        """While estop is engaged: send a stop right away and repeat it every 0.25 s. Otherwise the watchdog:
        a stop command once when commands go quiet."""
        if estop:
            self.last_cmd = None
            if self._estop_sent is None or now - self._estop_sent >= 0.25:
                self._estop_sent = now
                return ("motors", (0.0, 0.0))
            return None
        self._estop_sent = None
        if self.last_cmd is not None and now - self.last_cmd > self.watchdog_s:
            self.last_cmd = None
            return ("motors", (0.0, 0.0))
        return None


def estop_engaged(latch, heartbeat, now):
    """Fail-safe: engaged if the latch exists, or the heartbeat (time.monotonic() written by jetson/estop.py; the host and
    the container share CLOCK_MONOTONIC) is missing, unreadable, older than 2 s or from the future. A monotonic stamp in the
    file, not the file's mtime: the Jetson has no RTC, and a wall-clock step back made a dead e-stop look alive."""
    if os.path.exists(latch):
        return True
    try:
        with open(heartbeat) as f:
            age = now - float(f.read())
    except (OSError, ValueError):
        return True
    return not -0.5 <= age <= 2.0


def _clock_echo(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", port))
    while True:
        try:
            data, addr = sock.recvfrom(256)
            t0 = decode_clock_request(data)
            sock.sendto(encode_clock_reply(t0, time.monotonic()), addr)
        except ValueError:
            continue
        except OSError as e:  # one unreachable sender must not end the echo for good
            print("clock echo: %s" % e, flush=True)
            time.sleep(0.1)


def play_clip(audio_dir, clip, players, popen=subprocess.Popen, max_players=2):
    """Start `aplay` for <audio_dir>/<clip>.wav; reap finished players. Never raises: a missing WAV or a missing or
    broken `aplay` is logged and ignored, so an audio packet can never take down the motor loop. At most max_players
    clips play at once, so a flood of play packets cannot fork without limit."""
    players[:] = [p for p in players if p.poll() is None]
    if len(players) >= max_players:
        return "busy (%d clips playing)" % len(players)
    path = os.path.join(audio_dir, clip + ".wav")
    if not os.path.exists(path):
        return "missing clip %s" % path
    try:
        players.append(popen(["aplay", "-q", path]))
    except OSError as e:
        return "aplay failed: %s" % e
    return None


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
    ap.add_argument("--estop-dir", default=".", help="folder with ESTOP and ESTOP_ALIVE written by jetson/estop.py")
    ap.add_argument("--no-estop", action="store_true", help="DANGEROUS: ignore the gamepad e-stop (only for dry-run development)")
    args = ap.parse_args()

    calib = {}
    if os.path.exists(args.calib):
        with open(args.calib) as f:
            calib = json.load(f)
    try:
        ctl = Controller(calib.get("k", 1.0), calib.get("min_pwm", 0.0), args.max_speed, args.watchdog,
                         calib.get("deadband", DEADBAND))
    except ValueError as e:
        raise SystemExit("refusing to start: %s (check --max-speed, --watchdog and %s)" % (e, args.calib))
    robot = None if args.dry_run else _make_robot()

    printed = [None]
    players = []
    latch = os.path.join(args.estop_dir, "ESTOP")
    heartbeat = os.path.join(args.estop_dir, "ESTOP_ALIVE")


    def stamp():
        t = time.time()
        return "%s.%03d" % (time.strftime("%H:%M:%S", time.localtime(t)), int(t * 1000) % 1000)

    def apply(action):
        kind, val = action
        if kind == "motors":
            if robot:
                robot.set_motors(val[0], val[1])
            if val != printed[0]:  # print changes only
                printed[0] = val
                print("%s motors %+.2f %+.2f%s" % (stamp(), val[0], val[1], "" if robot else " (dry-run)"), flush=True)
        else:
            problem = play_clip(args.audio_dir, val, players)
            if problem:
                print("%s play %s: %s" % (stamp(), val, problem), flush=True)

    t = threading.Thread(target=_clock_echo, args=(args.clock_port,))
    t.daemon = True
    t.start()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", args.port))
    try:
        apply(("motors", (0.0, 0.0)))
        was = None
        last_stats, stats_seen = time.monotonic(), 0
        while True:
            estop = False if args.no_estop else estop_engaged(latch, heartbeat, time.monotonic())
            if estop != was:
                was = estop
                print("%s e-stop %s" % (stamp(), "ENGAGED: refusing motor commands" if estop else "released: motor commands accepted"), flush=True)
            if select.select([sock], [], [], 0.02)[0]:
                data, addr = sock.recvfrom(512)
                if not args.allow_ip or addr[0] == args.allow_ip:
                    action = ctl.on_packet(data, time.monotonic(), estop, addr)
                    if action:
                        apply(action)
            if time.monotonic() - last_stats >= 10.0:  # control-link counters for the packet-loss test; only while packets arrive
                last_stats = time.monotonic()
                if ctl.stats["received"] != stats_seen:
                    stats_seen = ctl.stats["received"]
                    print("%s packets %s" % (stamp(), " ".join("%s=%d" % kv for kv in sorted(ctl.stats.items()))), flush=True)
            action = ctl.on_tick(time.monotonic(), estop)
            if action:
                apply(action)
    finally:
        apply(("motors", (0.0, 0.0)))


if __name__ == "__main__":
    main()
