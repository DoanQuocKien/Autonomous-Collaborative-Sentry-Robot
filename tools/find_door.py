"""Find the door on the robot's own, in ONE run (arm the e-stop and hold R1 once): spin scan -> turn (right by default, --side left) and drive a baseline -> spin scan -> triangulate (tools.locate_door).

  python -m tools.find_door --label fd --camera-pose calib/camera_pose_self_<today>.json --entrance data/entrance/class_door [--dry-run]

The door detector gives a BEARING only. The robot spins a full circle (boards = ArUco, door via the entrance detector), turns by --turn-deg, drives about --baseline-s seconds
(open loop: it veers, which does not matter because the boards give the pose), spins a second circle, and the two door bearings are intersected in the first scan's frame. The boards seen in both
circles give where it stands; at least 2 are needed. Output data/find_door/<label>_<n>/result.json (door in the first frame and in the final frame, range spread, sweet spot and the two scan summaries; "located" = the on-line
running-sum estimate, "located_joint" = tools.door_pose with a 5-95 % range interval) and observations.json (every stop's raw board and door observations, every pulse: replay it with
python -m tools.door_pose <that file>).
SAFETY: R1 + armed e-stop (hold Start 1.5 s); the robot only turns in place and drives forward at --drive-v; the drive stops when a board straight ahead is closer than --stop-range, R1 is released, the
time is up or a frame is missing for 0.5 s. Keep 0.3 m clear around it and 1.5 m ahead in the turned direction. --dry-run: one stop, no commands.
Needs the boards (ArUco) around the robot, the same ones as tools.scan_boards."""
import argparse
import json
import math
import os
import subprocess
import threading
import time
from pathlib import Path

import numpy as np

from tools.approach_door import MAX_VIDEO_AGE_S, video_is_fresh
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


def baseline_turn_deg(door_deg, heading_deg, side):
    """Signed turn (left positive, degrees, shortest way) that points the robot ACROSS the line of sight to the door: facing the door, `side` is the direction of the baseline
    ('left' -> heading = door bearing + 90, 'right' -> - 90). door_deg and heading_deg are in the first scan's start frame (the heading is where the robot stands after the scan)."""
    target = door_deg + (90.0 if side == "left" else -90.0)
    return (target - heading_deg + 180.0) % 360.0 - 180.0


DRIVE_SPEED_M_S = 0.35                                  # worst case seen at v 0.85 on the classroom tile: 0.34 m/s on 2026-11-12 (1.9 m in 5.6 s, battery 11.64 V); 0.21 m/s in an earlier run (0.75 m in 3.5 s): the speed varies with battery and floor
CLEAR_MARGIN_M = 0.6                                    # veer arc (up to 25 deg/m), the robot's own size and the stopping distance


def required_clear_radius_m(baseline_s):
    """Clear floor the operator must have around the robot in EVERY direction for a drive of baseline_s seconds (the direction is chosen by the robot after scan 1)."""
    return baseline_s * DRIVE_SPEED_M_S + CLEAR_MARGIN_M


def max_baseline_s(clear_radius_m):
    """Longest drive time that fits in a measured clear radius (0 when even a standing start does not fit)."""
    return max(0.0, (clear_radius_m - CLEAR_MARGIN_M) / DRIVE_SPEED_M_S)


def door_vs_drive_deg(door_deg, heading_deg, turn_signed_deg):
    """Angle (degrees, -180..180) between the direction to the door and the direction the robot will drive, both in scan 1's start frame (left positive). Near 0 or +/-180 the drive is along the line of
    sight (a useless baseline: the two door rays are nearly parallel); +/-90 is ideal."""
    return (door_deg - (heading_deg + turn_signed_deg) + 180.0) % 360.0 - 180.0


def summarise(boards, doors):
    """-> scan_boards-style summary dict (medians per board in the scan's start frame, door bearing = the dominant cluster of sightings, raw sightings kept)."""
    bearing, n, total, second = dominant_bearing(doors)
    return dict(boards={str(m): dict(x_m=float(np.median([p[0] for p in v])), y_m=float(np.median([p[1] for p in v])), stops=len(v)) for m, v in boards.items()},
                door_bearing_deg=bearing, door_sightings=total, door_cluster_sightings=n, door_second_cluster_sightings=second,
                door_sightings_raw=[[round(math.degrees(d[0]), 1), int(d[1])] for d in doors])


