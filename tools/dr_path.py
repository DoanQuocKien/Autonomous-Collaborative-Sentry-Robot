"""T2 dead reckoning over a straight path (Week 2 session): drive, log commands and camera frames, replay offline with and without ArUco correction.

  python -m tools.dr_path --label rugged_1 --anchors data/dr_anchors_1018.csv --dist 3.0 --expect-scale 0.72
      beeps, waits for R1 (e-stop armed), drives v for the time the wheel model needs for --dist at --expect-scale, stops,
      asks for the true end position read with a tape (forward and left from the start cross, heading), then replays the logged
      commands and frames through LocalizationTracker for every scale in --scales, with and without marker correction.
  python -m tools.dr_path --label rugged_1 --replay-only --anchors ... --forward 2.95 --lateral -0.08 --heading -4

Frame: x forward along the path from the point under the lens at the start, y left, heading 0 = along +x. The anchors CSV is
marker_id,x_m,y_m,z_m,yaw_deg (z: marker centre above the floor; yaw: the direction the marker FACES in this frame, a board
facing the robot at the end of the path is 180). Output: data/dr_path/<label>/{commands.csv,frames/,summary.json}.
Closed loop (--follow ID): instead of driving open loop, steer by the bearing of marker ID with the PI controller of tools.follow_marker (the veer of a real
floor and real motors is corrected as the robot drives; the commands that were sent, including the steering, are logged and replayed) and stop when that
marker is --stop-m away (a board 3.8 m ahead and --stop-m 0.8 is a 3.0 m path).
Acceptance (Implementation Plan 4.3): end error <= 15 cm with correction, <= 40 cm without. Never use --no-estop; R1 held.
"""
import argparse
import csv
import json
import math
import os
import threading
import time
from pathlib import Path

MAX_SPEED = 0.3
ESTOP_LATCH = "/home/jetbot/sentry/ESTOP"
MIN_BATTERY_V = 11.3


def replay(cmds, frames, anchors_csv, scale, correct, alpha=0.4):
    """cmds: [(t, v, w)] at the send rate; frames: [(t, bgr)] sorted by t. -> (x, y, heading_deg, corrections)."""
    from sentry.nav.localization import LocalizationTracker
    tr = LocalizationTracker(camera_calib="calib/camera.json" if correct else None)
    tr.scale = scale
    tr.set_pose(0.0, 0.0, 0.0)
    if anchors_csv:
        tr.load_anchors_csv(anchors_csv)
    fi, prev = 0, cmds[0][0] if cmds else 0.0
    for t, v, w in cmds:
        tr.update_odometry(v, w, t - prev, t)
        prev = t
        while correct and fi < len(frames) and frames[fi][0] <= t:
            tr.update_with_markers(frames[fi][1], alpha=alpha, t=t)
            fi += 1
    return tr.pose.x, tr.pose.y, math.degrees(tr.pose.theta), tr.corrections_count


def end_error_m(est, true_xy):
    return math.hypot(est[0] - true_xy[0], est[1] - true_xy[1])


def drive_seconds(dist_m, v, expect_scale):
    from sentry.nav.wheel_model import WheelModel
    speed = WheelModel().body_speeds(v, 0.0)[0] * expect_scale
    return dist_m / speed


def _frame_thread(stop, frames):
    from sentry.net.zmq_rx import ZMQReceiver
    with ZMQReceiver() as rx:
        last = 0.0
        while not stop.is_set():
            try:
                f = rx.read(timeout=1.0)
            except Exception:
                continue
            if f is None:                                  # read timed out (also at the end of the run)
                continue
            now = time.perf_counter()
            if now - last >= 0.1:                      # about 10 frames per second are enough for marker corrections
                frames.append((now, f.frame_bgr))
                last = now


def drive(a, out):
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
    seconds = a.seconds or drive_seconds(a.dist, a.v, a.expect_scale)
    print("drive v=%.2f for %.1f s (the model at scale %.2f predicts %.2f m)" % (a.v, seconds, a.expect_scale, a.dist))
    frames, cmds, stop = [], [], threading.Event()
    th = threading.Thread(target=_frame_thread, args=(stop, frames), daemon=True)
    th.start()
    time.sleep(2.0)
    state = {}
    if a.follow is not None:
        from tools.follow_marker import _vision
        threading.Thread(target=_vision, args=(stop, state, a.follow), daemon=True).start()
        t_wait = time.perf_counter() + 10
        while not state and time.perf_counter() < t_wait:
            time.sleep(0.1)
        if not state:
            raise SystemExit("marker %d not in view: aim the robot at the board first" % a.follow)
        print("marker %d in view: distance %.2f m, bearing %+.1f deg" % (a.follow, state["dist"], math.degrees(state["bearing"])))
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
        print("R1 held: driving", flush=True)
        t0 = time.perf_counter()
        frames.clear()
        if a.follow is None:
            while time.perf_counter() - t0 < seconds:
                sender.send(a.v, 0.0)
                cmds.append((time.perf_counter(), a.v, 0.0))
                time.sleep(sender.period_s)
        else:
            from tools.follow_marker import PIController
            ctl, w, prev = PIController(kp=a.kp, ki=a.ki), 0.0, t0
            seen_t, last_ok, why = state["t"], t0, "max time"
            while time.perf_counter() - t0 < a.max_s:
                now = time.perf_counter()
                s_ = dict(state)
                if s_["t"] != seen_t:                                  # a new observation of the marker
                    w = ctl.step(s_["bearing"], now - prev)
                    seen_t, last_ok, prev = s_["t"], now, now
                if now - last_ok > a.lost_s:
                    why = "marker lost"
                    break
                if s_["dist"] < a.stop_m:
                    why = "arrived (%.2f m)" % s_["dist"]
                    break
                sender.send(a.v, w)
                cmds.append((now, a.v, w))
                time.sleep(sender.period_s)
            print("stopped: %s, last steering w %.3f, integral %.4f" % (why, w, ctl.i), flush=True)
    finally:
        sender.close()                                     # always sends the stop
        stop.set()
    time.sleep(0.5)
    beep(1000, 300)
    out.mkdir(parents=True, exist_ok=True)
    (out / "frames").mkdir(exist_ok=True)
    import cv2
    for i, (t, img) in enumerate(frames):
        cv2.imwrite(str(out / "frames" / ("%03d_%.3f.jpg" % (i, t))), img)
    with (out / "commands.csv").open("w", newline="") as f:
        csv.writer(f).writerows([("t", "v", "w")] + [(round(t, 4), v, w) for t, v, w in cmds])
    return cmds, frames, volts, seconds


