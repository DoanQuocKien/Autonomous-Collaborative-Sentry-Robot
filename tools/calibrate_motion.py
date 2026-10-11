"""Motion calibration: command fixed (v, w), tape-measure what the robot did, fit the dead-reckoning gains -> calib/motion.json.

Two steps (T2, wheels on the floor, e-stop armed, you hold R1 for the whole run):

  1. collect (robot, tape measure, ~20 min). One trial = place the robot at a start mark, the tool streams (v, w) for --seconds, you hold R1, then you type what you measured:
       python -m tools.calibrate_motion run --kind straight --v 1.0 --seconds 4 --runs 5     # forward_m (start mark -> robot centre), lateral_m (left +)
       python -m tools.calibrate_motion run --kind turn --w 1.0 --seconds 2 --runs 5         # turn_deg (left +; stick a tape strip along the robot's centreline before and after, read the angle with a protractor)
     The time the wheels really turned ("moving_s") is read from the robot's robot_udp.log (R1 releases and the watchdog cut runs short), so the gains do not depend on how long you held R1.
  2. fit:
       python -m tools.calibrate_motion fit --push        # data -> calib/motion.json (and onto the robot)

Model used by nav/localization.py (per unit of the normalised command, at the --max-speed that robot_udp.py ran with):
    forward speed [m/s]  = v_gain * v          turn rate [rad/s] = w_gain * w          heading drift = drift_rad_per_m * distance
motion.json also keeps `k` (mixing turn gain) and `min_pwm`, which robot_udp.py reads; the other keys are ignored there.
Repeatability limits (proposed, not in the plan yet): coefficient of variation of the forward gain and of the turn gain (distance or angle per second the wheels really turned, so R1 hold-time scatter does not count) <= 10 % each; fit exits 1 when a limit or the number of runs is missed. The raw angle / distance spreads are reported too.
"""
import argparse
import csv
import json
import math
import re
import statistics
import time
from datetime import date
from pathlib import Path

COLS = ["run_id", "kind", "v", "w", "seconds_commanded", "moving_s", "forward_m", "lateral_m", "turn_deg", "notes"]
LOG = "/home/jetbot/sentry/robot_udp.log"
CALIB_ON_ROBOT = "/home/jetbot/sentry/calib/motion.json"


def moving_seconds(log_lines):
    """Seconds the motors were non-zero, from robot_udp.log lines like '09:19:19.123 motors +0.12 +0.12' (only differences of the log's own times are used; a run across midnight is not handled)."""
    ev = []
    for line in log_lines:
        m = re.match(r"(\d+):(\d+):(\d+\.\d+) motors ([+-]\d+\.\d+) ([+-]\d+\.\d+)", line)
        if m:
            ev.append((int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]), float(m[4]), float(m[5])))
    return sum(t2 - t for (t, left, right), (t2, _, _) in zip(ev, ev[1:]) if left or right)


def _cv(xs):
    return statistics.pstdev(xs) / abs(statistics.mean(xs)) if len(xs) > 1 and statistics.mean(xs) else float("nan")


def fit(rows, max_speed=0.3, k=1.0, min_pwm=0.12, max_gain_cv=0.10, min_runs=5):
    """rows: dicts with the COLS keys (numbers already floats). -> motion.json dict."""
    straight = [r for r in rows if r["kind"] == "straight" and r["moving_s"] > 0.3 and r["v"]]
    turn = [r for r in rows if r["kind"] == "turn" and r["moving_s"] > 0.3 and r["w"]]
    v_gains = [r["forward_m"] / (r["v"] * r["moving_s"]) for r in straight]
    w_gains = [math.radians(r["turn_deg"]) / (r["w"] * r["moving_s"]) for r in turn]
    drift = [r["lateral_m"] / r["forward_m"] for r in straight if r["forward_m"]]
    out = {"k": k, "min_pwm": min_pwm, "max_speed": max_speed, "date": date.today().isoformat(),
           "v_gain_m_per_s": statistics.median(v_gains) if v_gains else None,
           "w_gain_rad_per_s": statistics.median(w_gains) if w_gains else None,
           "drift_rad_per_m": statistics.median(drift) if drift else None,
           "runs": {"straight": len(straight), "turn": len(turn)},
           "repeatability": {"forward_gain_cv": _cv(v_gains), "turn_gain_cv": _cv(w_gains),
                             "turn_angle_std_deg": statistics.pstdev([r["turn_deg"] for r in turn]) if len(turn) > 1 else None,
                             "forward_m_std": statistics.pstdev([r["forward_m"] for r in straight]) if len(straight) > 1 else None}}
    rep = out["repeatability"]
    problems = []
    if len(straight) < min_runs or len(turn) < min_runs:
        problems.append("fewer than %d straight / turn runs (%d / %d)" % (min_runs, len(straight), len(turn)))
    for name in ("forward_gain_cv", "turn_gain_cv"):
        if not math.isnan(rep[name]) and rep[name] > max_gain_cv:
            problems.append("%s CV %.1f %% > %.0f %%" % (name.split("_")[0], 100 * rep[name], 100 * max_gain_cv))
    out["passed"], out["problems"] = not problems, problems
    return out


