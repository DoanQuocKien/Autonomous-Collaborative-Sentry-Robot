"""Spin-in-place scan: find the ArUco boards (and the door, with an entrance reference) all around the robot, and measure the turn per pulse from the boards' bearings.

  python -m tools.scan_boards --label scan_1 --camera-pose calib/camera_pose_self_<today>.json [--entrance data/entrance/class_door] [--dry-run]

The robot only ROTATES (no translation): hold R1 with the e-stop armed (hold Start 1.5 s), keep 0.3 m of floor clear around it. Each pulse is a legal spin command (v = 0, w = 0.45 for 0.2 s,
about 25 degrees to the left), then the robot holds still for --hold s and the video is sampled. The angle of every pulse is measured from the boards seen before and after it (a fixed board's
bearing falls by the pulse angle); the heading at each stop is the running sum, so each board's position is expressed in the START frame (x forward, y left, metres).
Output data/scan/<label>_<n>/: stops.csv (one row per stop and board), summary.json (turn per pulse with its spread, board positions, door bearing), anchors.csv (marker_id,x_m,y_m,z_m,yaw_deg).
The anchor yaw is not measured here (0 is written): it only matters for the pose fixes, not for the servo or the layout.
Only the calibrated 0.2 s pulse is supported. Missing/stale video or an incomplete frame sample aborts the scan and sends an immediate stop; a valid image without boards is allowed.
"""
import argparse
import csv
import json
import math
import os
import threading
import time
from pathlib import Path

import numpy as np

SPIN_W = 0.45
CALIBRATED_SPIN_S = 0.2
PRIOR_PULSE_RAD = 0.438                           # turn per 0.2 s pulse measured on 2026-10-30 and 2026-11-11 (25 deg); only used until a board gives a measurement
MAX_VIDEO_AGE_S = 0.5
ESTOP_LATCH = "/home/jetbot/sentry/ESTOP"
MIN_BATTERY_V = 11.4


def wrap(a):
    return math.atan2(math.sin(a), math.cos(a))


def pulse_angle(prev, cur, min_range=1.0):
    """prev, cur: {marker_id: (bearing_rad, range_m)} at two consecutive stops. Boards at least min_range away seen at both stops: a fixed board's bearing falls by the pulse angle
    (left positive). -> (median angle rad, n boards) or (None, 0)."""
    d = [wrap(prev[m][0] - cur[m][0]) for m in prev if m in cur and prev[m][1] >= min_range and cur[m][1] >= min_range]
    return (float(np.median(d)), len(d)) if d else (None, 0)


def to_start_frame(fwd, left, heading):
    """A point seen at (fwd, left) metres from the robot while its heading is `heading` (left positive from the start heading) -> (x, y) in the start frame."""
    c, s = math.cos(heading), math.sin(heading)
    return fwd * c - left * s, fwd * s + left * c


