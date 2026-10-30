"""Measure the robot's real turns and straight drives against the dead-reckoning model with ArUco boards (no tape), and fit this session's floor corrections.

  python -m tools.motion_check --label class_1 --anchors data/anchors_class.csv                          # drive, measure, fit: writes calib/motion_session_<date>_<n>.json
  python -m tools.motion_check --label class_2 --anchors data/anchors_class.csv --motion-session calib/motion_session_1030_1.json   # CHECK: same drive with the correction applied
  python -m tools.motion_check --label class_1 --anchors ... --replay-only                                 # analyse a saved run again

WHY: on 2026-10-30 the first supervised run went off the line toward the door (dead reckoning said it was on the sweet spot). An unlevel floor turns the robot at different rates to the left and to the right
and bends straight drives; the Week 2 gains came from another floor. Here the robot stands still, sees the boards, moves, stands still again: the marker pose before and after each segment is the truth (the
tracker's own marker pose, as tools.dr_path), the model integrated over the commands that were sent is the prediction. Per segment: ratio = measured / predicted (turn angle, forward distance) and the
heading the model did not predict per metre driven. Fit: speed `scale`, `w_scale_left`, `w_scale_right`, `drift_rad_per_m` (sentry/nav/wheel_model.py), applied by `deploy_live --motion-session`.

SETUP: robot where the run starts, e-stop armed, you hold R1 for the whole sequence (it stops by itself if R1 is released), floor CLEAR for 1.5 m around it. Boards (150 mm, upright, ids from the anchors CSV marker_id,x_m,y_m,z_m,yaw_deg
as tools.dr_path) must be within --max-marker-m (1.5) of the robot at every rest: otherwise that segment is reported as "no marker pose" and does not count. Several boards all around make every rest measurable.
Sequence (--repeats times): spin left, spin right, drive forward, each followed by --rest s of stillness; the pose is the median of the marker poses of the last 1.2 s of the rest.
PASS (check run, proposed limits): every measurable segment within 10 % of its prediction (turn angle, forward distance) and drift under 0.05 rad/m. The fit is refused when the repeats of one kind scatter by more than 0.15 in
ratio, or a kind has no measurable segment. Never use --no-estop; R1 held.
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

from sentry.nav.wheel_model import WheelModel

ESTOP_LATCH = "/home/jetbot/sentry/ESTOP"
MIN_BATTERY_V = 11.3
RATIO_LIMIT = 0.10
DRIFT_LIMIT = 0.05
SCATTER_LIMIT = 0.15
KINDS = ("spin_left", "spin_right", "forward")


def wrap(a):
    return math.atan2(math.sin(a), math.cos(a))


def rest_pose(frames, t0, t1, tracker_factory, min_frames=5, max_yaw_std_deg=1.5, max_pos_std_m=0.05):
    """Marker pose (x, y, yaw) in the frames stamped in [t0, t1]: median position, circular mean yaw; None when too few frames saw a board or they scatter."""
    poses = []
    for t, img in frames:
        if t0 <= t <= t1:
            tr = tracker_factory()
            tr.update_with_markers(img, alpha=1.0)
            if tr.corrections_count:
                poses.append((tr.pose.x, tr.pose.y, tr.pose.theta))
    if len(poses) < min_frames:
        return None
    p = np.array(poses)
    yaw = math.atan2(np.mean(np.sin(p[:, 2])), np.mean(np.cos(p[:, 2])))
    yaw_std = math.degrees(math.sqrt(np.mean([wrap(a - yaw) ** 2 for a in p[:, 2]])))
    if yaw_std > max_yaw_std_deg or max(p[:, 0].std(), p[:, 1].std()) > max_pos_std_m:
        return None
    return float(np.median(p[:, 0])), float(np.median(p[:, 1])), yaw


def dr_delta(cmds, model, t0, t1):
    """The model's displacement over the commands stamped in [t0, t1], in the frame of the start pose: (forward m, left m, turn rad)."""
    x = y = yaw = 0.0
    prev = None
    for t, v, w in cmds:
        if prev is not None and t0 <= t <= t1:
            dt = min(t - prev[0], 0.1)
            v_m, w_r = model.body_speeds(prev[1], prev[2])
            x += v_m * math.cos(yaw) * dt
            y += v_m * math.sin(yaw) * dt
            yaw += w_r * dt
        prev = (t, v, w)
    return x, y, yaw