def read_rows(path):
    rows = []
    for r in csv.DictReader(Path(path).open(encoding="utf-8")):
        rows.append({"kind": r["kind"], **{c: float(r[c] or 0) for c in ("v", "w", "seconds_commanded", "moving_s", "forward_m", "lateral_m", "turn_deg")}})
    return rows


def _ssh(ip, user, password):
    import paramiko  # imported here so the pure functions above can be tested without it
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(ip, username=user, password=password, timeout=20, look_for_keys=False, allow_agent=False)
    return c


def _sh(c, cmd):
    return c.exec_command(cmd, timeout=30)[1].read().decode(errors="replace")


def run_trials(a):
    from sentry.net.discover import resolve
    from sentry.net.udp_tx import UDPSender
    ip = resolve(a.ip)
    c = _ssh(ip, a.user, a.password)
    path = Path(a.csv)
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    n = 0 if new else sum(1 for _ in path.open(encoding="utf-8")) - 1
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(COLS)
        for i in range(a.runs):
            n += 1
            input("\nrun %d (%s, v=%.2f w=%.2f, %.1f s): robot on the start mark, e-stop armed. Press Enter, then HOLD R1 for the whole run... " % (n, a.kind, a.v, a.w, a.seconds))
            before = int(_sh(c, "wc -l < %s" % LOG).strip() or 0)
            sender = UDPSender(ip)
            end = time.perf_counter() + a.seconds
            while time.perf_counter() < end:
                sender.send(a.v, a.w)
                time.sleep(sender.period_s)
            sender.close()
            time.sleep(0.5)
            moving = moving_seconds(_sh(c, "tail -n +%d %s" % (before + 1, LOG)).splitlines())
            print("  the wheels turned for %.2f s of the %.1f s commanded" % (moving, a.seconds))
            if a.kind == "straight":
                fwd, lat, turn = float(input("  forward_m (start mark -> robot centre, metres): ")), float(input("  lateral_m (left +, metres): ")), 0.0
            else:
                fwd, lat, turn = 0.0, 0.0, float(input("  turn_deg (left +): "))
            w.writerow([n, a.kind, a.v, a.w, a.seconds, "%.2f" % moving, fwd, lat, turn, input("  notes (enter for none): ")])
            f.flush()


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="collect trials")
    r.add_argument("--kind", choices=["straight", "turn"], required=True)
    r.add_argument("--v", type=float, default=0.0)
    r.add_argument("--w", type=float, default=0.0)
    r.add_argument("--seconds", type=float, default=4.0)
    r.add_argument("--runs", type=int, default=5)
    r.add_argument("--ip", default="auto")
    r.add_argument("--user", default="jetbot")
    r.add_argument("--password", default="jetbot")
    f = sub.add_parser("fit", help="fit the gains from the trials")
    for p in (r, f):
        p.add_argument("--csv", default="reports/DoanQuocKien/week-02/motion_runs.csv")
    f.add_argument("--out", default="calib/motion.json")
    f.add_argument("--max-speed", type=float, default=0.3, help="the --max-speed robot_udp.py ran with")
    f.add_argument("--min-pwm", type=float, default=0.12)
    f.add_argument("--k", type=float, default=1.0)
    f.add_argument("--push", action="store_true", help="also copy motion.json to the robot (restart robot_udp.py afterwards)")
    f.add_argument("--ip", default="auto")
    f.add_argument("--user", default="jetbot")
    f.add_argument("--password", default="jetbot")
    a = ap.parse_args()
    if a.cmd == "run":
        if (a.kind == "straight" and not a.v) or (a.kind == "turn" and not a.w):
            ap.error("a straight run needs --v, a turn run needs --w")
        run_trials(a)
        return
    out = fit(read_rows(a.csv), a.max_speed, a.k, a.min_pwm)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))
    if a.push:
        from sentry.net.discover import resolve
        c = _ssh(resolve(a.ip), a.user, a.password)
        _sh(c, "mkdir -p /home/jetbot/sentry/calib")
        sftp = c.open_sftp()
        sftp.put(a.out, CALIB_ON_ROBOT)
        sftp.close()
        print("pushed to %s: restart robot_udp.py (or sentry-control) so it reads k / min_pwm" % CALIB_ON_ROBOT)
    print("PASS" if out["passed"] else "FAIL: " + "; ".join(out["problems"]))
    raise SystemExit(0 if out["passed"] else 1)


if __name__ == "__main__":
    main()
