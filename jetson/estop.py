#!/usr/bin/env python3
"""Gamepad dead-man switch + emergency stop for the JetBot.  Python 3.6, stdlib only.

Runs on the Jetson HOST (not in the jetbot container) so it keeps working if jetson/robot_udp.py hangs or crashes.
Needs root for the I2C motor cut:  sudo python3 jetson/estop.py

The robot may move ONLY while the operator holds R1 (the dead-man button) AND the e-stop is armed:
  * Starts HARD-STOPPED. ARM by holding the arm buttons (default: Start alone, see --arm-buttons) for 1.5 s (proves the pad is awake). R1 must then be held to move.
  * Releasing R1 stops the robot (soft stop); holding R1 again resumes. A pad that dies while R1 is held makes the receiver
    report a release (measured 2026-10-06 for a power-off), so a dying pad stops the robot instead of silently disabling the e-stop.
  * ANY other button press, losing the gamepad, or starting up is a HARD stop that needs the arm buttons again.
  * Every stop also cuts the motor driver directly over I2C (about 10-15 ms).
Files in --dir, read by jetson/robot_udp.py:  ESTOP = latch (exists whenever motion is NOT allowed),  ESTOP_ALIVE = heartbeat
(time.monotonic(), written atomically; the robot has no RTC, so wall-clock times can jump). Deploy estop.py and robot_udp.py together.
robot_udp.py treats a missing or stale heartbeat as stopped, so it never drives without this program running.

Pad: "TGZ Controller" (DragonRise), /dev/input/js0. Buttons inferred from a recording on 2026-10-06: Select = 10, Start = 11
(the chord needs BOTH, so their order does not matter), R1 = 7. D-pad and sticks are axes and are ignored.
Unmeasured: a pad that dies some other way (flat batteries, out of range) may freeze the receiver's last state instead.
The motor cut uses the PCA9685 at I2C 0x60: ALL_LED_OFF_H (0xFD) bit 4 = every output full OFF. Resuming first zeroes all
outputs (ALL_LED registers 0xFA-0xFD = 0), so nothing can restart at an old speed.
"""
import argparse
import errno
import glob
import os
import select
import struct
import subprocess
import sys
import time

ARM_BUTTONS = (11,)  # Start alone (Select = 10, Start = 11); --arm-buttons 10 11 asks for both
ARM_HOLD_S = 1.5
DEADMAN_BUTTON = 7
JS_EVENT = struct.Struct("<IhBB")  # time ms, value, type, number
JS_BUTTON, JS_INIT = 0x01, 0x80


class EstopLogic(object):
    """Pure state machine (no files, no clock of its own): easy to test.

    Methods return a list of events: "STOP" (motion no longer allowed), "ARM" (hard stop cleared), "GO" (motion allowed).
    """

    def __init__(self, arm_buttons=ARM_BUTTONS, arm_hold_s=ARM_HOLD_S, deadman=DEADMAN_BUTTON):
        self.arm_buttons = tuple(arm_buttons)
        self.arm_hold_s = arm_hold_s
        self.deadman = deadman
        self.hard = True          # hard stop: startup, any other button, pad lost. Cleared by the arm chord
        self.dead_held = False    # is R1 held right now?
        self.held = set()
        self.chord_since = None
        self.reason = "startup"

    @property
    def motion_allowed(self):
        return (not self.hard) and self.dead_held

    def _events(self, before, armed_now=False):
        out = []
        if armed_now:
            out.append("ARM")
        after = self.motion_allowed
        if before and not after:
            out.append("STOP")
        elif after and not before:
            out.append("GO")
        return out

    def button(self, number, pressed, now):
        before = self.motion_allowed
        if pressed:
            self.held.add(number)
        else:
            self.held.discard(number)
        if number == self.deadman:
            self.dead_held = pressed
            if not pressed:
                self.reason = "R1 released"
        elif pressed and not self.hard:
            self.hard = True
            self.reason = "button %d pressed" % number
        self._update_chord(now)
        return self._events(before)

    def _update_chord(self, now):
        if self.hard and all(b in self.held for b in self.arm_buttons):
            if self.chord_since is None:
                self.chord_since = now
        else:
            self.chord_since = None

    def tick(self, now):
        """Call often, also when no events arrive. The arm chord completes here."""
        if self.hard and self.chord_since is not None and now - self.chord_since >= self.arm_hold_s:
            before = self.motion_allowed
            self.hard = False
            self.chord_since = None
            return self._events(before, armed_now=True)
        return []

    def device_lost(self):
        """The gamepad vanished: hard stop and forget every held button."""
        before = self.motion_allowed
        self.held.clear()
        self.chord_since = None
        self.dead_held = False
        self.hard = True
        self.reason = "gamepad lost"
        return self._events(before)


