#!/usr/bin/env python3
"""Gamepad emergency stop for the JetBot.  Python 3.6, stdlib only.

Runs on the Jetson HOST (not in the jetbot container) so it keeps working if jetson/robot_udp.py hangs or crashes.
Needs root for the I2C motor cut:  sudo python3 jetson/estop.py

Fail-safe design:
  * Starts ENGAGED (motors must not move). The operator ARMS it by holding Select+Start for 2 s, which also proves the pad works.
  * ANY gamepad button press engages it again and cuts the motor driver directly over I2C.
  * Losing the gamepad (unplugged, re-pairing, receiver reset) engages it.
  * Files in --dir, read by jetson/robot_udp.py:  ESTOP = latch (exists while engaged),  ESTOP_ALIVE = heartbeat.
    robot_udp.py treats a missing or stale heartbeat as ENGAGED, so it never drives without this program running.

Pad: "TGZ Controller" (DragonRise), /dev/input/js0. Select = button 10 and Start = button 11 were inferred from a recording on
2026-10-06; the chord needs BOTH, so their order does not matter. D-pad and sticks are axes and are ignored.
The motor cut uses the PCA9685 at I2C 0x60: ALL_LED_OFF_H (0xFD) bit 4 = every output full OFF. Re-arming first zeroes all
outputs (ALL_LED registers 0xFA-0xFD = 0), so nothing can resume at an old speed.
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

ARM_BUTTONS = (10, 11)
ARM_HOLD_S = 2.0
JS_EVENT = struct.Struct("<IhBB")  # time ms, value, type, number
JS_BUTTON, JS_INIT = 0x01, 0x80


class EstopLogic(object):
    """Pure state machine (no files, no clock of its own): easy to test."""

    def __init__(self, arm_buttons=ARM_BUTTONS, arm_hold_s=ARM_HOLD_S):
        self.arm_buttons = tuple(arm_buttons)
        self.arm_hold_s = arm_hold_s
        self.engaged = True  # engaged at start: the operator must arm with the pad
        self.held = set()
        self.chord_since = None

    def button(self, number, pressed, now):
        """Feed one button event. Returns "STOP" when a press engages the e-stop, else None."""
        if pressed:
            self.held.add(number)
        else:
            self.held.discard(number)
        self._update_chord(now)
        if pressed and not self.engaged:
            self.engaged = True
            self.chord_since = None
            return "STOP"
        return None

    def _update_chord(self, now):
        if self.engaged and all(b in self.held for b in self.arm_buttons):
            if self.chord_since is None:
                self.chord_since = now
        else:
            self.chord_since = None

    def tick(self, now):
        """Call often, also when no events arrive. Returns "ARM" once the chord has been held long enough."""
        if self.engaged and self.chord_since is not None and now - self.chord_since >= self.arm_hold_s:
            self.engaged = False
            self.chord_since = None
            return "ARM"
        return None

    def device_lost(self):
        """The gamepad vanished: engage. Returns "STOP" if that changed anything."""
        self.held.clear()
        self.chord_since = None
        if not self.engaged:
            self.engaged = True
            return "STOP"
        return None


def i2c_write(bus, addr, reg, value, call=subprocess.call):
    return call(["i2cset", "-y", str(bus), hex(addr), hex(reg), hex(value)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0


def motor_cut(bus, addr, call=subprocess.call):
    """PCA9685 ALL_LED_OFF_H bit 4: every output full OFF."""
    return i2c_write(bus, addr, 0xFD, 0x10, call)


def motor_rearm(bus, addr, call=subprocess.call):
    """Zero every channel (ALL_LED_ON_L/H, ALL_LED_OFF_L/H = 0); writing OFF_H = 0 also clears the full-OFF bit."""
    return all([i2c_write(bus, addr, reg, 0x00, call) for reg in (0xFA, 0xFB, 0xFC, 0xFD)])


def log(msg):
    print("%s %s" % (time.strftime("%H:%M:%S"), msg))
    sys.stdout.flush()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="/home/jetbot/sentry", help="where ESTOP and ESTOP_ALIVE live (the container sees it as /workspace/sentry)")
    ap.add_argument("--bus", type=int, default=1)
    ap.add_argument("--addr", type=lambda s: int(s, 0), default=0x60)
    ap.add_argument("--arm-hold", type=float, default=ARM_HOLD_S)
    ap.add_argument("--no-motor-cut", action="store_true", help="logic and files only; never touch the motor driver (for first tests)")
    args = ap.parse_args()

    latch, alive = os.path.join(args.dir, "ESTOP"), os.path.join(args.dir, "ESTOP_ALIVE")
    logic = EstopLogic(arm_hold_s=args.arm_hold)

    def stop(why):
        with open(latch, "w") as f:
            f.write(why + "\n")
        cut = "motor cut skipped (--no-motor-cut)" if args.no_motor_cut else ("motors CUT" if motor_cut(args.bus, args.addr) else "MOTOR CUT FAILED (i2cset)")
        log("ENGAGED (%s); %s" % (why, cut))

    def arm():
        ok = True if args.no_motor_cut else motor_rearm(args.bus, args.addr)
        if not ok:
            log("re-arm FAILED to reset the motor driver; staying engaged")
            logic.engaged = True
            return
        if os.path.exists(latch):
            os.remove(latch)
        log("ARMED (Select+Start held %.1f s); robot may move" % args.arm_hold)

    stop("startup")
    devs = {}  # fd -> path
    had_pad, last_scan, last_alive = False, 0.0, 0.0
    log("watching the gamepad; hold Select+Start for %.1f s to arm, any button to stop" % args.arm_hold)
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
            if logic.device_lost() == "STOP":
                stop("gamepad lost")
        if now - last_alive > 0.5:
            last_alive = now
            with open(alive, "w") as f:
                f.write("%.3f\n" % time.time())
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
                if logic.button(number, bool(value), time.monotonic()) == "STOP":
                    stop("button %d pressed" % number)
        if logic.tick(time.monotonic()) == "ARM":
            arm()


if __name__ == "__main__":
    main()
