"""Link-cut safety trials (plan: 'Control link', motors stop <= 350 ms after link loss). LAPTOP-PATH evidence only: it is not the 'Edge safety' pass (no on-robot layer exists).

The robot SPINS IN PLACE (v = 0, w = 0.45: no floor space needed, still wheels-on-ground: keep the area clear and the e-stop armed). For each trial: hold R1; the laptop sends the spin command for --spin-s,
then STOPS SENDING (no stop packet: the app 'closed'); the robot's own 0.3 s watchdog must stop it. The stop is seen in the VIDEO (consecutive-frame difference), so the result is an UPPER BOUND on the
motor stop latency: it includes the video delay (bounded < 0.16 s on 2026-10-30) and the frame period (about 0.05 s). Not a mechanical braking measurement.

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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--label", required=True)
    ap.add_argument("--trials", type=int, default=5)
    ap.add_argument("--spin-s", type=float, default=2.0)
    ap.add_argument("--ip", default="auto")
    ap.add_argument("--user", default="jetbot")
    ap.add_argument("--password", default=os.environ.get("JETBOT_PASSWORD"))
    ap.add_argument("--wait", type=float, default=90.0, help="seconds to arm the e-stop and hold R1 for each trial")
    ap.add_argument("--min-battery", type=float, default=11.4)
    ap.add_argument("--out", default="data/link_safety")
    a = ap.parse_args()

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
    rx.start()

    def r1_held():
        return _sh(ssh, "test -e %s && echo no || echo yes" % ESTOP_LATCH).strip() == "yes"

    def grab(dur, frames):
        end = time.time() + dur
        while time.time() < end:
            f = rx.read(timeout=0.2)
            if f is not None:
                g = cv2.cvtColor(cv2.resize(f.frame_bgr, (80, 60)), cv2.COLOR_BGR2GRAY)
                frames.append((time.time(), g))

    rest_frames = []
    grab(2.0, rest_frames)
    rest = sum(m for _, m in motion_series(rest_frames)) / max(1, len(rest_frames) - 1)
    print("picture noise at rest: %.2f" % rest, flush=True)

    rows = []
    for k in range(1, a.trials + 1):
        print("\nTRIAL %d of %d: ARM the e-stop (hold Start 1.5 s) and HOLD R1; the robot will SPIN IN PLACE for %.0f s, then the link is cut" % (k, a.trials, a.spin_s), flush=True)
        winsound.Beep(1000, 400)
        winsound.Beep(1400, 400)
        t_end, since = time.time() + a.wait, None
        while True:
            held = r1_held()
            now = time.time()
            since = (since or now) if held else None
            if since and now - since >= 0.5:
                break
            if now > t_end:
                raise SystemExit("ABORT: R1 not held in time")
            time.sleep(0.2)
        state = {"send": True, "last": None, "stop": False}
        s = UDPSender(a.ip, port, 30)

        def sender():
            while not state["stop"]:
                if state["send"]:
                    s.send(0.0, W_SPIN)
                    state["last"] = time.time()
                time.sleep(1 / 30.0)

        th = threading.Thread(target=sender)
        th.daemon = True
        th.start()
        frames = []
        grab(a.spin_s, frames)
        spin_series = motion_series(frames)
        spin = sorted(m for _, m in spin_series)[len(spin_series) // 2] if spin_series else 0.0
        state["send"] = False                                      # the link is cut: no stop packet
        t_cut = state["last"]
        grab(1.5, frames)
        series = motion_series(frames)
        thr = threshold(rest, spin)
        t_still = stop_time(series, t_cut, thr)
        lat = None if t_still is None else t_still - t_cut
        rows.append(dict(trial=k, spin_median_motion=round(spin, 2), still_noise=round(rest, 2), threshold=round(thr, 2), stop_seen_after_s=None if lat is None else round(lat, 3), r1_still_held=int(r1_held())))
        print("trial %d: spin motion %.1f (rest %.1f), threshold %.1f, stop seen %s s after the last packet (upper bound, includes the video delay)" % (k, spin, rest, thr, "never" if lat is None else "%.3f" % lat), flush=True)
        state["stop"] = True
        th.join(timeout=1.0)
        s.close(stop=True)                                         # stop packet only AFTER the measurement
        time.sleep(3.0)
    volts1 = ina219_bus_volts(jetbot_ssh.sudo(ssh, "i2cget -y 1 0x41 0x02 w", password))
    rx.close()

    out_dir = Path(a.out)
    n = 1 + len(list(out_dir.glob(a.label + "_*"))) if out_dir.exists() else 1
    run_dir = out_dir / ("%s_%d" % (a.label, n))
    run_dir.mkdir(parents=True, exist_ok=True)
    with open(run_dir / "trials.csv", "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)
    lats = [r["stop_seen_after_s"] for r in rows if r["stop_seen_after_s"] is not None]
    summary = dict(trials=len(rows), seen=len(lats), upper_bound_s=sorted(lats), max_s=max(lats) if lats else None, median_s=sorted(lats)[len(lats) // 2] if lats else None,
                   battery_v_start=volts0, battery_v_end=volts1, date=time.strftime("%Y-%m-%d %H:%M"),
                   note="upper bound from the video: includes the video delay (< 0.16 s on 2026-10-30) and the frame period; spin in place at w = 0.45; laptop path only, NOT the on-robot Edge safety pass; plan limit 0.35 s")
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=1, allow_nan=False))
    print("\nSTOP seen after the last packet (s): %s | plan limit 0.35 s (upper bounds, include the video delay)" % lats)
    print("saved", run_dir)


if __name__ == "__main__":
    main()
