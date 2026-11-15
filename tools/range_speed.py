"""Straight-drive speed from the RANGE to one ArUco board (the range is good to about 5 mm; no marker orientation is used): forward at v = 0.55 and 0.75, reverse at v = -0.45.

  python -m tools.range_speed --label rs_1 --marker 0 --ip <robot ip>

Each forward run drives --fwd-s seconds (or until the range falls to --min-m) open loop (w = 0); the reverse run that follows backs away until the range is back at the start
value (never more than --back-m behind the start, never longer than --rev-max-s), so the robot stays near its start spot and the board stays in view. The speed is the slope of the
range against time over the steady part of the run (the first --skip-s seconds are the start-up). Also logs the bearing change (the open-loop veer) and the battery at the start and end.
Board: upright, facing the robot, about 2.4 m ahead; at least 1.2 m of free floor in every direction (the runs stay within -0.35 m / +0.6 m of the start along the line to the board).
The e-stop must be armed and R1 held (as follow_marker); never use --no-estop. Output: data/range_speed/<label>/{runs.csv,summary.json}."""
import argparse
import csv
import json
import math
import os
import threading
import time
from pathlib import Path

from sentry.nav.bearing_servo import TurnController
from tools.closed_loop_check import _vision
from tools.follow_marker import ESTOP_LATCH

TICK_S = 1.0 / 30.0


