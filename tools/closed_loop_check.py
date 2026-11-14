"""Closed-loop turns and drives on the bearing of one ArUco board, with an online trim estimate (the idea: always straighten on the board instead of trusting the open-loop veer).

  python -m tools.closed_loop_check --label cl_1 --marker 0 --repeats 2 --turn-deg 45 --drive-m 0.4 --min-m 1.1

Per repeat: turn LEFT by --turn-deg and RIGHT back in short pulses with a rest and a bearing measurement after each (the camera is blind while the robot spins: motion
blur; sentry/nav/bearing_servo.TurnController learns the degrees per second of pulse; commands are only a stop or a spin above the dead zone), then drive --drive-m toward the board with the PI of tools.follow_marker whose integral STARTS at the Kalman trim estimate
(TrimEstimator: predict before the drive, update with the settled integral after it). Logs the turn errors, the bearing error of every drive and its Gaussian
differential entropy (nats; lower = straighter). Board setup: upright, facing the robot, 1.8-2.0 m ahead, floor clear; --min-m stops the sequence before the wall.
Needs the e-stop armed and R1 held (as follow_marker); never use --no-estop. Output: data/closed_loop/<label>/{log.csv,summary.json}."""
import argparse
import csv
import json
import math
import os
import threading
import time
from pathlib import Path

from sentry.nav.bearing_servo import TrimEstimator, TurnController, heading_entropy_nats
from tools.follow_marker import ESTOP_LATCH, PIController, veer_deg_per_m

TICK_S = 1.0 / 30.0


