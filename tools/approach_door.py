"""Drive to the sweet spot in front of the door, stop-and-go, steering on the DOOR ITSELF (no dead reckoning, no board map).

  python -m tools.approach_door --label ap --camera-pose calib/camera_pose_self_<today>.json --entrance data/entrance/class_door --door-range-m 3.42 [--dry-run]

Why: an open-loop drive veers 5-60 deg per metre (measured 2026-11-11), so the heading after a drive is unpredictable; the entrance detector gives the door bearing to about 1 deg (checked against
tape twice on 2026-11-11), so the loop is: measure the door (median of a few frames) -> if its bearing is outside +/- --center-tol-deg, spin a short pulse toward it -> else drive one burst ->
stop, hold, measure again. RANGE: the image area of the matched door outline scales as 1/range^2, so range = --door-range-m * sqrt(A0 / A) with A0 the area at the first sighting (taken as
--door-range-m, a tape measurement: the only manual number). Stops when the range estimate reaches --stand-off (1.5-3.0 m window of the spec, 2.0 m default) -> final report.
If the door is not in view at the start the robot spins left in pulses to find it (at most --search-pulses). It is NOT a general solution: the first range is a tape value, the area ratio assumes the
door outline is matched the same way at every range, and the obstacle check is only the ArUco boards ahead (--stop-range); a clear floor is the operator's job.
SAFETY: R1 + armed e-stop (hold Start 1.5 s); at most --max-bursts bursts; stops when R1 is released, the door is lost for --lost-max measurements, a frame is missing, or a board ahead is closer than
--stop-range. Output data/approach/<label>_<n>/log.csv + summary.json (range estimate per step; compare the final one with a tape measurement)."""
import argparse
import csv
import json
import math
import os
import time
from pathlib import Path

import numpy as np

from tools.scan_boards import ESTOP_LATCH, MIN_BATTERY_V, SPIN_W


MAX_VIDEO_AGE_S = 0.5                                     # a frame older than this is not used, and no command is sent on older video (same limit as the scan guard in PR #107)


def video_is_fresh(last_rx, now, max_age=MAX_VIDEO_AGE_S):
    """True when the last received frame is at most max_age seconds old (both times from time.perf_counter())."""
    return last_rx is not None and 0 <= now - last_rx <= max_age


def polygon_area(quad):
    """Shoelace area of the matched door outline [(x, y), ...] (pixels^2)."""
    a = 0.0
    for (x0, y0), (x1, y1) in zip(quad, quad[1:] + quad[:1]):
        a += x0 * y1 - x1 * y0
    return abs(a) / 2.0


def range_from_area(area, area0, range0, exponent=2.0):
    """Range at which the outline has `area`, given `area0` at `range0` (area ~ range^-exponent; 2 for an ideal flat target). On 2026-11-11/12 the door outline grew more slowly than 1/range^2
    (exponent about 1.55-1.7 from two taped runs, probably because the matched outline is cut by the frame edges as the door fills the view): fitted on those two runs, then confirmed on a third (0.00 m error); one door, one floor."""
    if area <= 0 or area0 <= 0 or exponent <= 0:
        raise ValueError("areas and the exponent must be positive")
    return range0 * (area0 / area) ** (1.0 / exponent)