def unreliable_text(res):
    """What is wrong when the on-line range is not reliable (res: tools.locate_door.locate output): the fitted geometry, not a guess about the drive."""
    why = []
    if res["baseline_m"] < 0.5:
        why.append("the fitted baseline between the two scan spots is %.2f m (< 0.5 m)" % res["baseline_m"])
    if res["ray_angle_deg"] < 8.0:
        why.append("the two door rays differ by only %.1f deg (< 8 deg)" % res["ray_angle_deg"])
    return ("WARNING: the range is NOT reliable: %s. The rays are nearly parallel, so 1-2 deg of bearing or heading error moves the range a lot. Both numbers come from the board fit "
            "(rms %.2f m on boards %s): a short drive, a drive along the line of sight or heading error in a scan all give this; see located_joint and observations.json."
            % (" and ".join(why), res["board_fit_rms_m"], ",".join(res["boards_used"])))


def measured_pulse(w, prev, seen, pulses):
    """Angle of the pulse between two stops (rad, the sign of w): from the boards seen at both, else the median of the earlier measured pulses of that sign, else the calibrated prior.
    Appends (angle, boards used) to pulses."""
    ang, nb = pulse_angle({m: x[:2] for m, x in prev.items()}, {m: x[:2] for m, x in seen.items()})
    if ang is None:
        good = [p[0] for p in pulses if p[1] > 0 and np.sign(p[0]) == np.sign(w)]
        ang = float(np.median(good)) if good else math.copysign(PRIOR_PULSE_RAD, w)
        nb = 0
    pulses.append((ang, nb))
    return ang


def new_scan():
    return dict(boards={}, doors=[], pulses=[], heading=0.0, prev=None, record=dict(stops=[], pulses=[]))