def fit_speed(samples, skip_s=0.5):
    """samples: [(t, range_m)] of one straight run -> (speed m/s, residual sd m, n). Speed > 0 when the range FALLS (driving toward the board). Least squares on t >= t0 + skip_s."""
    pts = [(t, r) for t, r in samples if t - samples[0][0] >= skip_s]
    if len(pts) < 4:
        return None, None, len(pts)
    n = len(pts)
    tm = sum(t for t, _ in pts) / n
    rm = sum(r for _, r in pts) / n
    sxx = sum((t - tm) ** 2 for t, _ in pts)
    if sxx <= 0:
        return None, None, n
    slope = sum((t - tm) * (r - rm) for t, r in pts) / sxx
    resid = [r - (rm + slope * (t - tm)) for t, r in pts]
    sd = math.sqrt(sum(e * e for e in resid) / max(n - 2, 1))
    return -slope, sd, n


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--label", required=True)
    ap.add_argument("--marker", type=int, default=0)
    ap.add_argument("--fwd-v", type=float, nargs="+", default=[0.55, 0.55, 0.55, 0.75, 0.75, 0.75], help="one forward run (each followed by a reverse run) per value")
    ap.add_argument("--rev-v", type=float, default=-0.45)
    ap.add_argument("--fwd-s", type=float, nargs="+", default=[1.8], help="command time of each forward run (cycled): several different times separate the speed from the start-up loss")
    ap.add_argument("--rev-max-s", type=float, default=4.0)
    ap.add_argument("--skip-s", type=float, default=0.5)
    ap.add_argument("--min-m", type=float, default=1.2, help="stop a forward run at this range")
    ap.add_argument("--back-m", type=float, default=0.35, help="a reverse run never goes further than this behind the start range")
    ap.add_argument("--lost-s", type=float, default=1.2)
    ap.add_argument("--min-battery", type=float, default=11.3)
    ap.add_argument("--wait", type=float, default=60.0)
    ap.add_argument("--ip")
    ap.add_argument("--user", default="jetbot")
    ap.add_argument("--password", default=os.environ.get("JETBOT_PASSWORD"))
    a = ap.parse_args()
    if any(not 0.3 <= v <= 1.0 for v in a.fwd_v) or not -1.0 <= a.rev_v <= -0.3:
        raise SystemExit("forward v in [0.3, 1], reverse v in [-1, -0.3] (above the motor dead zone)")

    from sentry.config import load
    from sentry.net.discover import resolve
    from sentry.net.udp_tx import UDPSender
    from tools import jetbot_ssh
    from tools.calibrate_motion import _sh
    from tools.jetbot_status import ina219_bus_volts
    from tools.speed_trial import beep

    ip = resolve(a.ip)
    password = jetbot_ssh.password(a.password)
    ssh = jetbot_ssh.connect(ip, a.user, password)

    def battery():
        return ina219_bus_volts(jetbot_ssh.sudo(ssh, "i2cget -y 1 0x41 0x02 w", password))
    volts0 = battery()
    print("battery %.2f V" % volts0)
    if volts0 < a.min_battery:
        raise SystemExit("battery below %.1f V: charge first" % a.min_battery)
    state, stop = {}, threading.Event()
    threading.Thread(target=_vision, args=(stop, state, a.marker, ip), daemon=True).start()
    t_wait = time.perf_counter() + 10
    while not state and time.perf_counter() < t_wait:
        time.sleep(0.1)
    if not state:
        raise SystemExit("marker %d not in view: aim the robot at the board first" % a.marker)
    r0 = state["dist"]
    print("marker %d in view: range %.2f m, bearing %+.1f deg" % (a.marker, r0, math.degrees(state["bearing"])))
    if r0 - 0.8 < a.min_m:
        raise SystemExit("ABORT: the range %.2f m is too short for a forward run of up to 0.8 m with --min-m %.2f" % (r0, a.min_m))
    sender = UDPSender(ip, load()["net"]["control_port"], 30)
    runs, samples_all, seen = [], [], {"t": state["t"]}
    t_start = None
    why = "done"

    def run(kind, v, name, fwd_s_now=0.0):
        """-> run record. Drives (v, 0) until the stop rule of its kind."""
        s0 = dict(state)
        start_range, start_bearing = s0["dist"], math.degrees(s0["bearing"])
        t0 = time.perf_counter()
        last_ok = t0
        pts = []
        while True:
            now = time.perf_counter()
            s = dict(state)
            if s["t"] != seen["t"]:
                seen["t"], last_ok = s["t"], now
                pts.append((now, s["dist"]))
                samples_all.append((round(now - t_start, 3), name, round(s["dist"], 4), round(math.degrees(s["bearing"]), 2)))
            if now - last_ok > a.lost_s:
                raise RuntimeError("marker lost during %s" % name)
            elapsed = now - t0
            if kind == "fwd" and (elapsed >= fwd_s_now or s["dist"] <= a.min_m):
                break
            if kind == "rev" and (elapsed >= a.rev_max_s or s["dist"] >= r_ref + 0.05 or s["dist"] >= r_ref + a.back_m):
                break
            sender.send(v, 0.0)
            time.sleep(TICK_S)
        cmd_s = time.perf_counter() - t0
        for _ in range(6):
            sender.send(0.0, 0.0)
            time.sleep(TICK_S)
        speed, sd, n = fit_speed(pts, a.skip_s)
        end = dict(state)
        return {"name": name, "kind": kind, "v": v, "seconds": round(time.perf_counter() - t0, 2), "command_s": round(cmd_s, 2), "start_range_m": round(start_range, 3), "end_range_m": round(end["dist"], 3),
                "speed_m_s": None if speed is None else round(abs(speed), 4), "direction_ok": None if speed is None else (speed > 0) == (kind == "fwd"), "fit_resid_sd_m": None if sd is None else round(sd, 4), "n_obs": n,
                "bearing_change_deg": round(math.degrees(end["bearing"]) - start_bearing, 2)}

    def rest(seconds):
        """Stand still for `seconds`; -> the median range of the fresh observations in the last 0.6 s (None if fewer than 3): the range AT REST, good to a few mm."""
        t0 = time.perf_counter()
        vals = []
        while time.perf_counter() - t0 < seconds:
            sender.send(0.0, 0.0)
            s_ = dict(state)
            if s_["t"] != seen["t"]:
                seen["t"] = s_["t"]
                if time.perf_counter() - t0 >= seconds - 0.6:
                    vals.append(s_["dist"])
            time.sleep(TICK_S)
        vals.sort()
        return vals[len(vals) // 2] if len(vals) >= 3 else None

    def aim():
        """Re-aim at the board with the pulse-and-measure turn when its bearing is beyond 12 deg (the open-loop drives veer 10-30 deg per run); -> True if it turned."""
        b = math.degrees(dict(state)["bearing"])
        if abs(b) <= 12.0:
            return False
        ctl = TurnController(max(-60.0, min(60.0, b)))
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < 12.0:
            now = time.perf_counter()
            s_ = dict(state)
            fresh = s_["t"] != seen["t"]
            seen["t"] = s_["t"]
            w, done = ctl.step(now, math.degrees(s_["bearing"]) if fresh else None)
            sender.send(0.0, w)
            if done:
                break
            time.sleep(TICK_S)
        if ctl.reason and ctl.reason == "board lost":
            raise RuntimeError("board lost while aiming")
        return True

    try:
        for _ in range(3):
            beep(1500, 300)
        end_t, held_since, last_poll, started = time.perf_counter() + a.wait, None, 0.0, False
        while time.perf_counter() < end_t:
            sender.send(0.0, 0.0)
            now = time.perf_counter()
            if now - last_poll >= 0.25:
                last_poll = now
                held = _sh(ssh, "test -e %s && echo no || echo yes" % ESTOP_LATCH).strip() == "yes"
                held_since = (held_since or now) if held else None
                if held_since and now - held_since >= 0.5:
                    started = True
                    break
            time.sleep(sender.period_s)
        if not started:
            raise SystemExit("ABORT: R1 not held (and the e-stop armed) within %.0f s" % a.wait)
        print("R1 held: runs start (hold R1 until the two beeps)", flush=True)
        t_start = time.perf_counter()
        r_rest = rest(1.5)
        if r_rest is None:
            raise RuntimeError("no steady range at the start")
        for i, v in enumerate(a.fwd_v, 1):
            r_ref = r_rest                                                # the range the reverse run returns to
            for kind, vv, nm in (("fwd", v, "fwd_%d_v%.2f" % (i, v)), ("rev", a.rev_v, "rev_%d_v%.2f" % (i, a.rev_v))):
                if aim():
                    r_new = rest(1.5)
                    if r_new is None:
                        raise RuntimeError("no steady range after aiming")
                    r_rest = r_new
                    if kind == "fwd":
                        r_ref = r_rest
                rec = run(kind, vv, nm, a.fwd_s[(i - 1) % len(a.fwd_s)])
                r_after = rest(1.5)
                rec["rest_start_m"] = None if r_rest is None else round(r_rest, 4)
                rec["rest_end_m"] = None if r_after is None else round(r_after, 4)
                if r_rest is not None and r_after is not None and rec["command_s"] > 0:
                    moved = (r_rest - r_after) if kind == "fwd" else (r_after - r_rest)        # metres driven (positive = the intended direction)
                    rec["moved_at_rest_m"] = round(moved, 4)
                    rec["mean_speed_rest_m_s"] = round(moved / rec["command_s"], 4)
                runs.append(rec)
                print("  %-14s v %+.2f: command %.1f s, at rest %s -> %s m, moved %s m, mean speed %s m/s | in-motion fit %s m/s (resid sd %s m, n %d), bearing %+.1f deg" % (
                    rec["name"], vv, rec["command_s"], rec["rest_start_m"], rec["rest_end_m"], rec.get("moved_at_rest_m"), rec.get("mean_speed_rest_m_s"), rec["speed_m_s"], rec["fit_resid_sd_m"], rec["n_obs"], rec["bearing_change_deg"]), flush=True)
                if r_after is None:
                    raise RuntimeError("no steady range after %s" % nm)
                r_rest = r_after
    except RuntimeError as e:
        why = str(e)
        print("STOPPED:", why)
    finally:
        sender.close()                                                    # always sends the stop
        stop.set()
    beep(1000, 300)
    volts1 = battery()
    out = Path("data/range_speed") / a.label
    out.mkdir(parents=True, exist_ok=True)
    with (out / "runs.csv").open("w", newline="") as f:
        csv.writer(f).writerows([("t", "run", "range_m", "bearing_deg")] + samples_all)
    summary = {"label": a.label, "marker": a.marker, "battery_start_v": round(volts0, 3), "battery_end_v": round(volts1, 3), "start_range_m": r0, "skip_s": a.skip_s, "ended": why, "runs": runs}
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    print("battery %.2f -> %.2f V; saved %s" % (volts0, volts1, out))


if __name__ == "__main__":
    main()
