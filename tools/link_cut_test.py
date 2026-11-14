"""Link-cut safety trials (plan: 'Control link', motors stop <= 350 ms after link loss). LAPTOP-PATH evidence only: it is not the 'Edge safety' pass (no on-robot layer exists).

The robot SPINS IN PLACE (v = 0, w = 0.45: no floor space needed). **Exception to the project rule 'motor tests only with the wheels off the ground' (CLAUDE.md):** the stop is read from the video,
which needs a rotating view, so the wheels are on the floor. Conditions: in place only, the e-stop armed and R1 held, 0.3 m of clear floor around the robot; the operator confirms with
--wheels-on-ground-ack (decided by DQK for the 2026-11-08 trials). For each trial: hold R1; the laptop sends the spin command for --spin-s,
then STOPS SENDING (no stop packet: the app 'closed'); the robot's own 0.3 s watchdog must stop it. The stop is seen in the VIDEO (consecutive-frame difference), so the result is an UPPER BOUND on the
motor stop latency: it includes the video delay (a bound of < 0.16 s was measured on 2026-10-30 only, NOT re-measured later) and the frame period (about 0.05 s). Not a mechanical braking measurement.
A trial counts only if it is VALID (validate_trial): enough rest, spin and post-cut frames, clear motion before the cut, R1 held at the cut AND at the end check, and a confirmed last send; the cutoff is the time of the
last send that UDPSender reported as sent (rate-limited sends do not count), taken atomically with stopping the sender thread.

  python -m tools.link_cut_test --label home_1 --trials 5          # robot on, e-stop armed (hold Start 1.5 s), hold R1 when it says so
Output: data/link_safety/<label>_<n>/trials.csv + summary.json (numbers only).
"""
import argparse
import csv
import json
import os
import threading
import time
from pathlib import Path

W_SPIN = 0.45
MIN_REST_FRAMES, MIN_SPIN_FRAMES, MIN_POST_FRAMES = 10, 10, 5
MIN_SPIN_OVER_REST = 3.0
ESTOP_LATCH = "/home/jetbot/sentry/ESTOP"


def motion_series(frames):
    """frames: [(t_arrival, gray_small)] -> [(t, mean abs diff to the previous frame)]."""
    import numpy as np
    out = []
    for (t0, a), (t1, b) in zip(frames, frames[1:]):
        out.append((t1, float(np.abs(a.astype("float32") - b.astype("float32")).mean())))
    return out


def stop_time(series, t_cut, thr, n_still=2):
    """First arrival time after t_cut from which n_still consecutive frames are below thr (the picture has stopped moving); None if never."""
    after = [(t, m) for t, m in series if t >= t_cut]
    for i in range(len(after) - n_still + 1):
        if all(m < thr for _, m in after[i:i + n_still]):
            return after[i][0]
    return None


def threshold(rest, spin):
    """Between the still noise and the spinning level: noise + 25 % of the gap."""
    return rest + 0.25 * (spin - rest)