def measured_delta(p0, p1):
    """Marker pose change in the frame of the first pose: (forward m, left m, turn rad)."""
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    c, s = math.cos(p0[2]), math.sin(p0[2])
    return dx * c + dy * s, -dx * s + dy * c, wrap(p1[2] - p0[2])


def analyse(segments, poses, cmds, model):
    """segments: [{name, kind, t0, t1}]; poses[i] is the rest pose before segment i, poses[i + 1] after it (None = not measurable). -> one row per segment."""
    rows = []
    for i, sg in enumerate(segments):
        row = dict(name=sg["name"], kind=sg["kind"], measurable=poses[i] is not None and poses[i + 1] is not None)
        if row["measurable"]:
            mf, ml, mth = measured_delta(poses[i], poses[i + 1])
            pf, pl, pth = dr_delta(cmds, model, sg["t0"], sg["t1"])
            row.update(measured_forward_m=round(mf, 3), measured_left_m=round(ml, 3), measured_turn_deg=round(math.degrees(mth), 1),
                       predicted_forward_m=round(pf, 3), predicted_turn_deg=round(math.degrees(pth), 1))
            if sg["kind"] == "forward":
                row["ratio"] = round(mf / pf, 3) if pf > 0.05 else None
                row["drift_rad_per_m"] = round((mth - pth) / mf, 4) if mf > 0.05 else None
            else:
                row["ratio"] = round(mth / pth, 3) if abs(pth) > math.radians(10) else None
        rows.append(row)
    return rows


def fit(rows, model):
    """-> (session dict, problems). The ratios are against `model`, so the new gains are model gains times the mean ratio; the drift adds to the model's drift. `scale` multiplies the wheel speeds and so the turn rate too: the turn scales are the turn ratio divided by the speed ratio."""
    problems, mean = [], {}
    for kind in KINDS:
        rs = [r["ratio"] for r in rows if r["kind"] == kind and r.get("ratio") is not None]
        if not rs:
            problems.append("no measurable %s segment (a board within %.1f m at both rests?)" % (kind, 1.5))
            continue
        if max(rs) - min(rs) > SCATTER_LIMIT:
            problems.append("%s ratios scatter: %s (limit %.2f)" % (kind, rs, SCATTER_LIMIT))
        mean[kind] = float(np.mean(rs))
    drifts = [r["drift_rad_per_m"] for r in rows if r["kind"] == "forward" and r.get("drift_rad_per_m") is not None]
    if problems:
        return None, problems
    return dict(scale=round(model.scale * mean["forward"], 4), w_scale_left=round(model.w_scale_left * mean["spin_left"] / mean["forward"], 4),
                w_scale_right=round(model.w_scale_right * mean["spin_right"] / mean["forward"], 4), drift_rad_per_m=round(model.drift_rad_per_m + float(np.mean(drifts)), 4),
                segments=len(rows), measurable=sum(1 for r in rows if r["measurable"])), problems


def verdict(rows):
    """Check rule: every measurable segment's ratio within RATIO_LIMIT of 1 and every drift under DRIFT_LIMIT. -> (passed, list of failures)."""
    bad = []
    for r in rows:
        if r.get("ratio") is not None and abs(r["ratio"] - 1.0) > RATIO_LIMIT:
            bad.append("%s ratio %.2f" % (r["name"], r["ratio"]))
        if r.get("drift_rad_per_m") is not None and abs(r["drift_rad_per_m"]) > DRIFT_LIMIT:
            bad.append("%s drift %+.3f rad/m" % (r["name"], r["drift_rad_per_m"]))
    return not bad, bad


def plan(repeats, spin_w, spin_s, v, drive_s):
    seq = []
    for k in range(repeats):
        seq += [("spin_left_%d" % (k + 1), "spin_left", 0.0, spin_w, spin_s), ("spin_right_%d" % (k + 1), "spin_right", 0.0, -spin_w, spin_s),
                ("forward_%d" % (k + 1), "forward", v, 0.0, drive_s)]
    return seq