def next_action(bearing_deg, range_m, stand_off_m, tol_deg, aim_offset_deg=0.0):
    """-> 'done' | 'turn_left' | 'turn_right' | 'drive'. Bearing positive = door to the LEFT. aim_offset_deg: the bearing treated as "centred" (feed-forward for a known veer: the robot veered
    left about 5.5 deg per 0.6 s burst on 2026-11-11, which moves the door to the right, so +2.75 centres the door after the burst)."""
    bearing_deg -= aim_offset_deg
    if range_m <= stand_off_m:
        return "done"
    if bearing_deg > tol_deg:
        return "turn_left"
    if bearing_deg < -tol_deg:
        return "turn_right"
    return "drive"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--label", required=True)
    ap.add_argument("--camera-pose", required=True)
    ap.add_argument("--entrance", required=True)
    ap.add_argument("--door-range-m", type=float, required=True, help="tape distance from the robot to the door NOW (calibrates the area scale)")
    ap.add_argument("--stand-off", type=float, default=2.0)
    ap.add_argument("--area-exponent", type=float, default=1.6, help="outline area ~ range^-exponent (2 = ideal flat target). 1.6: fitted on two taped runs (1.55-1.7) and confirmed on a third from another start (error 0.00 m): this door, this floor, starts 2.6-3.4 m")
    ap.add_argument("--center-tol-deg", type=float, default=8.0, help="drive when the door bearing is within +/- this of the aim (the shortest turn pulse turns about 14 deg: a window under about 7 makes the robot hunt, see classroom_1111_pm)")
    ap.add_argument("--aim-offset-deg", type=float, default=0.0, help="bearing treated as centred (feed-forward for a known left veer: +2.75 on the classroom tile, 2026-11-11)")
    ap.add_argument("--drive-v", type=float, default=0.85)
    ap.add_argument("--burst-s", type=float, default=0.6)
    ap.add_argument("--spin-s", type=float, default=0.2, help="turn pulse for a bearing error over 12 deg")
    ap.add_argument("--small-spin-s", type=float, default=0.12, help="turn pulse for a smaller error")
    ap.add_argument("--hold", type=float, default=0.8)
    ap.add_argument("--samples", type=int, default=5)
    ap.add_argument("--max-bursts", type=int, default=20)
    ap.add_argument("--max-steps", type=int, default=60)
    ap.add_argument("--search-pulses", type=int, default=15)
    ap.add_argument("--lost-max", type=int, default=3)
    ap.add_argument("--search-side", choices=("left", "right"), default="left", help="spin direction while the door has not been seen yet (use the side it was last seen on)")
    ap.add_argument("--stop-range", type=float, default=0.8, help="stop when a board within 30 deg of straight ahead is closer than this (m)")
    ap.add_argument("--ip", default="auto")
    ap.add_argument("--user", default="jetbot")
    ap.add_argument("--password", default=os.environ.get("JETBOT_PASSWORD"))
    ap.add_argument("--wait", type=float, default=90.0)
    ap.add_argument("--min-battery", type=float, default=MIN_BATTERY_V)
    ap.add_argument("--path-clear", action="store_true", help="the operator confirms the floor is clear (required for a live run: the obstacle check only sees boards straight ahead)")
    ap.add_argument("--dry-run", action="store_true", help="measure only, no commands")
    ap.add_argument("--out", default="data/approach")
    a = ap.parse_args()
    if not a.dry_run and not a.path_clear:
        raise SystemExit("ABORT: the robot drives toward the door: add --path-clear to confirm that the whole way to the door is clear and 0.3 m around the robot (the only obstacle check is a board straight ahead, a chair is not seen)")
    if not (1.5 <= a.stand_off <= 3.0 and a.door_range_m > a.stand_off - 0.5 and 1.0 <= a.area_exponent <= 2.5 and 0.3 <= a.drive_v <= 1.0 and 0.1 <= a.burst_s <= 1.0 and 0.05 <= a.small_spin_s <= a.spin_s <= 0.5 and 1 <= a.center_tol_deg <= 15 and abs(a.aim_offset_deg) <= 8):
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
    rows, summary = [], {}
    video = {"last_rx": None}

    def r1_held():
        for attempt in (0, 1):
            try:
                return _sh(link["ssh"], "test -e %s && echo no || echo yes" % ESTOP_LATCH).strip() == "yes"
            except Exception:
                if attempt == 1:
                    raise
                link["ssh"] = jetbot_ssh.connect(a.ip, a.user, password)

    def measure():
        """-> (door bearing deg, outline area px^2, n frames with the door, board range ahead or None); medians over --samples frames."""
        b, ar, n, ahead = [], [], 0, []
        t0, got = time.time(), 0
        while got < a.samples and time.time() - t0 < 6.0:
            f = rx.read(timeout=0.5)
            if f is None:
                continue
            if not video_is_fresh(f.t_rx, time.perf_counter()):             # stale frame (laggy link): not used
                continue
            video["last_rx"] = f.t_rx
            got += 1
            ahead += [d.distance_m for d in tr.detect_markers(f.frame_bgr) if abs(d.bearing_rad) < math.radians(30)]
            r = entrance(f.frame_bgr, 0.0)
            if r.in_view and r.bearing_rad is not None and r.quad:
                b.append(math.degrees(r.bearing_rad))
                ar.append(polygon_area(list(r.quad)))
                n += 1
        if got == 0:
            raise SystemExit("STOP: no fresh video frame for 6 s")
        return (float(np.median(b)) if b else None, float(np.median(ar)) if ar else None, n, min(ahead) if ahead else None)

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
        time.sleep(a.hold)

    try:
        if not a.dry_run:
            print("ARM the e-stop (hold Start 1.5 s) and HOLD R1 within %.0f s and keep holding it for the whole run; keep 0.3 m clear around the robot and the way to the door clear." % a.wait, flush=True)
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
        area0, lost, bursts, searched, end = None, 0, 0, 0, "max steps"
        for step in range(a.max_steps):
            if not a.dry_run and not r1_held():
                end = "R1 released"
                break
            bearing, area, n, ahead = measure()
            if bearing is None:
                lost += 1
                rows.append(dict(step=step, action="lost", bearing_deg="", range_m="", frames=n))
                print("step %2d: door not in view (%d)" % (step, lost), flush=True)
                if a.dry_run:
                    end = "dry run"
                    break
                if area0 is None and searched < a.search_pulses:        # not seen yet: spin left to find it
                    searched += 1
                    command(0.0, SPIN_W if a.search_side == "left" else -SPIN_W, a.spin_s)
                    lost = 0
                    continue
                if lost >= a.lost_max:
                    end = "door lost"
                    break
                continue
            lost = 0
            if area0 is None:
                area0 = area
                print("first sighting: area %.0f px2 taken as %.2f m" % (area0, a.door_range_m), flush=True)
            rng = range_from_area(area, area0, a.door_range_m, a.area_exponent)
            act = next_action(bearing, rng, a.stand_off, a.center_tol_deg, a.aim_offset_deg)
            if act == "drive" and ahead is not None and ahead < a.stop_range:
                act, end = "done", "board ahead %.2f m" % ahead
            rows.append(dict(step=step, action=act, bearing_deg=round(bearing, 1), range_m=round(rng, 2), frames=n, area_px2=round(area), board_ahead_m=None if ahead is None else round(ahead, 2)))
            print("step %2d: door %+6.1f deg, range est %.2f m (area %.0f px2, %d frames) -> %s" % (step, bearing, rng, area, n, act), flush=True)
            if a.dry_run:
                end = "dry run"
                break
            if act == "done":
                end = end if end != "max steps" else "stand-off reached"
                break
            if act == "drive":
                bursts += 1
                if bursts > a.max_bursts:
                    end = "max bursts"
                    break
                command(a.drive_v, 0.0, a.burst_s)
            else:
                command(0.0, SPIN_W if act == "turn_left" else -SPIN_W, a.spin_s if abs(bearing - a.aim_offset_deg) > 16 else a.small_spin_s)
        summary = dict(end_reason=end, steps=len(rows), bursts=bursts, last_range_est_m=rows[-1].get("range_m") if rows else None, door_range_m_input=a.door_range_m, stand_off_m=a.stand_off)
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
        if rows and not a.dry_run:
            out = Path(a.out)
            n = 1
            while True:
                run_dir = out / ("%s_%d" % (a.label, n))
                try:
                    run_dir.mkdir(parents=True, exist_ok=False)
                    break
                except FileExistsError:
                    n += 1
            with open(run_dir / "log.csv", "w", newline="") as fh:
                wr = csv.DictWriter(fh, fieldnames=["step", "action", "bearing_deg", "range_m", "frames", "area_px2", "board_ahead_m"], restval="")
                wr.writeheader()
                wr.writerows(rows)
            (run_dir / "summary.json").write_text(json.dumps(dict(summary, camera_pose_file=a.camera_pose, battery_v_start=volts0, date=time.strftime("%Y-%m-%d %H:%M")), indent=1, allow_nan=False))
            print("saved", run_dir, json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
