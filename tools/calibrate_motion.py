"""Motion calibration: command fixed (v, w), tape-measure what the robot did, fit the dead-reckoning gains -> calib/motion.json.

Two steps (T2, wheels on the floor, e-stop armed, you hold R1 for the whole run):

  1. collect (robot, tape measure, ~20 min). One trial = place the robot at a start mark, the tool streams (v, w) for --seconds, you hold R1, then you type what you measured:
       python -m tools.calibrate_motion run --kind straight --v 1.0 --seconds 4 --runs 5     # forward_m (start mark -> robot centre), lateral_m (left +)
       python -m tools.calibrate_motion run --kind turn --w 1.0 --seconds 2 --runs 5         # turn_deg (left +; stick a tape strip along the robot's centreline before and after, read the angle with a protractor)
     The time the wheels really turned ("moving_s") is read from the robot's robot_udp.log (R1 releases and the watchdog cut runs short), so the gains do not depend on how long you held R1.
     A trial where the log shows no motion (R1 not held, the command below min_pwm, robot_udp.py not writing /home/jetbot/sentry/robot_udp.log) is refused and repeated. Ctrl-C always sends a stop first.
     Every row also records the battery voltage, the robot's k / min_pwm (read from its calib/motion.json) and --max-speed (must equal the --max-speed robot_udp.py runs with; 0.3 in the systemd unit).
  2. fit:
       python -m tools.calibrate_motion fit --push        # data -> calib/motion.json (and onto the robot)
     A failed fit (too few runs, scatter over the limit, mixed settings) prints FAIL, writes nothing and pushes nothing; --force writes it anyway.

Model used by nav/localization.py (per unit of the normalised command, at the recorded max_speed):
    forward speed [m/s] = v_gain * v      turn rate [rad/s] = w_gain * w      path curvature drift [rad/m] = drift_rad_per_m (heading changes by drift_rad_per_m * distance)
    A constant curvature kappa over a straight run of length d leaves a lateral offset of kappa * d^2 / 2, so kappa = 2 * lateral / forward^2.
motion.json also keeps `k` (mixing turn gain) and `min_pwm`, which robot_udp.py reads; the other keys are ignored there.
Repeatability limits (proposed, not in the plan yet): coefficient of variation of the forward gain and of the turn gain (distance or angle per second the wheels really turned, so R1 hold-time scatter does not count) <= 10 % each. The raw angle / distance spreads are reported too.
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

COLS = ["run_id", "kind", "v", "w", "seconds_commanded", "moving_s", "forward_m", "lateral_m", "turn_deg", "battery_v", "max_speed", "k", "min_pwm", "notes"]
LOG = "/home/jetbot/sentry/robot_udp.log"
CALIB_ON_ROBOT = "/home/jetbot/sentry/calib/motion.json"
MIN_MOVING_S = 0.3


def moving_seconds(log_lines):
    """Seconds the motors were non-zero, from robot_udp.log lines like '09:19:19.123 motors +0.12 +0.12' (only differences of the log's own times are used; a time that goes backwards is a run across midnight)."""
    ev, day = [], 0.0
    for line in log_lines:
        m = re.match(r"(\d+):(\d+):(\d+\.\d+) motors ([+-]\d+\.\d+) ([+-]\d+\.\d+)", line)
        if m:
            t = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) + day
            if ev and t < ev[-1][0]:
                day += 86400.0
                t += 86400.0
            ev.append((t, float(m[4]), float(m[5])))
    return sum(t2 - t for (t, left, right), (t2, _, _) in zip(ev, ev[1:]) if left or right)


def _cv(xs):
    """Coefficient of variation, or None when it is undefined (fewer than 2 values or a zero mean): None keeps the JSON valid."""
    if len(xs) < 2 or not statistics.mean(xs):
        return None
    return statistics.pstdev(xs) / abs(statistics.mean(xs))