def i2c_write(bus, addr, reg, value, call=subprocess.call, timeout=1.0):
    """False on any failure, including a hung bus (timeout): the caller logs it and stays stopped."""
    try:
        return call(["i2cset", "-y", str(bus), hex(addr), hex(reg), hex(value)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout) == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def write_heartbeat(path, now):
    """time.monotonic() into ESTOP_ALIVE, atomically (write + replace): jetson/robot_udp.py must never read a half-written file."""
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write("%.3f\n" % now)
    os.replace(tmp, path)  # os.rename fails on Windows when the target exists; replace is atomic on both


def motor_cut(bus, addr, call=subprocess.call):
    """PCA9685 ALL_LED_OFF_H bit 4: every output full OFF."""
    return i2c_write(bus, addr, 0xFD, 0x10, call)


def motor_rearm(bus, addr, call=subprocess.call):
    """Zero every channel (ALL_LED_ON_L/H, ALL_LED_OFF_L/H = 0); writing OFF_H = 0 also clears the full-OFF bit."""
    return all([i2c_write(bus, addr, reg, 0x00, call) for reg in (0xFA, 0xFB, 0xFC, 0xFD)])


def stamp():
    t = time.time()
    return "%s.%03d" % (time.strftime("%H:%M:%S", time.localtime(t)), int(t * 1000) % 1000)


def log(msg):
    print("%s %s" % (stamp(), msg))
    sys.stdout.flush()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="/home/jetbot/sentry", help="where ESTOP and ESTOP_ALIVE live (the container sees it as /workspace/sentry)")
    ap.add_argument("--bus", type=int, default=1)
    ap.add_argument("--addr", type=lambda s: int(s, 0), default=0x60)
    ap.add_argument("--arm-hold", type=float, default=ARM_HOLD_S)
    ap.add_argument("--arm-buttons", type=int, nargs="+", default=list(ARM_BUTTONS), help="button numbers held together to arm (Select = 10, Start = 11; the default is Start alone)")
    ap.add_argument("--deadman", type=int, default=DEADMAN_BUTTON, help="dead-man button number (R1 = 7)")
    ap.add_argument("--no-motor-cut", action="store_true", help="logic and files only; never touch the motor driver (for first tests)")
    args = ap.parse_args()

    latch, alive = os.path.join(args.dir, "ESTOP"), os.path.join(args.dir, "ESTOP_ALIVE")
    logic = EstopLogic(arm_buttons=args.arm_buttons, arm_hold_s=args.arm_hold, deadman=args.deadman)
    arm_name = "+".join({10: "Select", 11: "Start"}.get(b, "button %d" % b) for b in args.arm_buttons)

    def stop(why):
        """Cut the motors FIRST (it does not depend on the file system), then write the latch for robot_udp.py."""
        if args.no_motor_cut:
            cut = "motor cut skipped (--no-motor-cut)"
        else:
            t0 = time.time()
            ok = motor_cut(args.bus, args.addr)
            cut = ("motors CUT in %.0f ms" % ((time.time() - t0) * 1000)) if ok else "MOTOR CUT FAILED (i2cset)"
        try:
            with open(latch, "w") as f:
                f.write(why + "\n")
        except OSError as e:  # robot_udp.py still stops: the heartbeat goes stale when this program exits
            log("STOPPED (%s); %s; LATCH WRITE FAILED: %s, exiting" % (why, cut, e))
            raise
        log("STOPPED (%s); %s" % (why, cut))

    def go():
        """Allowed to move: zero all outputs, then remove the latch so robot_udp.py may drive."""
        ok = True if args.no_motor_cut else motor_rearm(args.bus, args.addr)
        if not ok:
            log("resume FAILED to reset the motor driver; staying stopped")
            logic.hard = True
            logic.reason = "motor driver reset failed"
            return
        if os.path.exists(latch):
            os.remove(latch)
        log("GO (R1 held and armed); robot may move")

    def handle(events):
        for ev in events:
            if ev == "STOP":
                stop(logic.reason)
            elif ev == "ARM":
                log("ARMED (%s held %.1f s); now hold R1 to move" % (arm_name, args.arm_hold))
            elif ev == "GO":
                go()

    stop("startup")
    devs = {}  # fd -> path
    had_pad, last_scan, last_alive = False, 0.0, 0.0
    log("watching the gamepad; hold %s %.1f s to arm, then hold R1 (button %d) to move; any other button = hard stop" % (arm_name, args.arm_hold, args.deadman))
    while True:
        now = time.monotonic()
        if now - last_scan > 1.0:
            last_scan = now
            for path in sorted(glob.glob("/dev/input/js*")):
                if path not in devs.values():
                    try:
                        devs[os.open(path, os.O_RDONLY | os.O_NONBLOCK)] = path
                        log("gamepad found: " + path)
                    except OSError as e:
                        log("cannot open %s: %s" % (path, e))
        if devs:
            had_pad = True
        elif had_pad:
            had_pad = False
            ev = logic.device_lost()
            handle(ev)
            if not ev:
                log("gamepad lost (already stopped)")
        if now - last_alive > 0.5:
            last_alive = now
            write_heartbeat(alive, now)
        r = select.select(list(devs), [], [], 0.05)[0] if devs else []
        if not devs:
            time.sleep(0.05)
        for fd in r:
            while True:
                try:
                    data = os.read(fd, JS_EVENT.size)
                except BlockingIOError:
                    break
                except OSError as e:
                    if e.errno in (errno.ENODEV, errno.EIO):
                        log("gamepad gone: " + devs.pop(fd))
                        os.close(fd)
                        break
                    raise
                if len(data) < JS_EVENT.size:
                    break
                _, value, typ, number = JS_EVENT.unpack(data)
                if typ & JS_INIT or (typ & 0x7F) != JS_BUTTON:
                    continue  # skip the initial-state dump and every axis (D-pad, sticks)
                handle(logic.button(number, bool(value), time.monotonic()))
        handle(logic.tick(time.monotonic()))


if __name__ == "__main__":
    main()
