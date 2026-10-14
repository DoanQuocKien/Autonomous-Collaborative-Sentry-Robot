"""One motion-calibration trial driven from here, recorded after the operator reads the tape: same CSV columns as tools/calibrate_motion.py, so `calibrate_motion fit --csv ...` reads them.

  python -m tools.motion_trial trial straight 0.7 0 4          # beeps, --wait s of zeros (hold R1 now), then (v, w) for the seconds; prints the real wheel seconds and the battery
  python -m tools.motion_trial trial turn 0 1.0 0.5
  python -m tools.motion_trial record <csv> <forward_m> <lateral_m> <turn_deg> [notes]       # appends the row of the last trial (lateral: left +, turn: left +)

The operator only holds R1 and reads the tape (straight: forward and sideways distance from the start cross along a string to the far cross; turn: the angle with a protractor against a tape strip
along the robot's centreline). The last trial is kept in data/motion_trial_state.json. A trial whose wheel seconds are near zero (R1 not held in time) is printed as unusable: do not record it.
"""
import argparse
import csv
import json
import os
import time
from pathlib import Path

from sentry.config import load
from sentry.net.udp_tx import UDPSender
from tools import jetbot_ssh
from tools.calibrate_motion import CALIB_ON_ROBOT, COLS, LOG, _sh, moving_seconds
from tools.jetbot_status import ina219_bus_volts
from tools.speed_trial import beep

STATE = Path("data/motion_trial_state.json")
MAX_SPEED = 0.3


def trial(a):
    password = jetbot_ssh.password(a.password)
    c = jetbot_ssh.connect(a.ip, a.user, password)
    try:
        cal = json.loads(_sh(c, "cat %s 2>/dev/null" % CALIB_ON_ROBOT) or "{}")
    except ValueError:
        cal = {}
    before = int(_sh(c, "wc -l < %s" % LOG).strip() or 0)
    sender = UDPSender(a.ip, load()["net"]["control_port"], 30)
    try:
        for _ in range(3):
            beep(1500, 300)
        end = time.perf_counter() + a.wait
        while time.perf_counter() < end:
            sender.send(0.0, 0.0)
            time.sleep(sender.period_s)
        end = time.perf_counter() + a.seconds
        while time.perf_counter() < end:
            sender.send(a.v, a.w)
            time.sleep(sender.period_s)
    finally:
        sender.close()                                           # always sends the stop
    time.sleep(0.6)
    moving = moving_seconds(_sh(c, "tail -n +%d %s" % (before + 1, LOG)).splitlines())
    volts = ina219_bus_volts(jetbot_ssh.sudo(c, "i2cget -y 1 0x41 0x02 w", password))
    state = dict(kind=a.kind, v=a.v, w=a.w, seconds=a.seconds, moving_s=round(moving, 2), battery_v=round(volts, 2),
                 k=cal.get("k", 1.0), min_pwm=cal.get("min_pwm", 0.0), max_speed=MAX_SPEED)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state))
    print("TRIAL %s v=%.2f w=%.2f %.1f s: the wheels turned for %.2f s | battery %.2f V%s" % (
        a.kind, a.v, a.w, a.seconds, moving, volts, "" if moving > 0.3 else "  -> NO USABLE MOTION, repeat (R1 not held in time?)"))
    beep(1000, 300)
    beep(1000, 300)


def record(a):
    s = json.loads(STATE.read_text())
    p = Path(a.csv)
    p.parent.mkdir(parents=True, exist_ok=True)
    new = not p.exists()
    n = 0 if new else sum(1 for _ in p.open(encoding="utf-8")) - 1
    with p.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(COLS)
        w.writerow([n + 1, s["kind"], s["v"], s["w"], s["seconds"], "%.2f" % s["moving_s"], a.forward_m, a.lateral_m, a.turn_deg,
                    "%.2f" % s["battery_v"], s["max_speed"], s["k"], s["min_pwm"], " ".join(a.notes)])
    print("recorded run %d in %s: %s v=%.2f w=%.2f moving %.2f s, forward %.3f lateral %+.3f turn %+.1f" % (
        n + 1, p, s["kind"], s["v"], s["w"], s["moving_s"], a.forward_m, a.lateral_m, a.turn_deg))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("trial")
    t.add_argument("kind", choices=["straight", "turn"])
    t.add_argument("v", type=float)
    t.add_argument("w", type=float)
    t.add_argument("seconds", type=float)
    t.add_argument("--wait", type=float, default=5.0, help="seconds between the beeps and the command: time to hold R1")
    t.add_argument("--ip", default="10.35.172.160")
    t.add_argument("--user", default="jetbot")
    t.add_argument("--password", default=os.environ.get("JETBOT_PASSWORD"))
    r = sub.add_parser("record")
    r.add_argument("csv")
    r.add_argument("forward_m", type=float)
    r.add_argument("lateral_m", type=float)
    r.add_argument("turn_deg", type=float)
    r.add_argument("notes", nargs="*")
    a = ap.parse_args()
    if a.cmd == "trial":
        if not (-1 <= a.v <= 1 and -1 <= a.w <= 1 and 0 < a.seconds <= 8):
            ap.error("v, w in [-1, 1], seconds in (0, 8]")
        if a.kind == "straight" and not (a.v > 0 and a.w == 0):
            ap.error("a straight trial needs v > 0 and w = 0")
        if a.kind == "turn" and not (a.w != 0 and a.v == 0):
            ap.error("a turn trial needs w != 0 and v = 0")
        trial(a)
    else:
        record(a)


if __name__ == "__main__":
    main()