def drive(a, out):
    from sentry.config import load
    from sentry.net.discover import resolve
    from sentry.net.udp_tx import UDPSender
    from tools import jetbot_ssh
    from tools.calibrate_motion import _sh
    from tools.dr_path import _frame_thread
    from tools.jetbot_status import ina219_bus_volts
    from tools.speed_trial import beep
    ip = resolve(a.ip)
    password = jetbot_ssh.password(a.password)
    ssh = jetbot_ssh.connect(ip, a.user, password)
    volts = ina219_bus_volts(jetbot_ssh.sudo(ssh, "i2cget -y 1 0x41 0x02 w", password))
    print("battery %.2f V" % volts)
    if volts < a.min_battery:
        raise SystemExit("battery below %.1f V: charge first" % a.min_battery)
    frames, cmds, segments, stop = [], [], [], threading.Event()
    threading.Thread(target=_frame_thread, args=(stop, frames), daemon=True).start()
    time.sleep(2.0)
    sender = UDPSender(ip, load()["net"]["control_port"], 30)
    latch = {"armed": True}

    def watch():                                            # the e-stop latch file appears when R1 is released: stop the sequence
        while not stop.is_set():
            latch["armed"] = _sh(ssh, "test -e %s && echo no || echo yes" % ESTOP_LATCH).strip() == "yes"
            time.sleep(0.3)
    reason = "done"
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
        threading.Thread(target=watch, daemon=True).start()
        print("R1 held: sequence starts (hold it until the two beeps)", flush=True)

        def hold(v, w, seconds):
            t_end = time.perf_counter() + seconds
            while time.perf_counter() < t_end:
                if not latch["armed"]:
                    return False
                sender.send(v, w)
                cmds.append((time.perf_counter(), v, w))
                time.sleep(sender.period_s)
            return True
        ok = hold(0.0, 0.0, a.rest)
        for name, kind, v, w, seconds in plan(a.repeats, a.spin_w, a.spin_s, a.v, a.drive_s):
            if not ok:
                break
            t0 = time.perf_counter()
            ok = hold(v, w, seconds)
            if not ok:
                break                                      # released during the motion: this segment is not a measurement
            t1 = time.perf_counter()
            segments.append(dict(name=name, kind=kind, v=v, w=w, t0=t0, t1=t1))
            print("  %s done" % name, flush=True)
            ok = ok and hold(0.0, 0.0, a.rest)
        if not ok:
            reason = "R1 released: the sequence is incomplete"
    finally:
        sender.close()
        stop.set()
    time.sleep(0.5)
    beep(1000, 300)
    beep(1000, 300)
    out.mkdir(parents=True, exist_ok=True)
    (out / "frames").mkdir(exist_ok=True)
    import cv2
    for i, (t, img) in enumerate(frames):
        cv2.imwrite(str(out / "frames" / ("%03d_%.3f.jpg" % (i, t))), img)
    with (out / "commands.csv").open("w", newline="") as f:
        csv.writer(f).writerows([("t", "v", "w")] + [(round(t, 4), v, w) for t, v, w in cmds])
    (out / "segments.json").write_text(json.dumps(dict(segments=segments, rest_s=a.rest, battery_v=volts, ended=reason), indent=1))
    return cmds, frames, segments, volts, reason


def load_run(out):
    from tools.dr_path import load_run as lr
    cmds, frames = lr(out)
    info = json.loads((out / "segments.json").read_text())
    return cmds, frames, info["segments"], info["rest_s"]


