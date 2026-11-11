"""Find the door on the robot's own, in ONE run (arm the e-stop and hold R1 once): spin scan -> turn (right by default, --side left) and drive a baseline -> spin scan -> triangulate (tools.locate_door).

  python -m tools.find_door --label fd --camera-pose calib/camera_pose_self_<today>.json --entrance data/entrance/class_door [--dry-run]

The door detector gives a BEARING only. The robot spins a full circle (boards = ArUco, door via the entrance detector), turns by --turn-deg, drives about --baseline-s seconds
(open loop: it veers, which does not matter because the boards give the pose), spins a second circle, and the two door bearings are intersected in the first scan's frame. The boards seen in both
circles give where it stands; at least 2 are needed. Output data/find_door/<label>_<n>/result.json (door in the first frame and in the final frame, range spread, sweet spot) and the two scan summaries.
SAFETY: R1 + armed e-stop (hold Start 1.5 s); the robot only turns in place and drives forward at --drive-v; the drive stops when a board straight ahead is closer than --stop-range, R1 is released, the
time is up or a frame is missing for 0.5 s. Keep 0.3 m clear around it and 1.5 m ahead in the turned direction. --dry-run: one stop, no commands.
Needs the boards (ArUco) around the robot, the same ones as tools.scan_boards."""
import argparse
import json
import math
import os
import threading
import time
from pathlib import Path

import numpy as np

from tools.locate_door import locate
from tools.scan_boards import ESTOP_LATCH, MIN_BATTERY_V, PRIOR_PULSE_RAD, SPIN_W, camera_to_robot, pulse_angle, to_start_frame, wrap


def dominant_bearing(doors, window_deg=10.0):
    """doors: [(absolute angle rad in the scan's start frame, inliers)]. The detector also fires at wrong places, so the median of all sightings is meaningless: take the window of +/- window_deg
    holding the most sightings (ties: most inliers) and return (median angle deg of that window, sightings in it, all sightings, second-best window's count)."""
    if not doors:
        return None, 0, 0, 0
    a = [math.degrees(d[0]) for d in doors]

    def inside(c):
        return [i for i, x in enumerate(a) if abs((x - c + 180) % 360 - 180) <= window_deg]
    ranked = sorted(((len(inside(c)), sum(doors[i][1] for i in inside(c)), c) for c in a), reverse=True)
    n, _, c = ranked[0]
    idx = inside(c)
    ref = a[idx[0]]
    med = ref + float(np.median([(a[i] - ref + 180) % 360 - 180 for i in idx]))
    other = [r for r in ranked if abs((r[2] - c + 180) % 360 - 180) > 2 * window_deg]
    return round(((med + 180) % 360) - 180, 1), n, len(a), (other[0][0] if other else 0)