def load_run(out):
    import cv2
    with (out / "commands.csv").open() as f:
        cmds = [(float(r["t"]), float(r["v"]), float(r["w"])) for r in csv.DictReader(f)]
    frames = []
    for p in sorted((out / "frames").glob("*.jpg")):
        frames.append((float(p.stem.split("_")[1]), cv2.imread(str(p))))
    return cmds, frames


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--label", required=True)
    ap.add_argument("--anchors", help="marker anchors CSV (marker_id,x_m,y_m,z_m,yaw_deg)")
    ap.add_argument("--v", type=float, default=0.7)
    ap.add_argument("--dist", type=float, default=3.0)
    ap.add_argument("--expect-scale", type=float, default=1.0, help="speed scale of this floor against calib/motion.json (rugged floor about 0.72)")
    ap.add_argument("--seconds", type=float, help="override the drive time")
    ap.add_argument("--follow", type=int, metavar="ID", help="closed loop: steer by the bearing of this marker (PI, tools.follow_marker) and stop at --stop-m")
    ap.add_argument("--stop-m", type=float, default=0.8, help="--follow: stop when the marker is this far (board distance minus the path length)")
    ap.add_argument("--lost-s", type=float, default=1.2, help="--follow: stop if the marker is not seen for this long")
    ap.add_argument("--max-s", type=float, default=25.0, help="--follow: time limit")
    ap.add_argument("--kp", type=float, default=0.20)
    ap.add_argument("--ki", type=float, default=0.05)
    ap.add_argument("--scales", type=float, nargs="+", default=[1.0, 0.72], help="wheel-model scales to replay")
    ap.add_argument("--wait", type=float, default=60.0)
    ap.add_argument("--min-battery", type=float, default=MIN_BATTERY_V, help="refuse to drive below this pack voltage (the project rule is 11.1 V; the speed model is calibrated at 12.0-12.2 V)")
    ap.add_argument("--ip")
    ap.add_argument("--user", default="jetbot")
    ap.add_argument("--password", default=os.environ.get("JETBOT_PASSWORD"))
    ap.add_argument("--replay-only", action="store_true")
    ap.add_argument("--truncate", type=float, help="the run was aborted: keep only this many seconds after the first command (the robot log shows when the motors stopped)")
    ap.add_argument("--forward", type=float)
    ap.add_argument("--lateral", type=float)
    ap.add_argument("--heading", type=float)
    a = ap.parse_args()
    out = Path("data/dr_path") / a.label
    if a.replay_only:
        cmds, frames = load_run(out)
        volts = seconds = None
    else:
        cmds, frames, volts, seconds = drive(a, out)
    if a.truncate:
        t0 = cmds[0][0]
        cmds = [c for c in cmds if c[0] - t0 <= a.truncate]
        frames = [f for f in frames if f[0] - t0 <= a.truncate]
    fwd = a.forward if a.forward is not None else float(input("true end, forward from the start cross (m): "))
    lat = a.lateral if a.lateral is not None else float(input("true end, left of the string (m, left +): "))
    hd = a.heading if a.heading is not None else float(input("true heading (deg, left +): "))
    rows = []
    for scale in a.scales:
        for correct in (False, True):
            x, y, th, n = replay(cmds, frames, a.anchors, scale, correct)
            rows.append(dict(scale=scale, correction=correct, x=round(x, 3), y=round(y, 3), heading_deg=round(th, 1), corrections=n,
                             error_m=round(end_error_m((x, y), (fwd, lat)), 3)))
            print("scale %.2f  %-18s  est (%.2f, %.2f) %.0f deg  error %.1f cm  (%d marker corrections)" % (
                scale, "with correction" if correct else "no correction", x, y, th, rows[-1]["error_m"] * 100, n))
    (out / "summary.json").write_text(json.dumps(dict(
        label=a.label, v=a.v, seconds=seconds, truncated_to_s=a.truncate, battery_v=volts, frames=len(frames), commands=len(cmds), true_end=dict(forward=fwd, lateral=lat, heading_deg=hd),
        anchors=a.anchors, results=rows, acceptance="<= 0.15 m with correction, <= 0.40 m without"), indent=2))


if __name__ == "__main__":
    main()