def validate_trial(rest_n, spin_n, post_n, rest, spin, r1_ok_at_cut, last_ok, r1_ok_after):
    """-> (valid, reason). A trial yields a stop time only when the rest, spin and post-cut samples are sufficient, the picture clearly moved before the cut, R1 was held at the cut
    and at the end check (otherwise the stop may be the R1 release, not the watchdog), and at least one packet was confirmed sent.
    Two polls still do not prove continuous R1 history; this tool reports a video proxy, not watchdog certification."""
    if last_ok is None:
        return False, "no packet was confirmed sent"
    if rest_n < MIN_REST_FRAMES:
        return False, "too few rest frames (%d)" % rest_n
    if spin_n < MIN_SPIN_FRAMES:
        return False, "too few spin frames (%d)" % spin_n
    if spin < max(MIN_SPIN_OVER_REST * rest, rest + 1.0):
        return False, "no clear motion before the cut (spin %.1f, rest %.1f)" % (spin, rest)
    if post_n < MIN_POST_FRAMES:
        return False, "too few frames after the cut (%d)" % post_n
    if not r1_ok_at_cut:
        return False, "R1 was not held at the cut: the stop may be the R1 release"
    if not r1_ok_after:
        return False, "R1 was released before the end check: watchdog-only cause is unconfirmed"
    return True, ""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--label", required=True)
    ap.add_argument("--trials", type=int, default=5)
    ap.add_argument("--spin-s", type=float, default=2.0)
    ap.add_argument("--rest-s", type=float, default=2.0, help="seconds of still picture to measure the noise")
    ap.add_argument("--post-s", type=float, default=1.5, help="seconds watched after the cut")
    ap.add_argument("--pause", type=float, default=3.0, help="seconds between trials")
    ap.add_argument("--ip", default="auto")
    ap.add_argument("--user", default="jetbot")
    ap.add_argument("--password", default=os.environ.get("JETBOT_PASSWORD"))
    ap.add_argument("--wait", type=float, default=90.0, help="seconds to arm the e-stop and hold R1 for each trial")
    ap.add_argument("--min-battery", type=float, default=11.4)
    ap.add_argument("--wheels-on-ground-ack", action="store_true", help="confirm the exception to the wheels-off rule: in-place spin, R1 held, 0.3 m of clear floor")
    ap.add_argument("--out", default="data/link_safety")
    a = ap.parse_args()
    if not a.wheels_on_ground_ack:
        raise SystemExit("ABORT: this test spins the robot with its wheels ON the floor (exception to the wheels-off rule, see the docstring): pass --wheels-on-ground-ack to confirm")
    if not (1 <= a.trials <= 20 and 0.5 <= a.spin_s <= 5 and 0.1 <= a.rest_s <= 10 and 0.2 <= a.post_s <= 5 and 0 <= a.pause <= 30 and 1 <= a.wait <= 600):
        raise SystemExit("ABORT: trials 1-20, spin-s 0.5-5, rest-s 0.1-10, post-s 0.2-5, pause 0-30, wait 1-600")

    import cv2
    from sentry.config import load
    from sentry.net.discover import resolve
    from sentry.net.udp_tx import UDPSender
    from sentry.net.zmq_rx import ZMQReceiver
    from tools import jetbot_ssh
    from tools.calibrate_motion import _sh
    from tools.jetbot_status import ina219_bus_volts
    import winsound

    a.ip = resolve(a.ip)
    password = jetbot_ssh.password(a.password)
    ssh = jetbot_ssh.connect(a.ip, a.user, password)
    volts0 = ina219_bus_volts(jetbot_ssh.sudo(ssh, "i2cget -y 1 0x41 0x02 w", password))
    print("battery %.2f V" % volts0, flush=True)
    if volts0 < a.min_battery:
        raise SystemExit("ABORT: battery %.2f V < %.1f V: charge first" % (volts0, a.min_battery))
    port = load()["net"]["control_port"]
    rx = ZMQReceiver(ip=a.ip)
    rows, volts1, end_reason = [], None, "completed"
    try:
        rx.start()

        def r1_held():
            return _sh(ssh, "test -e %s && echo no || echo yes" % ESTOP_LATCH).strip() == "yes"

        def grab(dur, frames):
            end = time.time() + dur
            while time.time() < end:
                f = rx.read(timeout=0.2)
                if f is not None:
                    frames.append((time.time(), cv2.cvtColor(cv2.resize(f.frame_bgr, (80, 60)), cv2.COLOR_BGR2GRAY)))

        rest_frames = []
        grab(a.rest_s, rest_frames)
        rest_series = motion_series(rest_frames)
        rest = sum(m for _, m in rest_series) / max(1, len(rest_series))
        print("picture noise at rest: %.2f (%d frames)" % (rest, len(rest_frames)), flush=True)
        for k in range(1, a.trials + 1):
            print("\nTRIAL %d of %d: ARM the e-stop (hold Start 1.5 s) and HOLD R1; the robot will SPIN IN PLACE for %.1f s, then the link is cut" % (k, a.trials, a.spin_s), flush=True)
            winsound.Beep(1000, 400)
            winsound.Beep(1400, 400)
            t_end, since = time.time() + a.wait, None
            while True:
                held, now = r1_held(), time.time()
                since = (since or now) if held else None
                if since and now - since >= 0.5:
                    break
                if now > t_end:
                    raise SystemExit("ABORT: R1 not held in time")
                time.sleep(0.2)
            state, lock, s, th = {"send": True, "last_ok": None, "stop": False, "err": None}, threading.Lock(), None, None
            try:
                s = UDPSender(a.ip, port, 30)

                def sender():
                    try:
                        while not state["stop"]:
                            with lock:
                                if state["send"] and s.send(0.0, W_SPIN) is not False:      # only a packet the sender reports as sent counts
                                    state["last_ok"] = time.time()
                            time.sleep(1 / 30.0)
                    except Exception as e:                                                  # never let the thread die silently: the trial is then invalid
                        state["err"] = e
                th = threading.Thread(target=sender)
                th.daemon = True
                th.start()
                frames = []
                grab(a.spin_s, frames)
                spin_series = motion_series(frames)
                spin = sorted(m for _, m in spin_series)[len(spin_series) // 2] if spin_series else 0.0
                r1_at_cut = r1_held()                                                       # R1 must still be held when the link is cut
                with lock:                                                                  # atomic: no send can race the declared cutoff
                    state["send"] = False
                    t_cut = state["last_ok"]
                n_spin = len(frames)
                grab(a.post_s, frames)
                post = [(t, g) for t, g in frames if t_cut is not None and t >= t_cut]
                r1_after = r1_held()
                series = motion_series(frames)
                thr = threshold(rest, spin)
                ok, reason = validate_trial(len(rest_frames), n_spin, len(post), rest, spin, r1_at_cut, t_cut, r1_after)
                if state["err"] is not None:
                    ok, reason = False, "sender thread error: %r" % (state["err"],)
                t_still = stop_time(series, t_cut, thr) if ok else None
                lat = None if t_still is None else t_still - t_cut
                if ok and lat is None:
                    ok, reason = False, "the picture never stopped moving after the cut"
                rows.append(dict(trial=k, valid=int(ok), invalid_reason=reason, spin_median_motion=round(spin, 2), still_noise=round(rest, 2), threshold=round(thr, 2),
                                 stop_seen_after_s=None if lat is None else round(lat, 3), r1_held_at_cut=int(r1_at_cut), r1_held_after=int(r1_after), frames_rest=len(rest_frames), frames_spin=n_spin, frames_post=len(post)))
                print("trial %d: %s | spin motion %.1f (rest %.1f), threshold %.1f, stop seen %s s after the last confirmed packet (upper bound, includes the video delay)" % (
                    k, "VALID" if ok else "INVALID: " + reason, spin, rest, thr, "n/a" if lat is None else "%.3f" % lat), flush=True)
            finally:
                state["stop"] = True                                                        # ALWAYS: stop the thread, then send the stop packet and close (after the measurement)
                if th is not None:
                    th.join(timeout=2.0)
                if s is not None:
                    try:
                        s.close(stop=True)
                    except Exception:
                        pass
            time.sleep(a.pause)
    except BaseException as e:
        end_reason = "error: %s: %s" % (type(e).__name__, e)
        raise
    finally:
        try:
            rx.close()
        except Exception:
            pass
        try:
            volts1 = ina219_bus_volts(jetbot_ssh.sudo(ssh, "i2cget -y 1 0x41 0x02 w", password))
        except Exception:
            volts1 = None
        out_dir = Path(a.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        taken = [int(q.name[len(a.label) + 1:]) for q in out_dir.glob(a.label + "_*") if q.name[len(a.label) + 1:].isdigit()]
        n = 1 + max(taken, default=0)
        while True:
            run_dir = out_dir / ("%s_%d" % (a.label, n))
            try:
                run_dir.mkdir(exist_ok=False)
                break
            except FileExistsError:
                n += 1
        if rows:
            with open(run_dir / "trials.csv", "w", newline="") as fh:
                wr = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
                wr.writeheader()
                wr.writerows(rows)
        lats = sorted(r["stop_seen_after_s"] for r in rows if r["valid"] and r["stop_seen_after_s"] is not None)
        summary = dict(trials=len(rows), valid_trials=len(lats), invalid_trials=[(r["trial"], r["invalid_reason"]) for r in rows if not r["valid"]], upper_bound_s=lats,
                       max_s=max(lats) if lats else None, median_s=lats[len(lats) // 2] if lats else None, end_reason=end_reason, battery_v_start=volts0, battery_v_end=volts1,
                       date=time.strftime("%Y-%m-%d %H:%M"), wheels_on_ground_ack=True,
                       note="upper bound from the video: includes the video delay (< 0.16 s measured only on 2026-10-30) and the frame period; spin in place at w = 0.45 with the wheels on the floor (exception to the wheels-off rule); "
                            "laptop path only, NOT the on-robot Edge safety pass; the plan limit of 0.35 s is not verified by this tool")
        (run_dir / "summary.json").write_text(json.dumps(summary, indent=1, allow_nan=False))
        print("\nSTOP seen after the last confirmed packet (s), valid trials only: %s | invalid: %s | plan limit 0.35 s (upper bounds, include the video delay)" % (lats, summary["invalid_trials"]))
        print("saved", run_dir)


if __name__ == "__main__":
    main()
