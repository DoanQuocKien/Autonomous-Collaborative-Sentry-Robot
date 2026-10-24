"""Drive toward an ArUco board by its bearing and learn the steering offset that cancels the robot's veer (Week 2 session; the same loop is what a chase needs).

  python -m tools.follow_marker --label follow_1 --marker 0 --v 0.7 --stop-m 0.9

  Beeps, waits for R1 (e-stop armed), then drives at --v. Every frame (about 10 per second) the marker bearing b (rad, left positive) feeds a PI controller:
  w = kp * b + integral(ki * b).  The integral settles at the steering that keeps the marker dead ahead against the veer: THAT is the measured trim.
  Stops at --stop-m (estimated marker distance), when the marker is lost for --lost-s, or after --max-s. Release R1 to stop at any time.
  Output: data/follow/<label>/{log.csv,summary.json}: trim_w (the steady integral, normalised w units, sign: add -trim_w to a straight command),
  the veer it corresponds to in deg per metre from the wheel model (7.2 rad/s per unit w, speed from WheelModel), final distance.
Never use --no-estop. The robot only moves while R1 is held.
"""
import argparse
import csv
import json
import math
import os
import threading
import time
from pathlib import Path

W_TO_RADS = 7.2            # calib/motion.json: turn rate = 7.20 (w - 0.130) rad/s; with both wheels above the dead zone the slope is what matters
ESTOP_LATCH = "/home/jetbot/sentry/ESTOP"


class PIController:
    """Bearing (rad, left +) -> w. The integrator is clamped (anti-windup); output clamped to +-w_max."""

    def __init__(self, kp=0.20, ki=0.05, i_max=0.15, w_max=0.30):
        self.kp, self.ki, self.i_max, self.w_max = kp, ki, i_max, w_max
        self.i = 0.0

    def step(self, bearing, dt):
        self.i = max(-self.i_max, min(self.i_max, self.i + self.ki * bearing * dt))
        return max(-self.w_max, min(self.w_max, self.kp * bearing + self.i))


def veer_deg_per_m(trim_w, v):
    """The veer the trim cancels, from the wheel model: the robot turns at W_TO_RADS * (-trim_w) rad/s while it drives at body speed(v) m/s."""
    from sentry.nav.wheel_model import WheelModel
    speed = WheelModel().body_speeds(v, 0.0)[0]
    return math.degrees(-W_TO_RADS * trim_w / speed)


def simulate(bias_rads, v_speed=0.28, dt=0.1, steps=120, latency_steps=2, start_bearing=0.0, ctl=None):
    """Closed loop on a unicycle with a constant veer (rad/s, left +) toward a marker 4 m ahead; -> (final integral, final bearing). Test helper."""
    ctl = ctl or PIController()
    x, y, th = 0.0, 0.0, start_bearing
    pending = [0.0] * latency_steps
    for _ in range(steps):
        dx, dy = 4.0 - x, 0.0 - y
        bearing = math.atan2(dy, dx) - th
        w = ctl.step(bearing, dt)
        pending.append(w)
        w_applied = pending.pop(0)
        th += (W_TO_RADS * w_applied + bias_rads) * dt
        x += v_speed * math.cos(th) * dt
        y += v_speed * math.sin(th) * dt
        if 4.0 - x < 0.8:
            break
    return ctl.i, bearing


def _vision(stop, state, marker_id):
    from sentry.nav.localization import LocalizationTracker
    from sentry.net.zmq_rx import ZMQReceiver
    tr = LocalizationTracker(camera_calib="calib/camera.json")
    with ZMQReceiver() as rx:
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
    ap.add_argument("--v", type=float, default=0.7)
    ap.add_argument("--stop-m", type=float, default=0.9)
    ap.add_argument("--lost-s", type=float, default=1.2, help="keep the last steering this long without a new observation (about 0.34 m of blind driving at 0.28 m/s)")
    ap.add_argument("--max-s", type=float, default=20.0)
    ap.add_argument("--kp", type=float, default=0.20)
    ap.add_argument("--ki", type=float, default=0.05)
    ap.add_argument("--trim0", type=float, default=0.0, help="start value of the integral (normalised w; the veer seen on 2026-10-18 needs about -0.025)")
    ap.add_argument("--min-battery", type=float, default=11.3)
    ap.add_argument("--wait", type=float, default=60.0)
    ap.add_argument("--ip")
    ap.add_argument("--user", default="jetbot")
    ap.add_argument("--password", default=os.environ.get("JETBOT_PASSWORD"))
    a = ap.parse_args()

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
    threading.Thread(target=_vision, args=(stop, state, a.marker), daemon=True).start()
    t_wait = time.perf_counter() + 10
    while not state and time.perf_counter() < t_wait:
        time.sleep(0.1)
    if not state:
        raise SystemExit("marker %d not in view: aim the robot at the board first" % a.marker)
    print("marker %d in view: distance %.2f m, bearing %+.1f deg" % (a.marker, state["dist"], math.degrees(state["bearing"])))
    ctl = PIController(kp=a.kp, ki=a.ki)
    ctl.i = a.trim0
    w = a.trim0
    rows, why = [], "max time"
    sender = UDPSender(ip, load()["net"]["control_port"], 30)
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
        print("R1 held: following marker %d" % a.marker, flush=True)
        t0 = prev = time.perf_counter()
        seen_t, last_ok = state["t"], t0                           # the loss timer starts when R1 is held, not at the observation made before the wait
        while True:
            now = time.perf_counter()
            if now - t0 > a.max_s:
                break
            s = dict(state)
            if s["t"] != seen_t:                                      # a new marker observation
                w = ctl.step(s["bearing"], now - prev)
                seen_t, last_ok = s["t"], now
                prev = now
            if now - last_ok > a.lost_s:
                why = "marker lost"
                break
            if s["dist"] < a.stop_m:
                why = "arrived (%.2f m)" % s["dist"]
                break
            sender.send(a.v, w)
            rows.append((round(now - t0, 3), round(math.degrees(s["bearing"]), 2), round(s["dist"], 3), round(ctl.i, 4), round(w, 4)))
            time.sleep(sender.period_s)
    finally:
        sender.close()                                                 # always sends the stop
        stop.set()
    beep(1000, 300)
    out = Path("data/follow") / a.label
    out.mkdir(parents=True, exist_ok=True)
    with (out / "log.csv").open("w", newline="") as f:
        csv.writer(f).writerows([("t", "bearing_deg", "dist_m", "integral_w", "w")] + rows)
    tail = [r for r in rows if r[0] > 0.5 * (rows[-1][0] if rows else 0)] or rows
    trim = sum(r[3] for r in tail) / len(tail) if tail else 0.0
    summary = dict(label=a.label, marker=a.marker, v=a.v, battery_v=volts, stopped=why, seconds=rows[-1][0] if rows else 0, start_dist_m=rows[0][2] if rows else None,
                   end_dist_m=rows[-1][2] if rows else None, trim_w=round(trim, 4), veer_deg_per_m=round(veer_deg_per_m(trim, a.v), 1) if rows else None,
                   observations=len({(r[1], r[2]) for r in rows}), trim0=a.trim0, mean_abs_bearing_deg=round(sum(abs(r[1]) for r in tail) / len(tail), 2) if tail else None, kp=a.kp, ki=a.ki)
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