def summarise(boards, doors):
    """-> scan_boards-style summary dict (medians per board in the scan's start frame, door bearing = the dominant cluster of sightings, raw sightings kept)."""
    bearing, n, total, second = dominant_bearing(doors)
    return dict(boards={str(m): dict(x_m=float(np.median([p[0] for p in v])), y_m=float(np.median([p[1] for p in v])), stops=len(v)) for m, v in boards.items()},
                door_bearing_deg=bearing, door_sightings=total, door_cluster_sightings=n, door_second_cluster_sightings=second,
                door_sightings_raw=[[round(math.degrees(d[0]), 1), int(d[1])] for d in doors])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--label", required=True)
    ap.add_argument("--camera-pose", required=True)
    ap.add_argument("--entrance", required=True, help="folder from tools.enroll_entrance (the door's reference views)")
    ap.add_argument("--ip", default="auto")
    ap.add_argument("--user", default="jetbot")
    ap.add_argument("--password", default=os.environ.get("JETBOT_PASSWORD"))
    ap.add_argument("--turn-deg", type=float, default=90.0, help="turn before the baseline drive")
    ap.add_argument("--side", choices=("right", "left"), default="right", help="which way to turn (and so drive the baseline)")
    ap.add_argument("--baseline-s", type=float, default=5.5, help="forward drive time (about 0.22 m/s at v 0.55 on 2026-11-11: 5.5 s = 1.2 m)")
    ap.add_argument("--drive-v", type=float, default=0.55)
    ap.add_argument("--stop-range", type=float, default=0.8, help="stop driving when a board within 30 deg of straight ahead is closer than this (m)")
    ap.add_argument("--stand-off", type=float, default=2.0, help="sweet spot: this far from the door (m), inside the 1.5-3.0 m window")
    ap.add_argument("--max-pulses", type=int, default=18)
    ap.add_argument("--spin-s", type=float, default=0.2)
    ap.add_argument("--hold", type=float, default=1.0)
    ap.add_argument("--samples", type=int, default=6)
    ap.add_argument("--wait", type=float, default=90.0)
    ap.add_argument("--min-battery", type=float, default=MIN_BATTERY_V)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", default="data/find_door")
    a = ap.parse_args()
    if not (0 < a.spin_s <= 0.5 and 0 < a.hold <= 5 and 0 <= a.turn_deg <= 180 and 0 < a.baseline_s <= 10 and 0.3 <= a.drive_v <= 0.8 and 1.5 <= a.stand_off <= 3.0):
        raise SystemExit("ABORT: argument out of its safe range")

    from sentry.config import load
    from sentry.nav.localization import LocalizationTracker
    from sentry.net.discover import resolve
    from sentry.net.udp_tx import UDPSender
    from sentry.net.zmq_rx import ZMQReceiver
    from sentry.perception.entrance import Camera, EntranceDetector
    from tools import jetbot_ssh
    from tools.calibrate_motion import _sh
    from tools.jetbot_status import ina219_bus_volts
    import winsound

    pitch = math.radians(json.load(open(a.camera_pose))["pitch_down_deg"])
    tr = LocalizationTracker(motion_calib=None, camera_calib="calib/camera.json", max_marker_distance_m=1e6)
    entrance = EntranceDetector.load(a.entrance, camera=Camera.from_json("calib/camera.json"))
    a.ip = resolve(a.ip)
    password = jetbot_ssh.password(a.password)
    link = {"ssh": jetbot_ssh.connect(a.ip, a.user, password)}
    volts0 = ina219_bus_volts(jetbot_ssh.sudo(link["ssh"], "i2cget -y 1 0x41 0x02 w", password))
    print("battery %.2f V" % volts0, flush=True)
    if volts0 < a.min_battery:
        raise SystemExit("ABORT: battery %.2f V < %.1f V: charge first" % (volts0, a.min_battery))
    port = load()["net"]["control_port"]
    rx = ZMQReceiver(ip=a.ip)
    rx.start()
    sender = None

    def r1_held():
        for attempt in (0, 1):
            try:
                return _sh(link["ssh"], "test -e %s && echo no || echo yes" % ESTOP_LATCH).strip() == "yes"
            except Exception:
                if attempt == 1:
                    raise
                link["ssh"] = jetbot_ssh.connect(a.ip, a.user, password)

    def sample():
        """-> ({marker: (bearing, range, fwd, left, n)}, [(door bearing, inliers)]) medians over a few frames."""
        per, door, n, t0 = {}, [], 0, time.time()
        while n < a.samples and time.time() - t0 < 6.0:
            f = rx.read(timeout=0.5)
            if f is None:
                continue
            n += 1
            for d in tr.detect_markers(f.frame_bgr):
                fwd, left = camera_to_robot(d.tvec, pitch)
                per.setdefault(d.marker_id, []).append((d.bearing_rad, d.distance_m, fwd, left))
            r = entrance(f.frame_bgr, 0.0)
            if r.in_view and r.bearing_rad is not None:
                door.append((r.bearing_rad, r.inliers))
        return {m: tuple(float(np.median([v[i] for v in vs])) for i in range(4)) + (len(vs),) for m, vs in per.items()}, door

    def command(v, w, seconds):
        t_end = time.time() + seconds
        while time.time() < t_end:
            sender.send(v, w)
            time.sleep(1 / 30.0)
        sender.send(0.0, 0.0)

    def pulse(w, prev, seen, pulses):
        ang, nb = pulse_angle({m: x[:2] for m, x in prev.items()}, {m: x[:2] for m, x in seen.items()})
        if ang is None:
            good = [p[0] for p in pulses if p[1] > 0 and np.sign(p[0]) == np.sign(w)]
            ang = float(np.median(good)) if good else math.copysign(PRIOR_PULSE_RAD, w)
            nb = 0
        pulses.append((ang, nb))
        return ang

    def spin_scan(tag):
        """Full left circle from the current heading. -> (boards in this scan's start frame, doors [(heading + bearing, inliers)], pulses)."""
        boards, doors, pulses, heading, prev = {}, [], [], 0.0, None
        for k in range(a.max_pulses + 1):
            if not a.dry_run and not r1_held():
                raise SystemExit("STOP: R1 released during %s" % tag)
            seen, door = sample()
            if prev is not None:
                heading += pulse(SPIN_W, prev, seen, pulses)
            for m, v in seen.items():
                boards.setdefault(m, []).append(to_start_frame(v[2], v[3], heading) + (v[1],))
            doors.extend((heading + b, inl) for b, inl in door)
            print("%s stop %2d heading %6.1f deg | boards %s | door %s" % (tag, k, math.degrees(heading), {m: round(v[1], 2) for m, v in sorted(seen.items())}, "in view" if door else "-"), flush=True)
            prev = seen
            if a.dry_run or math.degrees(heading) >= 355 or k == a.max_pulses:
                break
            command(0.0, SPIN_W, a.spin_s)
            time.sleep(a.hold)
        return boards, doors, pulses

    def turn_side(deg, sign):
        """Turn by `deg` degrees, left (sign +1) or right (-1), in spin pulses; the angle of each pulse is measured from the boards."""
        turned, prev, pulses = 0.0, sample()[0], []
        for _ in range(8):
            if abs(turned) >= math.radians(deg) - 0.5 * PRIOR_PULSE_RAD or not r1_held():
                break
            command(0.0, sign * SPIN_W, a.spin_s)
            time.sleep(a.hold)
            seen = sample()[0]
            turned += pulse(sign * SPIN_W, prev, seen, pulses)
            prev = seen
            print("turn %s: %.0f deg so far" % (a.side, math.degrees(abs(turned))), flush=True)

    def drive():
        """Forward for baseline_s: the command is streamed at 30 Hz by its own thread (a check loop with an SSH call per round took ~1.7 s, so inline commands gave 0.3 s of motion per 1.7 s);
        this loop only watches R1, the frames and the boards ahead and stops the thread. The robot's own e-stop cuts the motors the moment R1 is released."""
        stop = threading.Event()

        def pump():
            while not stop.is_set():
                sender.send(a.drive_v, 0.0)
                time.sleep(1 / 30.0)
        th = threading.Thread(target=pump, daemon=True)
        t0 = time.time()
        th.start()
        try:
            while time.time() - t0 < a.baseline_s:
                if not r1_held():
                    print("drive: R1 released", flush=True)
                    break
                f = rx.read(timeout=0.5)
                if f is None:                                              # rx.read waited 0.5 s without a frame
                    print("drive: no frame, stopping", flush=True)
                    break
                ahead = [d.distance_m for d in tr.detect_markers(f.frame_bgr) if abs(d.bearing_rad) < math.radians(30)]
                if ahead and min(ahead) < a.stop_range:
                    print("drive: a board %.2f m ahead, stopping" % min(ahead), flush=True)
                    break
        finally:
            stop.set()
            th.join()
            sender.send(0.0, 0.0)
        print("drive: %.1f s of forward command" % (time.time() - t0), flush=True)

    result, run_dir = {}, None
    try:
        if not a.dry_run:
            print("ARM the e-stop (hold Start 1.5 s) and HOLD R1 within %.0f s and keep holding it for the whole run (about 2 minutes); keep 0.3 m clear around the robot." % a.wait, flush=True)
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
            sender = UDPSender(a.ip, port, 30)
        b1, d1, p1 = spin_scan("scan 1")
        s1 = summarise(b1, d1)
        result["scan1"] = s1
        if a.dry_run:
            print(json.dumps(s1, indent=1))
            return
        if s1["door_bearing_deg"] is None:
            raise SystemExit("STOP: the door was not seen in scan 1 (door_sightings 0): nothing to triangulate")
        turn_side(a.turn_deg, 1 if a.side == "left" else -1)
        drive()
        time.sleep(1.5)
        b2, d2, p2 = spin_scan("scan 2")
        s2 = summarise(b2, d2)
        result["scan2"] = s2
        if s2["door_bearing_deg"] is None:
            raise SystemExit("STOP: the door was not seen in scan 2")
        res = locate(s1, s2, stand_off_m=a.stand_off)
        res["range_reliable"] = bool(res["baseline_m"] >= 0.5 and res["ray_angle_deg"] >= 8.0)
        if not res["range_reliable"]:
            print("WARNING: baseline %.2f m / ray angle %.1f deg: too small, the range is NOT reliable (the drive probably did not happen)" % (res["baseline_m"], res["ray_angle_deg"]), flush=True)
        res["turn_per_pulse_deg"] = [round(math.degrees(float(np.median([p[0] for p in ps if p[1] > 0]))), 1) if any(p[1] > 0 for p in ps) else None for ps in (p1, p2)]
        result["located"] = res
        print(json.dumps(res, indent=1))
    finally:
        try:
            if sender is not None:
                sender.send(0.0, 0.0)
                sender.close(stop=True)
        except Exception:
            pass
        try:
            rx.close()
        except Exception:
            pass
        if result and not a.dry_run:
            out = Path(a.out)
            n = 1
            while True:
                run_dir = out / ("%s_%d" % (a.label, n))
                try:
                    run_dir.mkdir(parents=True, exist_ok=False)
                    break
                except FileExistsError:
                    n += 1
            (run_dir / "result.json").write_text(json.dumps(dict(result, camera_pose_file=a.camera_pose, battery_v_start=volts0, date=time.strftime("%Y-%m-%d %H:%M")), indent=1, allow_nan=False))
            print("saved", run_dir)


if __name__ == "__main__":
    main()