def fit(rows, max_gain_cv=0.10, min_runs=5):
    """rows: dicts with the COLS keys (numbers already floats). -> motion.json dict; k / min_pwm / max_speed are the values the runs were recorded with."""
    usable = [r for r in rows if r["moving_s"] > MIN_MOVING_S]
    straight = [r for r in usable if r["kind"] == "straight" and r["v"] > 0 and r["forward_m"] > 0]
    turn = [r for r in usable if r["kind"] == "turn" and r["w"]]
    settings = {(r["max_speed"], r["k"], r["min_pwm"]) for r in straight + turn}
    max_speed, k, min_pwm = sorted(settings)[0] if settings else (None, None, None)
    v_gains = [r["forward_m"] / (r["v"] * r["moving_s"]) for r in straight]
    w_gains = [math.radians(r["turn_deg"]) / (r["w"] * r["moving_s"]) for r in turn]
    drift = [2.0 * r["lateral_m"] / r["forward_m"] ** 2 for r in straight]
    batt = [r["battery_v"] for r in straight + turn if r["battery_v"]]
    out = {"k": k, "min_pwm": min_pwm, "max_speed": max_speed, "date": date.today().isoformat(),
           "v_gain_m_per_s": statistics.median(v_gains) if v_gains else None,
           "w_gain_rad_per_s": statistics.median(w_gains) if w_gains else None,
           "drift_rad_per_m": statistics.median(drift) if drift else None,
           "runs": {"straight": len(straight), "turn": len(turn), "dropped": len(rows) - len(straight) - len(turn)},
           "battery_v": {"min": min(batt), "max": max(batt)} if batt else None,
           "repeatability": {"forward_gain_cv": _cv(v_gains), "turn_gain_cv": _cv(w_gains),
                             "turn_angle_std_deg": statistics.pstdev([r["turn_deg"] for r in turn]) if len(turn) > 1 else None,
                             "forward_m_std": statistics.pstdev([r["forward_m"] for r in straight]) if len(straight) > 1 else None}}
    rep, problems = out["repeatability"], []
    if len(settings) > 1:
        problems.append("runs were recorded with different max_speed / k / min_pwm: %s" % sorted(settings))
    if len(straight) < min_runs or len(turn) < min_runs:
        problems.append("fewer than %d straight / turn runs (%d / %d; %d rows unusable)" % (min_runs, len(straight), len(turn), out["runs"]["dropped"]))
    for name in ("forward_gain_cv", "turn_gain_cv"):
        if rep[name] is not None and rep[name] > max_gain_cv:
            problems.append("%s CV %.1f %% > %.0f %%" % (name.split("_")[0], 100 * rep[name], 100 * max_gain_cv))
    out["passed"], out["problems"] = not problems, problems
    return out


def suggest_trim(out):
    """The `trim` (common.mixing.apply_trim) that would cancel the measured drift. Heading error rate = drift * speed; a trim t makes the wheels differ by 2*t*v (normalised),
    which turns the robot by 2*t*v * w_gain / (2*k) rad/s per unit command, so t = -drift * v_gain * k / w_gain (clamped to +-0.2). None when a value is missing.
    The runs are recorded WITH the trim that was on the robot, so the suggestion is an increment: add it to the current `trim` in calib/motion.json."""
    d, vg, wg, k = (out.get(x) for x in ("drift_rad_per_m", "v_gain_m_per_s", "w_gain_rad_per_s", "k"))
    if None in (d, vg, wg, k) or not wg:
        return None
    return max(-0.2, min(0.2, -d * vg * k / wg))


def read_rows(path):
    rows = []
    for r in csv.DictReader(Path(path).open(encoding="utf-8")):
        rows.append({"kind": r["kind"], **{c: float(r.get(c) or 0) for c in COLS if c not in ("run_id", "kind", "notes")}})
    return rows


def _ssh(ip, user, password):
    from tools import jetbot_ssh  # pinned host key, no password on any command line
    return jetbot_ssh.connect(ip, user, password)


def _sh(c, cmd):
    return c.exec_command(cmd, timeout=30)[1].read().decode(errors="replace")


def _ask(prompt):
    while True:
        try:
            return float(input(prompt).replace(",", ".").strip())
        except ValueError:
            print("  a number please (metres / degrees, no units)")