def camera_to_robot(tvec, pitch):
    """Camera optical frame (x right, y down, z forward) -> (forward, left, height above the lens axis downward positive...) for a camera pitched by `pitch` (positive = down)."""
    X, Y, Z = (float(v) for v in np.asarray(tvec).ravel())
    return Z * math.cos(pitch) - Y * math.sin(pitch), -X


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--label", required=True)
    ap.add_argument("--camera-pose", required=True)
    ap.add_argument("--entrance", default=None, help="folder from tools.enroll_entrance: also find the door (bearing only)")
    ap.add_argument("--ip", default="auto")
    ap.add_argument("--user", default="jetbot")
    ap.add_argument("--password", default=os.environ.get("JETBOT_PASSWORD"))
    ap.add_argument("--max-pulses", type=int, default=18)
    ap.add_argument("--spin-s", type=float, default=CALIBRATED_SPIN_S, help="calibrated pulse duration; only 0.2 s is supported")
    ap.add_argument("--hold", type=float, default=1.0, help="seconds to stay still after a pulse before sampling (video lag < 0.16 s)")
    ap.add_argument("--samples", type=int, default=6)
    ap.add_argument("--wait", type=float, default=90.0, help="seconds to arm the e-stop and hold R1")
    ap.add_argument("--min-battery", type=float, default=MIN_BATTERY_V)
    ap.add_argument("--dry-run", action="store_true", help="no spin commands: one stop only")
    ap.add_argument("--heading0", type=float, default=0.0, help="continue a scan: the robot is already turned by this many degrees (left positive) from the start heading; the scan ends at 355 deg")
    ap.add_argument("--out", default="data/scan")
    a = ap.parse_args()
    if not (0 < a.spin_s <= 0.5 and 0 < a.hold <= 5 and 1 <= a.max_pulses <= 40 and a.samples >= 1):
        raise SystemExit("ABORT: spin-s must be in (0, 0.5], hold in (0, 5], 1-40 pulses")
    if a.spin_s != CALIBRATED_SPIN_S:
        raise SystemExit("ABORT: only the calibrated --spin-s 0.2 is supported; other durations need a new turn calibration")

    from sentry.config import load
    from sentry.nav.localization import LocalizationTracker
    from sentry.net.discover import resolve
    from sentry.net.udp_tx import UDPSender
    from sentry.net.zmq_rx import ZMQReceiver
    from tools import jetbot_ssh
    from tools.calibrate_motion import _sh
    from tools.jetbot_status import ina219_bus_volts
    import winsound

    pose = json.load(open(a.camera_pose))
    pitch = math.radians(pose["pitch_down_deg"])
    tr = LocalizationTracker(motion_calib=None, camera_calib="calib/camera.json", max_marker_distance_m=1e6)
    entrance = None
    if a.entrance:
        from sentry.perception.entrance import Camera, EntranceDetector
        entrance = EntranceDetector.load(a.entrance, camera=Camera.from_json("calib/camera.json"))
    a.ip = resolve(a.ip)
    password = jetbot_ssh.password(a.password)
    ssh = jetbot_ssh.connect(a.ip, a.user, password)
    volts0 = ina219_bus_volts(jetbot_ssh.sudo(ssh, "i2cget -y 1 0x41 0x02 w", password))
    print("battery %.2f V" % volts0, flush=True)
    if volts0 < a.min_battery:
        raise SystemExit("ABORT: battery %.2f V < %.1f V: charge first" % (volts0, a.min_battery))
    port = load()["net"]["control_port"]
    rx = ZMQReceiver(ip=a.ip)
    stops, boards, doors, pulses = [], {}, [], []
    end_reason = {"r": None}
    sender = state = None
    volts1 = None
    heading = math.radians(a.heading0)
    link = {"ssh": ssh}
    video = {"last_rx": None}

    def require_fresh_video():
        last = video["last_rx"]
        if last is None or not 0 <= time.perf_counter() - last <= MAX_VIDEO_AGE_S:
            raise RuntimeError("ABORT: no fresh robot video; scan stopped")

    def r1_held():
        """R1 over SSH; one dropped connection is retried once with a fresh connection (the robot's Wi-Fi is weak), a second failure ends the run."""
        for attempt in (0, 1):
            try:
                return _sh(link["ssh"], "test -e %s && echo no || echo yes" % ESTOP_LATCH).strip() == "yes"
            except Exception:
                if attempt == 1:
                    raise
                link["ssh"] = jetbot_ssh.connect(a.ip, a.user, password)

    def sample(k):
        """Median over a few frames: {marker_id: (bearing, range, fwd, left)} and the door result."""
        per, door = {}, []
        n, t0 = 0, time.time()
        while n < a.samples and time.time() - t0 < 6.0:
            f = rx.read(timeout=0.5)
            if f is None:
                continue
            if not 0 <= time.perf_counter() - f.t_rx <= MAX_VIDEO_AGE_S:
                continue
            video["last_rx"] = f.t_rx
            n += 1
            for d in tr.detect_markers(f.frame_bgr):
                fwd, left = camera_to_robot(d.tvec, pitch)
                per.setdefault(d.marker_id, []).append((d.bearing_rad, d.distance_m, fwd, left))
            if entrance is not None:
                r = entrance(f.frame_bgr, 0.0)
                if r.in_view and r.bearing_rad is not None:
                    door.append((r.bearing_rad, r.inliers))
        if n < a.samples:
            raise RuntimeError("ABORT: incomplete robot video sample (%d/%d fresh frames); scan stopped" % (n, a.samples))
        require_fresh_video()
        seen = {m: tuple(float(np.median([v[i] for v in vs])) for i in range(4)) + (len(vs),) for m, vs in per.items()}
        return seen, door

    try:
        rx.start()
        if not a.dry_run:
            print("ARM the e-stop (hold Start 1.5 s) and HOLD R1 within %.0f s; the robot will spin in place, keep 0.3 m clear around it. Release R1 at any problem." % a.wait, flush=True)
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
        prev = None
        for k in range(a.max_pulses + 1):
            if not a.dry_run and not r1_held():
                end_reason["r"] = "R1 released"
                break
            seen, door = sample(k)
            if prev is not None:
                ang, nb = pulse_angle({m: v[:2] for m, v in prev.items()}, {m: v[:2] for m, v in seen.items()})
                if ang is None:                                                  # no board in common: use the median of the earlier pulses
                    ang = float(np.median([p[0] for p in measured])) if (measured := [p for p in pulses if p[1] > 0]) else PRIOR_PULSE_RAD    # no board in common: the measured median, else the calibrated prior
                    nb = 0
                pulses.append((ang, nb))
                heading += ang
            for m, v in seen.items():
                x, y = to_start_frame(v[2], v[3], heading)
                boards.setdefault(m, []).append((x, y, v[1]))
                stops.append(dict(stop=k, heading_deg=round(math.degrees(heading), 1), marker_id=m, bearing_deg=round(math.degrees(v[0]), 1), range_m=round(v[1], 2), fwd_m=round(v[2], 2), left_m=round(v[3], 2), x_m=round(x, 2), y_m=round(y, 2), frames=int(v[4])))
            for b, inl in door:
                doors.append((heading + b, inl))
            print("stop %2d heading %6.1f deg | boards %s | door %s" % (k, math.degrees(heading), {m: round(v[1], 2) for m, v in sorted(seen.items())}, "in view" if door else "-"), flush=True)
            prev = seen
            if a.dry_run or math.degrees(heading) >= 355 or k == a.max_pulses:
                break
            t_pulse = time.time() + a.spin_s                                     # one spin pulse, then stop and hold
            while time.time() < t_pulse:
                require_fresh_video()
                sender.send(0.0, SPIN_W)
                time.sleep(1 / 30.0)
            sender.stop()
            time.sleep(a.hold)
        if end_reason["r"] is None:
            end_reason["r"] = "dry run" if a.dry_run else ("full turn" if math.degrees(heading) >= 355 else "max pulses")
    except BaseException as e:
        end_reason["r"] = "error: %s: %s" % (type(e).__name__, e)
        raise
    finally:
        try:
            if sender is not None:
                sender.close(stop=True)
        except Exception:
            pass
        try:
            rx.close()
        except Exception:
            pass
        try:
            volts1 = ina219_bus_volts(jetbot_ssh.sudo(ssh, "i2cget -y 1 0x41 0x02 w", password))
        except Exception:
            volts1 = None
        out_dir = Path(a.out)
        n = 1 + len(list(out_dir.glob(a.label + "_*"))) if out_dir.exists() else 1
        while True:
            run_dir = out_dir / ("%s_%d" % (a.label, n))
            try:
                run_dir.mkdir(parents=True, exist_ok=False)
                break
            except FileExistsError:
                n += 1
        if stops:
            with open(run_dir / "stops.csv", "w", newline="") as fh:
                wr = csv.DictWriter(fh, fieldnames=list(stops[0].keys()))
                wr.writeheader()
                wr.writerows(stops)
        angs = [p[0] for p in pulses if p[1] > 0]
        summary = dict(label=a.label, end_reason=end_reason["r"], pulses=len(pulses), pulses_measured=len(angs), total_heading_deg=round(math.degrees(heading), 1),
                       turn_per_pulse_rad=round(float(np.median(angs)), 3) if angs else None, turn_per_pulse_sd_rad=round(float(np.std(angs)), 3) if len(angs) > 1 else None,
                       turn_per_pulse_deg=round(math.degrees(float(np.median(angs))), 1) if angs else None, spin_s=a.spin_s, spin_w=SPIN_W,
                       boards={str(m): dict(x_m=round(float(np.median([p[0] for p in v])), 2), y_m=round(float(np.median([p[1] for p in v])), 2), stops=len(v), spread_m=round(float(np.hypot(np.std([p[0] for p in v]), np.std([p[1] for p in v]))), 2)) for m, v in sorted(boards.items())},
                       door_bearing_deg=round(math.degrees(float(np.median([d[0] for d in doors]))), 1) if doors else None, door_sightings=len(doors),
                       camera_pose_file=a.camera_pose, battery_v_start=volts0, battery_v_end=volts1, date=time.strftime("%Y-%m-%d %H:%M"), dry_run=a.dry_run,
                       note="positions from the boards' pose in the video and the heading summed from the measured pulse angles; boards seen only at the start stop have no heading error; 150 mm boards are noisy beyond 2-3 m")
        (run_dir / "summary.json").write_text(json.dumps(summary, indent=1, allow_nan=False))
        with open(run_dir / "anchors.csv", "w", newline="") as fh:
            fh.write("marker_id,x_m,y_m,z_m,yaw_deg\n")
            for m, v in sorted(boards.items()):
                fh.write("%d,%.2f,%.2f,0.207,0\n" % (m, float(np.median([p[0] for p in v])), float(np.median([p[1] for p in v]))))
        print(json.dumps({k: summary[k] for k in ("end_reason", "pulses_measured", "turn_per_pulse_deg", "turn_per_pulse_sd_rad", "total_heading_deg", "boards", "door_bearing_deg")}, indent=1), flush=True)
        print("saved", run_dir, flush=True)


if __name__ == "__main__":
    main()
