"""Driven range test of the 50 mm tower markers (ids 10-13): at what distance does the robot first see the tower, and how far can it back off before it loses it?

  python -m tools.tower_marker_trial approach 1.8 --yaw 0 --label tower_a     # tape 1.8 m from the lens to the tower, marker NOT seen yet: drives forward, stops after 3 frames with a tower marker
  python -m tools.tower_marker_trial reverse 0.5 --yaw 0 --label tower_a      # tape 0.5 m, marker seen: drives BACKWARD (blind, clear 1.5 m behind it), stops 0.3 s after the last frame with a marker

  python -m tools.tower_marker_trial avoid 1.9 --label avoid_a               # tape 1.9 m, tower NOT seen yet: drives forward and runs sentry.nav.tower_avoid (turn 90 deg away, 0.8 m sideways, turn back, straight on until clear)
                                                                              # then stops; tape the lens -> tower distance and the sideways offset after the run (--turn-scale / --drive-scale correct the open-loop turns and the 0.8 m)

SEQUENCE as tools.speed_trial: start check -> 3 beeps -> HOLD R1 (the tool polls the robot's e-stop latch, starts after R1 held 0.5 s) -> drive -> stop -> 2 short beeps (then release R1) -> type the tape distance
from the lens to the tower (Enter to skip). Armed e-stop and R1 are the real safety stop: this tool's stop adds the 30 Hz loop and the video delay (p95 128 ms on 11-12 = about 2.5 cm at v 0.5).
HARD LIMIT: the drive time is capped so that the robot cannot get closer than --floor-m (0.40 m) in approach mode (modelled speed from calib/motion.json, +15 %), or go further than --back-m (1.5 m) from the start in reverse mode.
Wheels on the floor, ~2 m of clear floor along the path, operator next to the robot. Never --no-estop.
OUTPUT: data/tower_runs/<label>_<mode>_<n>.csv per frame (t, seen, id, range_m, bearing_deg, side_px, cmd_v) and a row in data/tower_runs/summary.csv. The range is the PnP range with --marker-m (0.05):
at 24 px the corner noise alone is a few percent, so compare with the tape at the stop point rather than trusting it to the centimetre.
"""
import argparse
import atexit
import csv
import json
import math
import os
import threading
import time

import cv2
import dataclasses
import numpy as np

from sentry.config import load
from sentry.nav.tower_avoid import TowerAvoid, TowerAvoidConfig
from sentry.net.udp_tx import UDPSender
from sentry.net.zmq_rx import ZMQReceiver
from sentry.perception.camera import CameraGeometry
from sentry.perception.camera_pose import detect_corners
from tools import jetbot_ssh
from tools.calibrate_motion import LOG, _sh, moving_seconds
from tools.jetbot_status import ina219_bus_volts
from tools.speed_trial import ESTOP_LATCH, beep, marker_range

TOWER_IDS = (10, 11, 12, 13)


def look(g, obj, raw):
    """-> (id, range_m, bearing_deg, side_px) of the first tower marker in the frame, or None."""
    found = [m for m in detect_corners(raw) if m[0] in TOWER_IDS][:1]
    mr = marker_range(g, obj, raw, found) if found else None
    if mr is None:
        return None
    c = found[0][1]
    return found[0][0], mr[0], mr[1], float(np.mean([np.linalg.norm(c[i] - c[(i + 1) % 4]) for i in range(4)]))