def rest_poses(segments, frames, rest_s, factory):
    """Rest pose before the first segment (the rest ending where it starts) and after every segment (the rest that follows it)."""
    t_first = segments[0]["t0"]
    out = [rest_pose(frames, t_first - 1.2, t_first, factory)]
    for sg in segments:
        out.append(rest_pose(frames, sg["t1"] + rest_s - 1.2, sg["t1"] + rest_s, factory))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--label", required=True)
    ap.add_argument("--anchors", required=True, help="marker anchors CSV (marker_id,x_m,y_m,z_m,yaw_deg)")
    ap.add_argument("--motion-session", help="a calib/motion_session_*.json: predict with its correction (the CHECK run)")
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--spin-w", type=float, default=0.45, help="turn command (0.45 is above the motor dead zone, as deploy_runner)")
    ap.add_argument("--spin-s", type=float, default=1.5)
    ap.add_argument("--v", type=float, default=0.55)
    ap.add_argument("--drive-s", type=float, default=3.0)
    ap.add_argument("--rest", type=float, default=2.5, help="seconds of stillness after each segment")
    ap.add_argument("--max-marker-m", type=float, default=1.5)
    ap.add_argument("--wait", type=float, default=60.0)
    ap.add_argument("--min-battery", type=float, default=MIN_BATTERY_V)
    ap.add_argument("--ip")
    ap.add_argument("--user", default="jetbot")
    ap.add_argument("--password", default=os.environ.get("JETBOT_PASSWORD"))
    ap.add_argument("--replay-only", action="store_true")
    ap.add_argument("--out", default="calib")
    a = ap.parse_args()
    run = Path("data/motion_check") / a.label
    if a.replay_only:
        cmds, frames, segments, rest_s = load_run(run)
        volts = None
    else:
        cmds, frames, segments, volts, why = drive(a, run)
        rest_s = a.rest
        print("sequence ended: %s" % why)
    if not segments:
        raise SystemExit("no segment was driven")
    model = WheelModel.from_session(a.motion_session) if a.motion_session else WheelModel()
    from sentry.nav.localization import LocalizationTracker

    def factory():
        tr = LocalizationTracker(motion_calib=None, camera_calib="calib/camera.json", max_marker_distance_m=a.max_marker_m)
        tr.load_anchors_csv(a.anchors)
        tr.set_pose(0.0, 0.0, 0.0)
        return tr
    poses = rest_poses(segments, frames, rest_s, factory)
    rows = analyse(segments, poses, cmds, model)
    for r in rows:
        if not r["measurable"]:
            print("  %-14s no marker pose before or after (no board within %.1f m at a rest)" % (r["name"], a.max_marker_m))
        else:
            print("  %-14s measured turn %+6.1f deg fwd %+.2f m | predicted turn %+6.1f deg fwd %+.2f m | ratio %s%s" % (
                r["name"], r["measured_turn_deg"], r["measured_forward_m"], r["predicted_turn_deg"], r["predicted_forward_m"], r.get("ratio"),
                ("  drift %+.3f rad/m" % r["drift_rad_per_m"]) if r.get("drift_rad_per_m") is not None else ""))
    passed, bad = verdict(rows)
    session, problems = fit(rows, model)
    result = dict(label=a.label, battery_v=volts, model="session " + a.motion_session if a.motion_session else "calib defaults", rows=rows, check_passed=passed, check_failures=bad,
                  fit=session, fit_problems=problems, limits=dict(ratio=RATIO_LIMIT, drift_rad_per_m=DRIFT_LIMIT, scatter=SCATTER_LIMIT))
    (run / "summary.json").write_text(json.dumps(result, indent=1))
    print("CHECK against the model (%s): %s%s" % (result["model"], "PASS" if passed else "FAIL", "" if passed else " - " + "; ".join(bad)))
    if session is None:
        raise SystemExit("NOT WRITTEN: " + "; ".join(problems))
    out = Path(a.out)
    n = 1 + len(list(out.glob("motion_session_%s_*.json" % time.strftime("%m%d"))))
    path = out / ("motion_session_%s_%d.json" % (time.strftime("%m%d"), n))
    session.update(label=a.label, battery_v=volts, method="marker-measured turns and drive against the wheel model (tools/motion_check.py)", based_on=result["model"])
    path.write_text(json.dumps(session, indent=1))
    print("wrote %s: scale %.3f, turn left %.3f, turn right %.3f, drift %+.3f rad/m" % (path, session["scale"], session["w_scale_left"], session["w_scale_right"], session["drift_rad_per_m"]))


if __name__ == "__main__":
    main()
