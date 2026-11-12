"""R1-release stop-time trials (wheels OFF THE GROUND, robot stationary): software path from the gamepad event to the motor cut, from the Jetson's own logs.
For each trial the laptop streams a steady command (v = 0.6, legal: 0.6 x 0.3 = 0.18 >= min_pwm 0.12) while R1 is held, you release R1 at the beep, the stream continues for 4 s after the beep (the robot must ignore it) and
then stops (the stream runs 4 s after the beep). Afterwards the new lines of /home/jetbot/sentry/estop.log (host clock, local time) and robot_udp.log (container clock, UTC) are fetched: the e-stop logs 'STOPPED (...); motors CUT in N ms' and robot_udp logs the first
e-stop refusal. NOT measured: the gamepad's own radio/USB latency and the wheels' mechanical stop (no encoders, no scope). Needs the e-stop armed (hold Start 1.5 s) before the first trial.
  PYTHONPATH=. JETBOT_PASSWORD=... python reports/DoanQuocKien/week-06/latency_1111/stop_time_trials.py --ip 10.169.60.160 --trials 5"""
import argparse
import json
import re
import sys
import time

import paramiko

from sentry.config import load
from sentry.net.udp_tx import UDPSender

ap = argparse.ArgumentParser()
ap.add_argument("--ip", required=True)
ap.add_argument("--trials", type=int, default=5)
ap.add_argument("--v", type=float, default=0.6)
ap.add_argument("--release-after", type=float, default=4.0, help="beep (release R1) this many seconds after the stream starts")
ap.add_argument("--press-other", action="store_true", help="hard-stop test: keep R1 held and press ANY OTHER gamepad button at the beep (the e-stop must stop and disarm) instead of releasing R1")
ap.add_argument("--out", required=True)
a = ap.parse_args()
if not 0.4 <= a.v <= 0.8 or not 1 <= a.trials <= 10:
    sys.exit("ABORT: v must be 0.4-0.8 and trials 1-10")
import os
import winsound

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(a.ip, username="jetbot", password=os.environ["JETBOT_PASSWORD"], timeout=10)


def sh(cmd):
    _, o, e = ssh.exec_command(cmd)
    return o.read().decode(errors="replace")


def latch_present():
    return sh("test -e /home/jetbot/sentry/ESTOP && echo y || echo n").strip() == "y"


def size(path):
    return int(sh("stat -c %%s %s" % path).strip() or 0)


def new_lines(path, offset):
    return sh("tail -c +%d %s" % (offset + 1, path)).splitlines()


def tod(line):
    m = re.match(r"(\d\d):(\d\d):(\d\d)\.(\d\d\d)", line)
    return (int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3]) + int(m[4]) / 1000.0) if m else None


results = []
sender = UDPSender(a.ip, load()["net"]["control_port"], 30)
try:
    for k in range(1, a.trials + 1):
        print("trial %d: ARM if needed (hold Start 1.5 s), then HOLD R1; %s at the beep" % (k, "keep R1 held and press ANY OTHER button (a different one each trial)" if a.press_other else "release R1"), flush=True)
        winsound.Beep(1000, 300)
        t_end = time.time() + 90
        since = None
        while True:
            held = not latch_present()
            now = time.time()
            since = (since or now) if held else None
            if since and now - since >= 0.5:
                break
            if now > t_end:
                print("ABORT: R1 not held in time")
                raise SystemExit(1)
            time.sleep(0.15)
        o_e, o_r = size("/home/jetbot/sentry/estop.log"), size("/home/jetbot/sentry/robot_udp.log")
        t0 = time.time()
        beeped = False
        while time.time() - t0 < a.release_after + 4.0:                 # stream steadily (no SSH calls inside: a gap over 300 ms would trigger the watchdog and confound the trial)
            sender.send(a.v, 0.0)
            time.sleep(1 / 30.0)
            if not beeped and time.time() - t0 >= a.release_after:
                beeped = True
                winsound.Beep(1600, 300)                                # release R1 (or press another button) now; the stream goes on for 4 more seconds (commands must be ignored)
        sender.send(0.0, 0.0)
        time.sleep(1.0)
        e_lines, r_lines = new_lines("/home/jetbot/sentry/estop.log", o_e), new_lines("/home/jetbot/sentry/robot_udp.log", o_r)
        results.append(dict(trial=k, estop=e_lines, robot_udp=r_lines))
        print("  estop.log:", [l for l in e_lines if "STOPPED" in l or "GO" in l], flush=True)
        print("  robot_udp.log (non-stat):", [l for l in r_lines if "packets" not in l][:6], flush=True)
finally:
    try:
        sender.send(0.0, 0.0)
        sender.close(stop=True)
    except Exception:
        pass
    json.dump(results, open(a.out, "w"), indent=1)
print("saved", a.out)
