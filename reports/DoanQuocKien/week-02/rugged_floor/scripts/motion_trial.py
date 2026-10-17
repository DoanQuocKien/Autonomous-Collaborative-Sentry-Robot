"""Run one motion-calibration trial from here and record it, so the operator only holds R1 and reads the tape.

  python motion_trial.py trial  straight 0.7 0 4      # 3 beeps, then 3 s of zeros (time to hold R1), then (v, w) for the seconds; prints moving seconds + battery
  python motion_trial.py record <csv> <forward_m> <lateral_m> <turn_deg> [notes]   # appends the row of the last trial with the measurements
Rows use the columns of tools/calibrate_motion.py (COLS), so `calibrate_motion fit --csv ...` reads them."""
import csv, json, os, sys, time, winsound
from pathlib import Path

from sentry.config import load
from sentry.net.udp_tx import UDPSender
from tools import jetbot_ssh
from tools.calibrate_motion import COLS, LOG, CALIB_ON_ROBOT, _sh, moving_seconds
from tools.jetbot_status import ina219_bus_volts

IP, USER, PW = "10.35.172.160", "jetbot", os.environ.get("JETBOT_PASSWORD", "jetbot")
STATE = Path(__file__).with_name("last_trial.json")
MAX_SPEED = 0.3


def trial(kind, v, w, seconds):
    c = jetbot_ssh.connect(IP, USER, PW)
    try:
        cal = json.loads(_sh(c, "cat %s 2>/dev/null" % CALIB_ON_ROBOT) or "{}")
    except ValueError:
        cal = {}
    before = int(_sh(c, "wc -l < %s" % LOG).strip() or 0)
    sender = UDPSender(IP, load()["net"]["control_port"], 30)
    try:
        for _ in range(3):
            winsound.Beep(1500, 300)
        t_end = time.perf_counter() + 3.0                      # time to hold R1 before the command starts
        while time.perf_counter() < t_end:
            sender.send(0.0, 0.0); time.sleep(sender.period_s)
        t_end = time.perf_counter() + seconds
        while time.perf_counter() < t_end:
            sender.send(v, w); time.sleep(sender.period_s)
    finally:
        sender.close()                                          # always sends the stop
    time.sleep(0.6)
    moving = moving_seconds(_sh(c, "tail -n +%d %s" % (before + 1, LOG)).splitlines())
    volts = ina219_bus_volts(jetbot_ssh.sudo(c, "i2cget -y 1 0x41 0x02 w", PW))
    state = dict(kind=kind, v=v, w=w, seconds=seconds, moving_s=round(moving, 2), battery_v=round(volts, 2), k=cal.get("k", 1.0), min_pwm=cal.get("min_pwm", 0.0), max_speed=MAX_SPEED)
    STATE.write_text(json.dumps(state))
    print("TRIAL %s v=%.2f w=%.2f %.1f s: the wheels turned for %.2f s | battery %.2f V%s" % (kind, v, w, seconds, moving, volts, "" if moving > 0.3 else "  -> NO USABLE MOTION, repeat (R1 not held in time?)"))
    winsound.Beep(1000, 300); winsound.Beep(1000, 300)


def record(path, fwd, lat, turn, notes=""):
    s = json.loads(STATE.read_text())
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    new = not p.exists()
    n = 0 if new else sum(1 for _ in p.open(encoding="utf-8")) - 1
    with p.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(COLS)
        w.writerow([n + 1, s["kind"], s["v"], s["w"], s["seconds"], "%.2f" % s["moving_s"], fwd, lat, turn, "%.2f" % s["battery_v"], s["max_speed"], s["k"], s["min_pwm"], notes])
    print("recorded run %d in %s: %s v=%.2f w=%.2f moving %.2f s, forward %.3f lateral %+.3f turn %+.1f" % (n + 1, p, s["kind"], s["v"], s["w"], s["moving_s"], fwd, lat, turn))


if __name__ == "__main__":
    if sys.argv[1] == "trial":
        trial(sys.argv[2], float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5]))
    else:
        record(sys.argv[2], float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5]), " ".join(sys.argv[6:]))