def add_stop(scan, seen, door, w=SPIN_W, spin_s=None):
    """Fold one stop into a scan (pure: no hardware). seen: {marker: (bearing rad, range m, fwd m, left m, frames)}, door: [(bearing rad, inliers)] of this stop's frames.
    Updates the running-sum heading and the start-frame board positions (the on-line estimate) and scan['record'], everything tools.door_pose needs to re-estimate off-line:
    per stop the raw board and door observations (angles in degrees) with the running-sum heading, per pulse the command and the measured angle (boards = 0: not measured, filled in).
    -> the heading (rad) at this stop."""
    k = len(scan["record"]["stops"])
    if scan["prev"] is not None:
        ang = measured_pulse(w, scan["prev"], seen, scan["pulses"])
        scan["heading"] += ang
        scan["record"]["pulses"].append(dict(cmd_w=w, cmd_s=spin_s, measured_deg=round(math.degrees(ang), 2), boards=scan["pulses"][-1][1]))
    h = scan["heading"]
    for m, v in seen.items():
        scan["boards"].setdefault(m, []).append(to_start_frame(v[2], v[3], h) + (v[1],))
    scan["doors"].extend((h + b, inl) for b, inl in door)
    scan["record"]["stops"].append(dict(stop=k, heading_deg=round(math.degrees(h), 2),
                                        boards=[[int(m), round(math.degrees(v[0]), 2), round(v[1], 3), round(v[2], 3), round(v[3], 3), int(v[4])] for m, v in sorted(seen.items())],
                                        door=[[round(math.degrees(b), 2), int(inl)] for b, inl in door]))
    scan["prev"] = seen
    return h


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--label", required=True)
    ap.add_argument("--camera-pose", required=True)
    ap.add_argument("--entrance", required=True, help="folder from tools.enroll_entrance (the door's reference views)")
    ap.add_argument("--ip", default="auto")
    ap.add_argument("--user", default="jetbot")
    ap.add_argument("--password", default=os.environ.get("JETBOT_PASSWORD"))
    ap.add_argument("--side", choices=("right", "left"), default="right", help="baseline direction ACROSS the line of sight, as seen when facing the door: the robot turns to it (shortest way) and drives")
    ap.add_argument("--turn-deg", type=float, default=None, help="override: turn by this many degrees (side decides left or right) instead of computing the turn from the door bearing")
    ap.add_argument("--preview-s", type=float, default=4.0, help="after scan 1 the plan (turn and drive) is spoken and the robot waits this long with the motors off: release R1 to abort (0 = no pause)")
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
    ap.add_argument("--clear-ahead-m", type=float, default=None, help="with --turn-deg (the drive direction is known to you): MEASURED clear floor along that direction (m); needs baseline_s x 0.21 + 0.6 m. --clear-radius-m is then only the spin clearance (at least 0.5 m)")
    ap.add_argument("--clear-radius-m", type=float, default=None, help="MEASURED clear floor around the robot in every direction (m), required for a live run: the drive needs baseline_s x 0.21 + 0.6 m (the obstacle check only sees boards straight ahead)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", default="data/find_door")
    a = ap.parse_args()
    if not a.dry_run:
        if a.turn_deg is not None:                         # the drive direction is chosen by the operator: the room it needs is AHEAD along that direction, the spin needs 0.5 m around
            if a.clear_ahead_m is None or a.clear_radius_m is None:
                raise SystemExit("ABORT: with --turn-deg give both --clear-radius-m (MEASURED clear floor around the robot for the spin, at least 0.5 m) and --clear-ahead-m (MEASURED clear floor along the drive direction, needs %.1f m for %.1f s)" % (required_clear_radius_m(a.baseline_s), a.baseline_s))
            if a.clear_radius_m < 0.5 or a.clear_ahead_m < required_clear_radius_m(a.baseline_s):
                raise SystemExit("ABORT: spin clearance %.1f m (needs 0.5 m) and clear ahead %.1f m (a %.1f s drive needs %.1f m; the longest that fits is %.1f s)" % (a.clear_radius_m, a.clear_ahead_m, a.baseline_s, required_clear_radius_m(a.baseline_s), math.floor(max_baseline_s(a.clear_ahead_m) * 10) / 10))
        elif a.clear_radius_m is None:
            raise SystemExit("ABORT: give the MEASURED clear radius around the robot with --clear-radius-m (the drive of %.1f s needs %.1f m in every direction)" % (a.baseline_s, required_clear_radius_m(a.baseline_s)))
        elif a.clear_radius_m < required_clear_radius_m(a.baseline_s):
            raise SystemExit("ABORT: %.1f m of clear floor is not enough for a %.1f s drive (needs %.1f m): use --baseline-s %.1f or less, or find more room" % (a.clear_radius_m, a.baseline_s, required_clear_radius_m(a.baseline_s), math.floor(max_baseline_s(a.clear_radius_m) * 10) / 10))
    if not (0 < a.spin_s <= 0.5 and 0 < a.hold <= 5 and (a.turn_deg is None or 0 <= a.turn_deg <= 180) and 0 < a.baseline_s <= 10 and 0 <= a.preview_s <= 15 and 0.3 <= a.drive_v <= 1.0 and 1.5 <= a.stand_off <= 3.0):
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

    def preview(turn_signed_deg):
        """Say what the robot is about to do and wait a.preview_s with the motors off; releasing R1 in that time aborts the run (the operator cannot see the plan otherwise: the direction is computed from the door bearing after scan 1)."""
        metres = a.baseline_s * DRIVE_SPEED_M_S                      # the worst case speed seen (the real drive can be 40 % shorter)
        if abs(turn_signed_deg) < 1:
            text = "Driving straight ahead about %.1f metres. Release R1 now to stop." % metres
        else:
            text = "Turning %s %d degrees, then driving about %.1f metres. Release R1 now to stop." % ("left" if turn_signed_deg > 0 else "right", round(abs(turn_signed_deg)), metres)
        print("PLAN: " + text, flush=True)
        if a.preview_s <= 0:
            return
        try:
            subprocess.Popen(["powershell", "-NoProfile", "-Command", "Add-Type -AssemblyName System.Speech; $v = New-Object System.Speech.Synthesis.SpeechSynthesizer; $v.Rate = -3; $v.Speak('%s')" % text],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            winsound.Beep(900, 600)                                    # no speech: a long beep announces the pause
        t_end = time.time() + a.preview_s
        while time.time() < t_end:
            if not r1_held():
                raise SystemExit("STOP: R1 released during the preview: nothing moved after scan 1")
            time.sleep(0.3)

    def sample():
        """-> ({marker: (bearing, range, fwd, left, n)}, [(door bearing, inliers)]) medians over a few frames."""
        per, door, n, t0 = {}, [], 0, time.time()
        while n < a.samples and time.time() - t0 < 6.0:
            f = rx.read(timeout=0.5)
            if f is None or not video_is_fresh(f.t_rx, time.perf_counter()):      # no frame, or a stale one (laggy link): not used
                continue
            video["last_rx"] = f.t_rx
            n += 1
            for d in tr.detect_markers(f.frame_bgr):
                fwd, left = camera_to_robot(d.tvec, pitch)
                per.setdefault(d.marker_id, []).append((d.bearing_rad, d.distance_m, fwd, left))
            r = entrance(f.frame_bgr, 0.0)
            if r.in_view and r.bearing_rad is not None:
                door.append((r.bearing_rad, r.inliers))
        if n < a.samples:
            raise SystemExit("STOP: incomplete fresh video sample (%d/%d frames newer than %.1f s): nothing is commanded on old video" % (n, a.samples, MAX_VIDEO_AGE_S))
        return {m: tuple(float(np.median([v[i] for v in vs])) for i in range(4)) + (len(vs),) for m, vs in per.items()}, door

    def command(v, w, seconds):
        f = rx.read(timeout=MAX_VIDEO_AGE_S)                         # liveness: a frame must arrive now (the age of an older frame would include our own processing time)
        if f is None or not video_is_fresh(f.t_rx, time.perf_counter()):
            raise SystemExit("STOP: no fresh robot video within %.1f s before a command: no command sent" % MAX_VIDEO_AGE_S)
        video["last_rx"] = f.t_rx
        t_end = time.time() + seconds
        while time.time() < t_end:
            sender.send(v, w)
            time.sleep(1 / 30.0)
        sender.send(0.0, 0.0)

    def spin_scan(tag):
        """Full left circle from the current heading. -> the scan (see new_scan / add_stop): boards in this scan's start frame, doors [(heading + bearing, inliers)], pulses, heading, record."""
        scan = new_scan()
        for k in range(a.max_pulses + 1):
            if not a.dry_run and not r1_held():
                raise SystemExit("STOP: R1 released during %s" % tag)
            seen, door = sample()
            heading = add_stop(scan, seen, door, SPIN_W, a.spin_s)
            print("%s stop %2d heading %6.1f deg | boards %s | door %s" % (tag, k, math.degrees(heading), {m: round(v[1], 2) for m, v in sorted(seen.items())}, "in view" if door else "-"), flush=True)
            if a.dry_run or math.degrees(heading) >= 355 or k == a.max_pulses:
                break
            command(0.0, SPIN_W, a.spin_s)
            time.sleep(a.hold)
        return scan

    def turn_side(deg, sign):
        """Turn by `deg` degrees, left (sign +1) or right (-1), in spin pulses; the angle of each pulse is measured from the boards."""
        turned, prev, pulses = 0.0, sample()[0], []
        for _ in range(8):
            if abs(turned) >= math.radians(deg) - 0.5 * PRIOR_PULSE_RAD or not r1_held():
                break
            command(0.0, sign * SPIN_W, a.spin_s)
            time.sleep(a.hold)
            seen = sample()[0]
            turned += measured_pulse(sign * SPIN_W, prev, seen, pulses)
            observations["turn_pulses"].append(dict(cmd_w=sign * SPIN_W, cmd_s=a.spin_s, measured_deg=round(math.degrees(pulses[-1][0]), 2), boards=pulses[-1][1]))
            prev = seen
            print("turn %s: %.0f deg so far" % ("left" if sign > 0 else "right", math.degrees(abs(turned))), flush=True)

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
                if f is None or not video_is_fresh(f.t_rx, time.perf_counter()):      # no frame for 0.5 s, or a stale one (checked once per round, about 1.7 s: the robot-side e-stop covers R1)
                    print("drive: no fresh frame, stopping", flush=True)
                    break
                video["last_rx"] = f.t_rx
                ahead = [d.distance_m for d in tr.detect_markers(f.frame_bgr) if abs(d.bearing_rad) < math.radians(30)]
                if ahead and min(ahead) < a.stop_range:
                    print("drive: a board %.2f m ahead, stopping" % min(ahead), flush=True)
                    break
        finally:
            stop.set()
            th.join()
            sender.send(0.0, 0.0)
        observations["drive"] = dict(cmd_v=a.drive_v, seconds=round(time.time() - t0, 2))
        print("drive: %.1f s of forward command" % (time.time() - t0), flush=True)

    result, run_dir, observations = {}, None, dict(turn_pulses=[])
    video = {"last_rx": None}
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
        sc1 = spin_scan("scan 1")
        observations["scan1"] = sc1["record"]
        s1, h1 = summarise(sc1["boards"], sc1["doors"]), sc1["heading"]
        result["scan1"] = s1
        if a.dry_run:
            print(json.dumps(s1, indent=1))
            return
        if s1["door_bearing_deg"] is None:
            raise SystemExit("STOP: the door was not seen in scan 1 (door_sightings 0): nothing to triangulate")
        if a.turn_deg is None:
            t = baseline_turn_deg(s1["door_bearing_deg"], math.degrees(h1), a.side)
            print("door bearing %.1f deg, robot heading %.1f deg: turning %s by %.0f deg to drive across the line of sight (baseline to the %s)" % (s1["door_bearing_deg"], math.degrees(h1), "left" if t > 0 else "right", abs(t), a.side), flush=True)
            result["turn_deg_signed"] = round(t, 1)
            preview(t)
            turn_side(abs(t), 1 if t > 0 else -1)
        else:
            turn_signed = a.turn_deg if a.side == "left" else -a.turn_deg
            ang = door_vs_drive_deg(s1["door_bearing_deg"], math.degrees(h1), turn_signed)
            print("door %.1f deg from the drive direction (needs 45-135 deg either side: sideways to the line of sight)" % ang, flush=True)
            if not 45.0 <= abs(ang) <= 135.0:
                raise SystemExit("STOP before moving: the door is %.0f deg from the drive direction; a drive along the line of sight gives parallel rays. Turn the robot so the door is about 90 deg to one side (or use --side without --turn-deg)." % ang)
            preview(turn_signed)
            turn_side(a.turn_deg, 1 if a.side == "left" else -1)
        drive()
        time.sleep(1.5)
        sc2 = spin_scan("scan 2")
        observations["scan2"] = sc2["record"]
        s2 = summarise(sc2["boards"], sc2["doors"])
        result["scan2"] = s2
        if s2["door_bearing_deg"] is None:
            raise SystemExit("STOP: the door was not seen in scan 2")
        try:                                                              # tools.door_pose: least-squares headings, weighted pose fit, range interval. Not yet validated against a taped run.
            from tools.door_pose import locate_joint, scan_from_record
            result["located_joint"] = locate_joint(scan_from_record(sc1["record"]), scan_from_record(sc2["record"]), stand_off_m=a.stand_off)
            print("joint estimate (tools.door_pose):", json.dumps(result["located_joint"], indent=1), flush=True)
        except ValueError as e:
            result["located_joint"] = dict(range_reliable=False, reasons=[str(e)])
            print("joint estimate (tools.door_pose): none (%s)" % e, flush=True)
        res = locate(s1, s2, stand_off_m=a.stand_off)
        res["range_reliable"] = bool(res["baseline_m"] >= 0.5 and res["ray_angle_deg"] >= 8.0)
        if not res["range_reliable"]:
            print(unreliable_text(res), flush=True)
        res["turn_per_pulse_deg"] = [round(math.degrees(float(np.median([p[0] for p in ps if p[1] > 0]))), 1) if any(p[1] > 0 for p in ps) else None for ps in (sc1["pulses"], sc2["pulses"])]
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
            (run_dir / "observations.json").write_text(json.dumps(observations, separators=(",", ":"), allow_nan=False))      # raw per-stop data: replay with python -m tools.door_pose
            (run_dir / "result.json").write_text(json.dumps(dict(result, camera_pose_file=a.camera_pose, battery_v_start=volts0, date=time.strftime("%Y-%m-%d %H:%M")), indent=1, allow_nan=False))
            print("saved", run_dir)


if __name__ == "__main__":
    main()