def _vision(stop, state, marker_id, ip):
    """Like follow_marker._vision, but the receiver gets the robot's resolved address (a second automatic scan inside the thread can miss the robot)."""
    from sentry.nav.localization import LocalizationTracker
    from sentry.net.zmq_rx import ZMQReceiver
    tr = LocalizationTracker(camera_calib="calib/camera.json")
    with ZMQReceiver(ip=ip) as rx:
        while not stop.is_set():
            f = rx.read(timeout=1.0)
            if f is None:
                continue
            for d in tr.detect_markers(f.frame_bgr):
                if d.marker_id == marker_id:
                    state.update(t=time.perf_counter(), bearing=d.bearing_rad, dist=d.distance_m)
                    break


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--label", required=True)
    ap.add_argument("--marker", type=int, default=0)
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--turn-deg", type=float, default=45.0)
    ap.add_argument("--drive-m", type=float, default=0.4)
    ap.add_argument("--min-m", type=float, default=1.1, help="never drive closer to the board than this")
    ap.add_argument("--v", type=float, default=0.55)
    ap.add_argument("--kp", type=float, default=0.20)
    ap.add_argument("--ki", type=float, default=0.05)
    ap.add_argument("--trim0", type=float, default=0.0)
    ap.add_argument("--trim-std0", type=float, default=0.03)
    ap.add_argument("--q-std", type=float, default=0.01, help="how much the trim may change between drives (normalised w)")
    ap.add_argument("--align", action="store_true", help="before each drive, turn (pulse-and-measure, at rest) so the board is back near bearing 0: the turns leave 12-15 deg that the PI cannot remove fast without blurring the image")
    ap.add_argument("--no-ff", action="store_true", help="control run for an A/B comparison: every drive starts at trim 0 (the estimator still records what it measures)")
    ap.add_argument("--rate-deg-s", type=float, default=140.0, help="first guess of the turn gain, deg per second of pulse (125 in the classroom, 147 at the dorm); learned from every pulse")
    ap.add_argument("--hold-s", type=float, default=0.2, help="while no fresh observation for longer than this the drive uses only the feed-forward trim (a strong correction must not be held blind: the image blurs while the robot turns)")
    ap.add_argument("--lost-s", type=float, default=1.2)
    ap.add_argument("--max-s", type=float, default=90.0)
    ap.add_argument("--min-battery", type=float, default=11.3)
    ap.add_argument("--wait", type=float, default=60.0)
    ap.add_argument("--ip")
    ap.add_argument("--user", default="jetbot")
    ap.add_argument("--password", default=os.environ.get("JETBOT_PASSWORD"))
    a = ap.parse_args()
    if a.repeats < 1 or a.drive_m <= 0 or not 0 < abs(a.turn_deg) <= 70:
        raise SystemExit("repeats >= 1, drive-m > 0 and 0 < turn-deg <= 70 (the board must stay in view)")

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
    volts = ina219_bus_volts(jetbot_ssh.sudo(ssh, "i2cget -y 1 0x41 0x02 w", password))
    print("battery %.2f V" % volts)
    if volts < a.min_battery:
        raise SystemExit("battery below %.1f V: charge first" % a.min_battery)
    state, stop = {}, threading.Event()
    threading.Thread(target=_vision, args=(stop, state, a.marker, ip), daemon=True).start()
    t_wait = time.perf_counter() + 10
    while not state and time.perf_counter() < t_wait:
        time.sleep(0.1)
    if not state:
        raise SystemExit("marker %d not in view: aim the robot at the board first" % a.marker)
    d0 = state["dist"]
    print("marker %d in view: distance %.2f m, bearing %+.1f deg" % (a.marker, d0, math.degrees(state["bearing"])))
    if d0 - a.repeats * a.drive_m < a.min_m:
        raise SystemExit("ABORT: %d drives of %.2f m from %.2f m would end closer than --min-m %.2f m" % (a.repeats, a.drive_m, d0, a.min_m))
    est = TrimEstimator(a.trim0, a.trim_std0, a.q_std)
    log, results, seen = [], [], {"t": state["t"]}
    sender = UDPSender(ip, load()["net"]["control_port"], 30)
    t_start, why = None, "done"

    def obs():
        """-> (bearing_deg, dist_m, fresh) from the latest board observation."""
        s = dict(state)
        fresh = s["t"] != seen["t"]
        seen["t"] = s["t"]
        return math.degrees(s["bearing"]), s["dist"], fresh

    def rest(seconds, name):
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < seconds:
            sender.send(0.0, 0.0)
            b, d, _ = obs()
            log.append((round(time.perf_counter() - t_start, 3), name, round(b, 2), round(d, 3), 0.0, 0.0, round(time.perf_counter() - state["t"], 3)))
            time.sleep(TICK_S)

    def turn(target, name):
        ctl = TurnController(target, rate_deg_s=a.rate_deg_s)
        t0 = time.perf_counter()
        while True:
            now = time.perf_counter()
            if now - t_start > a.max_s or now - t0 > 12.0:
                return ctl, "turn timeout"
            b, d, fresh = obs()
            w, done = ctl.step(now, b if fresh else None)
            sender.send(0.0, w)
            log.append((round(now - t_start, 3), name, round(b, 2), round(d, 3), 0.0, round(w, 3), round(now - state["t"], 3)))
            if done:
                return ctl, ctl.reason
            time.sleep(TICK_S)

    try:
        for _ in range(3):
            beep(1500, 300)
        end, held_since, last_poll, started = time.perf_counter() + a.wait, None, 0.0, False
        while time.perf_counter() < end:
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
        print("R1 held: closed-loop sequence starts (hold R1 until the two beeps)", flush=True)
        t_start = time.perf_counter()
        for r in range(1, a.repeats + 1):
            row = {"repeat": r}
            for sign, nm in ((1.0, "turn_left"), (-1.0, "turn_right")):
                ctl, reason = turn(sign * a.turn_deg, "%s_%d" % (nm, r))
                row[nm] = {"target_deg": sign * a.turn_deg, "achieved_deg": round(ctl.progress, 1), "error_deg": round(ctl.error, 1), "pulses": ctl.pulses, "reason": reason}
                print("  %s_%d: target %+.0f achieved %+.1f error %+.1f (%s)" % (nm, r, sign * a.turn_deg, ctl.progress, ctl.error, reason), flush=True)
                if reason in ("board lost", "turn timeout"):
                    raise RuntimeError(reason)
                rest(1.0, "rest")
            if a.align:
                b_now = obs()[0]
                if abs(b_now) > TurnController(1.0, rate_deg_s=a.rate_deg_s).resolution_deg:
                    ctl, reason = turn(max(-70.0, min(70.0, b_now)), "align_%d" % r)        # a left turn lowers the left-positive bearing: target = the bearing itself
                    row["align"] = {"bearing_before_deg": round(b_now, 1), "achieved_deg": round(ctl.progress, 1), "error_deg": round(ctl.error, 1), "pulses": ctl.pulses, "reason": reason}
                    print("  align_%d: bearing before %+.1f, turned %+.1f, error %+.1f (%s)" % (r, b_now, ctl.progress, ctl.error, reason), flush=True)
                    if reason in ("board lost", "turn timeout"):
                        raise RuntimeError(reason)
                    rest(1.0, "rest")
            est.predict()
            pi = PIController(kp=a.kp, ki=a.ki, w_max=min(0.30, max(0.0, a.v - 0.41)))      # the slower wheel must stay above the dead zone (0.40): |w| <= v - 0.40 - 0.01
            pi.i = 0.0 if a.no_ff else est.trim
            w, d_start, t0, prev, last_ok, ints, bears = pi.i, obs()[1], time.perf_counter(), time.perf_counter(), time.perf_counter(), [], []
            while True:
                now = time.perf_counter()
                b, d, fresh = obs()
                if fresh:
                    w, last_ok = pi.step(math.radians(b), now - prev), now
                    prev = now
                if now - last_ok > a.lost_s:
                    raise RuntimeError("marker lost")
                if d_start - d >= a.drive_m or d <= a.min_m or now - t_start > a.max_s:
                    break
                w_out = w if now - last_ok <= a.hold_s else pi.i
                sender.send(a.v, w_out)
                log.append((round(now - t_start, 3), "drive_%d" % r, round(b, 2), round(d, 3), round(pi.i, 4), round(w_out, 4), round(now - state["t"], 3)))
                bears.append(b)
                ints.append(pi.i)
                time.sleep(TICK_S)
            tail = ints[len(ints) // 2:] or ints
            z = sum(tail) / len(tail)
            sd = (sum((x - z) ** 2 for x in tail) / len(tail)) ** 0.5
            trim_before = 0.0 if a.no_ff else est.trim
            est.update(z, sd)
            row["drive"] = {"start_m": round(d_start, 3), "end_m": round(d, 3), "seconds": round(now - t0, 2), "trim_used": round(trim_before, 4), "trim_measured": round(z, 4), "trim_after": round(est.trim, 4), "trim_std_after": round(est.std, 4),
                            "veer_deg_per_m": round(veer_deg_per_m(z, a.v), 1), "mean_abs_bearing_deg": round(sum(abs(x) for x in bears) / max(len(bears), 1), 2),
                            "max_abs_bearing_deg": round(max((abs(x) for x in bears), default=0.0), 2), "entropy_nats": round(heading_entropy_nats(bears), 2) if len(bears) > 1 else None}
            print("  drive_%d: %.2f -> %.2f m, trim used %+.4f measured %+.4f -> estimate %+.4f (std %.4f), mean|b| %.2f deg, entropy %s" % (
                r, d_start, d, trim_before, z, est.trim, est.std, row["drive"]["mean_abs_bearing_deg"], row["drive"]["entropy_nats"]), flush=True)
            results.append(row)
            rest(1.0, "rest")
            if d <= a.min_m + 0.05:
                break
    except RuntimeError as e:
        why = str(e)
        print("STOPPED:", why)
    finally:
        sender.close()                                                      # always sends the stop
        stop.set()
    beep(1000, 300)
    out = Path("data/closed_loop") / a.label
    out.mkdir(parents=True, exist_ok=True)
    with (out / "log.csv").open("w", newline="") as f:
        csv.writer(f).writerows([("t", "segment", "bearing_deg", "dist_m", "integral_w", "w", "obs_age_s")] + log)
    summary = {"label": a.label, "marker": a.marker, "battery_v": volts, "v": a.v, "turn_deg": a.turn_deg, "drive_m": a.drive_m, "min_m": a.min_m, "kp": a.kp, "ki": a.ki, "trim0": a.trim0,
               "q_std": a.q_std, "no_ff": a.no_ff, "align": a.align, "hold_s": a.hold_s, "rate_deg_s": a.rate_deg_s, "ended": why, "start_dist_m": d0, "repeats": results}
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    print("saved", out)


if __name__ == "__main__":
    main()