def run_trials(a):
    from sentry.net.discover import resolve
    from sentry.net.udp_tx import UDPSender
    from tools.jetbot_status import ina219_bus_volts
    from tools import jetbot_ssh
    ip = resolve(a.ip)
    a.password = jetbot_ssh.password(a.password)
    c = _ssh(ip, a.user, a.password)
    try:
        robot_cal = json.loads(_sh(c, "cat %s 2>/dev/null" % CALIB_ON_ROBOT) or "{}")
    except ValueError:
        robot_cal = {}
    k, min_pwm = robot_cal.get("k", 1.0), robot_cal.get("min_pwm", 0.0)
    print("robot calibration: k %.2f, min_pwm %.2f; recording max_speed %.2f (must equal robot_udp.py --max-speed)" % (k, min_pwm, a.max_speed))
    path = Path(a.csv)
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    n = 0 if new else sum(1 for _ in path.open(encoding="utf-8")) - 1
    done = 0
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(COLS)
        while done < a.runs:
            input("\nrun %d (%s, v=%.2f w=%.2f, %.1f s): robot on the start mark, e-stop armed. Press Enter, then HOLD R1 for the whole run... " % (n + 1, a.kind, a.v, a.w, a.seconds))
            before = int(_sh(c, "wc -l < %s" % LOG).strip() or 0)
            sender = UDPSender(ip)
            try:
                end = time.perf_counter() + a.seconds
                while time.perf_counter() < end:
                    sender.send(a.v, a.w)
                    time.sleep(sender.period_s)
            finally:
                sender.close()  # always sends the stop, also on Ctrl-C
            time.sleep(0.5)
            moving = moving_seconds(_sh(c, "tail -n +%d %s" % (before + 1, LOG)).splitlines())
            print("  the wheels turned for %.2f s of the %.1f s commanded" % (moving, a.seconds))
            if moving <= MIN_MOVING_S:
                print("  no usable motion in the robot's log (R1 not held? command below min_pwm? robot_udp.py not writing %s?): not recorded, repeat this run" % LOG)
                continue
            volts = ina219_bus_volts(jetbot_ssh.sudo(c, "i2cget -y 1 0x41 0x02 w", a.password))
            if a.kind == "straight":
                fwd, lat, turn = _ask("  forward_m (start mark -> robot centre, metres): "), _ask("  lateral_m (left +, metres): "), 0.0
            else:
                fwd, lat, turn = 0.0, 0.0, _ask("  turn_deg (left +): ")
            n += 1
            done += 1
            w.writerow([n, a.kind, a.v, a.w, a.seconds, "%.2f" % moving, fwd, lat, turn, "%.2f" % volts, a.max_speed, k, min_pwm, input("  notes (enter for none): ")])
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
    r.add_argument("--max-speed", type=float, default=0.3, help="the --max-speed robot_udp.py runs with (recorded with every run)")
    r.add_argument("--ip", default="auto")
    r.add_argument("--user", default="jetbot")
    r.add_argument("--password", help="default: JETBOT_PASSWORD, else asked")
    f = sub.add_parser("fit", help="fit the gains from the trials")
    for p in (r, f):
        p.add_argument("--csv", default="reports/DoanQuocKien/week-02/motion_runs.csv")
    f.add_argument("--out", default="calib/motion.json")
    f.add_argument("--push", action="store_true", help="also copy motion.json to the robot (restart robot_udp.py afterwards)")
    f.add_argument("--apply-trim", action="store_true", help="add the suggested drift trim to the `trim` already in --out (robot_udp.py applies it; repeat the straight runs to check)")
    f.add_argument("--force", action="store_true", help="write (and push) even when the fit failed")
    f.add_argument("--ip", default="auto")
    f.add_argument("--user", default="jetbot")
    f.add_argument("--password", help="default: JETBOT_PASSWORD, else asked (only with --push)")
    a = ap.parse_args()
    if a.cmd == "run":
        if not 0 < a.seconds < float("inf"):
            ap.error("--seconds must be positive and finite")
        if not (-1 <= a.v <= 1 and -1 <= a.w <= 1):
            ap.error("--v and --w are normalised to [-1, 1]")
        if a.kind == "straight" and not (a.v > 0 and a.w == 0):
            ap.error("a straight run needs --v > 0 and no --w (reverse and arcs are not modelled)")
        if a.kind == "turn" and not (a.w != 0 and a.v == 0):
            ap.error("a turn run needs --w != 0 and no --v (turn in place)")
        run_trials(a)
        return
    out = fit(read_rows(a.csv))
    print(json.dumps(out, indent=2, allow_nan=False))
    if not out["passed"] and not a.force:
        print("FAIL: " + "; ".join(out["problems"]) + " -> nothing written, nothing pushed (--force to write anyway)")
        raise SystemExit(1)
    trim = suggest_trim(out)
    out["trim_suggested"] = None if trim is None else round(trim, 4)
    print("drift %s rad/m -> suggested trim increment %s" % (out["drift_rad_per_m"], out["trim_suggested"]))
    if a.apply_trim and trim is not None:
        old = json.loads(Path(a.out).read_text(encoding="utf-8")).get("trim", 0.0) if Path(a.out).exists() else 0.0
        out["trim"] = round(max(-0.2, min(0.2, old + trim)), 4)
        print("trim %.4f -> %.4f (written; push it and repeat the straight runs)" % (old, out["trim"]))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print("written %s" % a.out)
    if a.push:
        from sentry.net.discover import resolve
        from tools import jetbot_ssh
        c = _ssh(resolve(a.ip), a.user, jetbot_ssh.password(a.password))
        _sh(c, "mkdir -p /home/jetbot/sentry/calib")
        sftp = c.open_sftp()
        sftp.put(a.out, CALIB_ON_ROBOT)
        sftp.close()
        print("pushed to %s: restart robot_udp.py (or sentry-control) so it reads k / min_pwm" % CALIB_ON_ROBOT)
    print("PASS" if out["passed"] else "FAIL (forced): " + "; ".join(out["problems"]))
    raise SystemExit(0 if out["passed"] else 1)


if __name__ == "__main__":
    main()