def drive_seconds(travel_m, v, gain, margin=1.15):
    """Longest drive time (s) that keeps the robot inside `travel_m`, with the modelled speed `margin` times too low (the robot was 20 % SLOWER than the model on 11-18, so 1.0 is still a cap, not a target)."""
    return max(0.0, travel_m) / (gain * abs(v) * margin)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("approach", "reverse", "avoid"))
    ap.add_argument("start_m", type=float, help="tape distance lens -> tower at the start (m)")
    ap.add_argument("--v", type=float, default=0.5, help="command size (0.4 is the dead-zone limit); the sign is set by the mode")
    ap.add_argument("--yaw", type=float, default=0.0, help="how far the tower face is turned away from facing the robot (deg), for the record")
    ap.add_argument("--marker-m", type=float, default=0.05)
    ap.add_argument("--label", default="tower")
    ap.add_argument("--confirm", type=int, default=3, help="approach: consecutive frames with a tower marker before the stop")
    ap.add_argument("--lost-s", type=float, default=0.3, help="reverse: seconds without a tower marker before the stop")
    ap.add_argument("--floor-m", type=float, default=0.40, help="approach: closest the robot may get, whatever it sees")
    ap.add_argument("--back-m", type=float, default=1.5, help="reverse: furthest the robot may travel")
    ap.add_argument("--turn-scale", type=float, default=None, help="avoid: angle turned / angle asked (default [tower] turn_scale)")
    ap.add_argument("--drive-scale", type=float, default=None, help="avoid: distance driven / distance asked (default [tower] drive_scale)")
    ap.add_argument("--max-total-s", type=float, default=30.0, help="avoid: the whole run, manoeuvre included")
    ap.add_argument("--wait", type=float, default=20.0)
    ap.add_argument("--ip", default="auto")
    ap.add_argument("--user", default="jetbot")
    ap.add_argument("--password", default=os.environ.get("JETBOT_PASSWORD"))
    ap.add_argument("--camera", default="calib/camera.json")
    ap.add_argument("--pose", default="calib/camera_pose_nowedge.json", help="only K and D are used here")
    ap.add_argument("--out", default="data/tower_runs")
    a = ap.parse_args()
    if not 0.4 <= a.v <= 1 or not 0.2 <= a.start_m <= 3.0:
        ap.error("v in [0.4, 1], start_m in [0.2, 3.0]")
    fwd = a.mode in ("approach", "avoid")                  # drives forward at the tower; the others back away
    if fwd and a.start_m <= a.floor_m + 0.1:
        ap.error("%s needs start_m > floor_m + 0.1" % a.mode)
    gain = json.load(open("calib/motion.json"))["v_gain_m_per_s"]
    travel = a.start_m - a.floor_m if fwd else a.back_m
    max_s = drive_seconds(travel, a.v, gain, 1.0 if a.mode == "avoid" else 1.15)
    sign = 1.0 if fwd else -1.0
    cfg = TowerAvoidConfig.from_toml()
    cfg = dataclasses.replace(cfg, **{k: v for k, v in (("turn_scale", a.turn_scale), ("drive_scale", a.drive_scale), ("drive_v", a.v)) if v is not None})
    ta = TowerAvoid(cfg)
    from sentry.net.discover import resolve
    a.ip = resolve(a.ip)
    password = jetbot_ssh.password(a.password)
    S = a.marker_m / 2
    obj = np.array([[-S, S, 0], [S, S, 0], [S, -S, 0], [-S, -S, 0]], np.float64)
    g = CameraGeometry.from_files(a.camera, a.pose)
    c = jetbot_ssh.connect(a.ip, a.user, password)
    before = int(_sh(c, "wc -l < %s" % LOG).strip() or 0)
    cmd = {"v": 0.0, "w": 0.0}
    done = threading.Event()

    def sender():
        s = UDPSender(a.ip, load()["net"]["control_port"], 30)
        try:
            while not done.is_set():
                s.send(cmd["v"], cmd["w"])
                time.sleep(s.period_s)
        finally:
            s.close(stop=True)

    th = threading.Thread(target=sender, daemon=True)
    th.start()
    atexit.register(lambda: (cmd.update(v=0.0, w=0.0), done.set()))
    rows, why, event, t_cmd0, t_cmd1, streak, last_seen = [], "time cap", None, None, None, [], None
    try:
        def stop(reason):
            nonlocal why, t_cmd1
            cmd["v"] = cmd["w"] = 0.0
            t_cmd1 = t_cmd1 or time.time()
            why = reason

        with ZMQReceiver() as rx:
            first, start_img = None, None
            for _ in range(30):
                f = rx.read(timeout=5)
                first = look(g, obj, f.frame_bgr) if f is not None else None
                if f is not None:
                    start_img = f.frame_bgr
                if first or fwd and _ >= 10:
                    break
            if a.mode == "reverse" and first is None:
                done.set(); th.join()
                raise SystemExit("ABORT: reverse needs a tower marker in view at the start")
            if fwd and first is not None and not (a.mode == "avoid" and first[1] > cfg.trigger_m + 0.1):
                done.set(); th.join()
                raise SystemExit("ABORT: a tower marker is already seen at %.2f m (PnP); start further away" % first[1])
            os.makedirs(a.out, exist_ok=True)
            snap = os.path.join(a.out, "%s_%s_%s_start.jpg" % (a.label, a.mode, time.strftime("%H%M%S")))
            cv2.imwrite(snap, start_img)                         # what the camera saw at the start: check that the tower is in it
            print("start picture:", snap, flush=True)
            print("%s: tape %.2f m, drive time cap %.1f s (model %.3f m/s per unit x %.2f). HOLD R1 at the beeps." % (a.mode, a.start_m, max_s, gain, a.v), flush=True)
            for _ in range(3):
                beep(1500, 300)
            t0 = time.time()
            t_wait_end, t_go, r1_since, last_poll = t0 + a.wait, None, None, 0.0
            while True:
                now = time.time()
                if t_go is None and now - last_poll >= 0.25:
                    last_poll = now
                    held = _sh(c, "test -e %s && echo no || echo yes" % ESTOP_LATCH).strip() == "yes"
                    r1_since = (r1_since or now) if held else None
                    if r1_since and now - r1_since >= 0.5:
                        t_go = now
                        print("R1 held: driving", flush=True)
                    elif now > t_wait_end:
                        done.set(); th.join()
                        raise SystemExit("ABORT: R1 not held (and the e-stop armed) within %.0f s" % a.wait)
                if t_cmd0 is None and t_go is not None:
                    cmd["v"] = sign * a.v
                    t_cmd0 = now
                if t_cmd0 is not None and t_cmd1 is None:
                    if a.mode != "avoid" and now - t_cmd0 >= max_s:
                        stop("time cap")
                    elif a.mode == "avoid" and not (ta.active or ta.count) and now - t_cmd0 >= max_s:
                        stop("time cap: no tower marker inside %.2f m before the robot got to %.2f m" % (cfg.trigger_m, a.floor_m))
                    elif a.mode == "avoid" and now - t_cmd0 >= a.max_total_s:
                        stop("total time cap")
                if t_cmd1 is not None and now - t_cmd1 > 1.5:
                    break
                f = rx.read(timeout=5)
                if f is None:
                    stop("no frames")
                    break
                r = look(g, obj, f.frame_bgr)
                now = time.time()
                rows.append((now - t0, int(r is not None), r[0] if r else "", "%.4f" % r[1] if r else "", "%.2f" % r[2] if r else "", "%.1f" % r[3] if r else "", cmd["v"], cmd["w"], ta.phase))
                if t_cmd0 is None or t_cmd1 is not None:
                    continue
                if a.mode == "avoid":
                    out = ta.step(now, (r[1], r[2]) if r else None)
                    if out is not None:
                        cmd.update(v=out[0], w=out[1])
                        if out[2] == "ABORT":
                            stop("avoid aborted: %s" % ta.events[-1]["why"])
                    elif ta.count or ta.aborted:
                        stop("avoid done")
                    else:
                        cmd.update(v=a.v, w=0.0)
                        if r and r[1] < a.floor_m:
                            stop("marker closer than %.2f m before the avoid started" % a.floor_m)
                    continue
                if r:
                    last_seen = (now, r)
                if a.mode == "approach":
                    streak = streak + [r] if r else []
                    if len(streak) >= a.confirm:
                        event = streak[0]
                        stop("tower marker seen %d frames in a row" % a.confirm)
                    elif r and r[1] < a.floor_m:
                        stop("marker closer than %.2f m" % a.floor_m)
                elif last_seen and now - last_seen[0] > a.lost_s:
                    event = last_seen[1]
                    stop("marker lost for %.1f s" % a.lost_s)
    finally:
        cmd.update(v=0.0, w=0.0)
        done.set()
        th.join(timeout=2.0)
    time.sleep(0.6)
    moving = moving_seconds(_sh(c, "tail -n +%d %s" % (before + 1, LOG)).splitlines())
    volts = ina219_bus_volts(jetbot_ssh.sudo(c, "i2cget -y 1 0x41 0x02 w", password))
    beep(1000, 300); beep(1000, 300)
    print("ENDED by: %s | wheels turned %.2f s | battery %.2f V | %d frames" % (why, moving, volts, len(rows)))
    for e in ta.events:
        print("  avoid:", e)
    if event:
        print("EVENT: tower id %d at PnP range %.3f m, bearing %+.1f deg, side %.0f px (%s)" % (event[0], event[1], event[2], event[3], "first detection" if a.mode == "approach" else "last detection"))
    else:
        print("NO EVENT (no tower marker confirmed / lost): the marker was not detected in range, or the time cap ended the run")
    try:
        tape_end = input("Tape lens -> tower now, m (Enter to skip): ").strip()
    except EOFError:                                     # no console (launched from a script): fill the summary row by hand
        tape_end = ""
    os.makedirs(a.out, exist_ok=True)
    n = 1 + len([x for x in os.listdir(a.out) if x.startswith("%s_%s_" % (a.label, a.mode))])
    path = os.path.join(a.out, "%s_%s_%d.csv" % (a.label, a.mode, n))
    with open(path, "w", newline="") as fh:
        csv.writer(fh).writerows([("t", "seen", "id", "range_m", "bearing_deg", "side_px", "cmd_v", "cmd_w", "phase")] + [(("%.3f" % r[0]),) + r[1:] for r in rows])
    summ = os.path.join(a.out, "summary.csv")
    new = not os.path.exists(summ)
    with open(summ, "a", newline="") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["label", "mode", "yaw_deg", "v", "marker_m", "start_tape_m", "end_tape_m", "event_id", "event_range_m", "event_side_px", "why", "wheel_s", "battery_v", "csv"])
        w.writerow([a.label, a.mode, a.yaw, a.v, a.marker_m, a.start_m, tape_end, event[0] if event else "", "%.3f" % event[1] if event else "", "%.0f" % event[3] if event else "", why, "%.2f" % moving, "%.2f" % volts, path])
    print("saved", path)


if __name__ == "__main__":
    main()
