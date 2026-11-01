"""Re-derive every number of the 2026-10-30 classroom analysis from the saved raw data (no robot, no network).

  python -m tools.analyse_classroom_1030            # writes reports/DoanQuocKien/week-04/classroom_1030/analysis/{results.json, catalogue.csv, *.png, speed_vs_battery.json, floor_model_1030.json}
  python -m tools.analyse_classroom_1030 --yolo     # also re-runs YOLO at a low confidence on the furniture frames (needs data/models/yolov8n.pt)

Reads data/ (git-ignored, local only) and the Week 2 reports. Video frames are read for marker bearings, pitch and the furniture check only; no frame or crop is written anywhere.
Raw files are never modified: tools.motion_check --replay-only would overwrite data/motion_check/<label>/summary.json, so its functions are called here instead.
Time bases: deploy log.csv `t` = seconds since the control loop started; servo.csv `t` and frames/<t>.jpg = laptop wall clock at receipt (+ detection time for servo rows). align_t0() finds the
loop start on the wall clock from the commands recorded in both files.
"""
import argparse
import csv
import glob
import hashlib
import json
import math
import os
import subprocess
from pathlib import Path

import numpy as np

ROOT = Path("data")
OUT = Path("reports/DoanQuocKien/week-04/classroom_1030/analysis")
SERVO_RUNS = ("sup4_1", "sup5_1", "sup6_1", "t2_1", "t2_2", "t2_3", "t2_4", "t2_5")
ALL_RUNS = ("rehearsal_class_1", "rehearsal_class_2", "dry_negative_1", "dry_positive_1", "sup1_1", "sup2_1", "dry_fix_1", "dbg_1", "sup3_1", "dbg2_1") + SERVO_RUNS
# DQK's tape answers, from reports/DoanQuocKien/week-04/classroom_1030/README.md (axes not recorded; measured at the end of the run, i.e. after the retract when STANDBY was reached)
TAPE_OFFSET = {"sup6_1": (-0.18, 0.19), "t2_1": (0.25, -0.10), "t2_2": None, "t2_3": (-0.31, 0.23), "t2_4": (-0.60, 0.53), "t2_5": (-0.60, 0.97)}
TAPE_NOTE = {"t2_2": "< 0.04 m (no components given)", "sup2_1": "(-0.8, -0.17) m, camera turned around (DR run)"}
# The ENDED line printed by deploy_live for each run (session transcript 2026-10-30): wall seconds from the loop start to the print, incl. about 2.3-2.8 s of teardown (0.4 s stop, SSH battery read, 1.2 s, beeps)
ENDED_S = {"sup1_1": 16.8, "sup2_1": 14.7, "dry_fix_1": 14.6, "dbg_1": 22.3, "sup3_1": 15.1, "dbg2_1": 14.3, "sup4_1": 20.4, "sup5_1": 18.1, "sup6_1": 16.0,
           "t2_1": 20.1, "t2_2": 17.9, "t2_3": 16.5, "t2_4": 18.0, "t2_5": 22.9}
# Week 2 glossy-floor steady speeds (reports/DoanQuocKien/week-02/classroom_1015/README.md, data/speed_runs = the same files): file -> battery V at the run
WEEK2_BATTERY = {"classroom_v0.4_1.csv": 12.09, "classroom_v0.5_1.csv": 12.14, "classroom_v0.6_1.csv": 12.13, "classroom_v0.7_1.csv": 12.18, "classroom_v0.7_2.csv": 12.17,
                 "classroom_v0.85_1.csv": 12.04, "classroom_v1_1.csv": 12.02, "lowbattery_10.97V_head_centre_v0.6_1.csv": 10.97}
STILL_TOL = 0.01          # rad: two bearings of a still robot are "the same" within this (still frames repeat to about 0.001-0.006 rad)


# ---------------------------------------------------------------- small helpers
def read_csv(path):
    with open(path, newline="") as f:
        return [{k: (v if k == "state" else float(v)) for k, v in r.items()} for r in csv.DictReader(f)]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def linfit(t, y):
    """-> (slope, standard error of the slope, residual std) of a least-squares line."""
    t, y = np.asarray(t, float), np.asarray(y, float)
    A = np.c_[t - t.mean(), np.ones_like(t)]
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    res = y - A @ coef
    s = float(np.sqrt(res @ res / max(1, len(t) - 2)))
    se = s / math.sqrt(float(((t - t.mean()) ** 2).sum())) if len(t) > 2 else float("nan")
    return float(coef[0]), se, s


def r3(x, n=3):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else round(float(x), n)


def summary_of(values):
    v = np.asarray([x for x in values if x is not None], float)
    if not len(v):
        return dict(n=0)
    return dict(n=int(len(v)), mean=r3(v.mean()), std=r3(v.std(ddof=1)) if len(v) > 1 else None, min=r3(v.min()), max=r3(v.max()),
                ci95_halfwidth=r3(1.96 * v.std(ddof=1) / math.sqrt(len(v))) if len(v) > 1 else None)


# ---------------------------------------------------------------- deploy runs: time alignment, pulses, drives
def _same(a, b):
    return abs(a[0] - b[0]) < 1e-6 and abs(a[1] - b[1]) < 2e-3


def align_t0(log, servo, window=0.6, grid_step=0.002):
    """Wall-clock time of log t = 0. Each command change in log.csv (at log time tc) must fall between the two servo.csv rows whose recorded command changes the same way: a vote over
    a fine grid of offsets around a first guess (the first drive) picks the offset most changes agree with. -> (t0, votes, changes matched)."""
    g = next(r["t"] for r in servo if r["cmd_v"] > 0) - next(r["t"] for r in log if r["cmd_v"] > 0)
    iv = []
    for i in range(1, len(log)):
        a, b, tc = (log[i - 1]["cmd_v"], log[i - 1]["cmd_w"]), (log[i]["cmd_v"], log[i]["cmd_w"]), log[i]["t"]
        if _same(a, b):
            continue
        for j in range(1, len(servo)):
            if abs(servo[j]["t"] - g - tc) > window:
                continue
            if _same((servo[j - 1]["cmd_v"], servo[j - 1]["cmd_w"]), a) and _same((servo[j]["cmd_v"], servo[j]["cmd_w"]), b):
                iv.append((servo[j - 1]["t"] - tc - g, servo[j]["t"] - tc - g))
                break
    grid = np.arange(-0.4, 0.4, grid_step)
    cnt = np.array([sum(lo <= x <= hi for lo, hi in iv) for x in grid])
    return g + float(np.median(grid[cnt == cnt.max()])), int(cnt.max()), len(iv)


def segments(log, pred):
    """Contiguous runs of log rows where pred(row) holds -> [(t_start, t_end, state of the first row)]; t_end = time of the first row after the run."""
    out, i = [], 0
    while i < len(log):
        if pred(log[i]):
            j = i
            while j < len(log) and pred(log[j]):
                j += 1
            out.append((log[i]["t"], log[j]["t"] if j < len(log) else log[-1]["t"] + 0.033, log[i]["state"]))
            i = j
        else:
            i += 1
    return out


def spin_pulses(log):
    """Spin commands (v = 0, |w| > 0.3) -> [(start, end, sign, state, next command change after the end)]."""
    out = []
    for a, e, st in segments(log, lambda r: r["cmd_v"] == 0 and abs(r["cmd_w"]) > 0.3):
        sign = int(np.sign(next(r["cmd_w"] for r in log if r["t"] >= a)))
        nxt = next((r["t"] for r in log if r["t"] > e and (r["cmd_v"] != 0 or abs(r["cmd_w"]) > 1e-9)), log[-1]["t"])
        out.append((a, e, sign, st, nxt))
    return out


def pulse_turns(log, servo, t0):
    """Still-to-still bearing change of the followed board per spin pulse. before = median bearing in [start - 0.35, start + 0.10] (all rows within STILL_TOL of the last one),
    after = median in [end + 0.25, next command + 0.10] (robot still: the command between is 0). turn = -(after - before): the board's bearing moves opposite to the robot's turn.
    Also per pulse: the latest receipt time after the pulse START that still shows the before value (lower bound of video latency + motor start) and the earliest after the pulse END
    that shows the after value (upper bound of video latency + the coast to a stop)."""
    ts = np.array([r["t"] - t0 for r in servo])
    b = np.array([r["bearing_rad"] for r in servo])
    rg = np.array([r["range_m"] for r in servo])
    out = []
    for ps, pe, sign, st, nxt in spin_pulses(log):
        moving_before = [q["t"] for q in log if q["t"] < ps and (q["cmd_v"] != 0 or abs(q["cmd_w"]) > 1e-9)]
        still_before = ps - (moving_before[-1] + 0.033) if moving_before else ps
        if still_before < 0.4 and moving_before:
            continue                               # the robot was moving (e.g. driving) right before: no still "before" bearing
        pre = (ts >= ps - 0.35) & (ts <= ps + 0.10)
        post = (ts >= pe + 0.25) & (ts <= nxt + 0.10)
        if pre.sum() < 1 or post.sum() < 1:
            continue
        bp, ba = b[pre], b[post]
        if np.ptp(bp) > 2 * STILL_TOL or np.ptp(ba) > 2 * STILL_TOL:
            continue                               # not still at one of the ends
        before, after = float(np.median(bp)), float(np.median(ba))
        after_pulse = ts >= ps
        lb = [t - ps for t, v in zip(ts[after_pulse], b[after_pulse]) if abs(v - before) < STILL_TOL and t <= pe + 1.0]
        ub = [t - pe for t, v in zip(ts[ts >= pe], b[ts >= pe]) if abs(v - after) < STILL_TOL and t <= nxt + 0.10]
        out.append(dict(start=r3(ps), dur=r3(pe - ps), sign=sign, state=st, before=r3(before), after=r3(after), turn_rad=r3(-(after - before), 4),
                        range_m=r3(float(np.median(rg[pre]))), latest_unchanged_after_start=r3(max(lb)) if lb else None,
                        earliest_final_after_end=r3(min(ub)) if ub else None))
    return out


def model_turn(model, sign, dur):
    return model.body_speeds(0.0, 0.45 * sign)[1] * dur


def drive_fits(log, servo, t0, model, settle=0.8, lat=0.15):
    """Per drive segment (cmd_v > 0) with the board in view: range slope over [start + settle, end + lat] -> speed (corrected by the cosine of the mean bearing), and the heading drift
    the steering had to cancel: drift rate = -db/dt - mean(model turn rate of the steering command) + mean(v sin(b) / r)."""
    ts = np.array([r["t"] - t0 for r in servo])
    b = np.array([r["bearing_rad"] for r in servo])
    rg = np.array([r["range_m"] for r in servo])
    out = []
    for a, e, st in segments(log, lambda r: r["cmd_v"] > 0):
        m = (ts >= a + settle) & (ts <= e + lat)
        if m.sum() < 8 or ts[m].max() - ts[m].min() < 0.8:
            continue
        slope, se, res = linfit(ts[m], rg[m])
        cosb = math.cos(float(np.mean(b[m])))
        v = -slope / cosb
        bslope, bse, _ = linfit(ts[m], b[m])
        cmds = [r for r in log if a + settle - lat <= r["t"] <= e]
        w_model = float(np.mean([model.body_speeds(r["cmd_v"], r["cmd_w"])[1] - model.body_speeds(r["cmd_v"], 0.0)[1] for r in cmds])) if cmds else 0.0
        geo = float(np.mean(v * np.sin(b[m]) / rg[m]))
        drift_rate = -bslope - w_model + geo
        pred = float(np.mean([model.body_speeds(r["cmd_v"], r["cmd_w"])[0] for r in cmds])) if cmds else float("nan")
        out.append(dict(start=r3(a), end=r3(e), n=int(m.sum()), span_s=r3(ts[m].max() - ts[m].min()), speed=r3(v, 4), speed_se=r3(se / cosb, 4), range_resid_std=r3(res),
                        mean_bearing=r3(float(np.mean(b[m]))), mean_steer_w=r3(float(np.mean([r["cmd_w"] for r in cmds])), 4) if cmds else None,
                        model_speed=r3(pred, 4), ratio_to_default_model=r3(v / pred) if pred else None,
                        drift_rad_per_s=r3(drift_rate, 4), drift_rad_per_m=r3(drift_rate / v, 3) if v > 0.05 else None))
    return out


def startup_lag(log, servo, t0):
    """speedfit.fit_start on the first long drive from rest whose start is in view: -> onset (receipt time of the first motion minus the command, = motor start lag + video latency), tau, S."""
    from tools.speedfit import fit_start
    ts = np.array([r["t"] - t0 for r in servo])
    rg = np.array([r["range_m"] for r in servo])
    for a, e, st in segments(log, lambda r: r["cmd_v"] > 0):
        if e - a < 2.0:
            continue
        m = (ts >= a - 0.6) & (ts <= e)
        if m.sum() < 15 or not ((ts >= a - 0.6) & (ts < a)).any():
            continue
        f = fit_start(ts[m] - a, rg[m])
        if f:
            return dict(segment_start=r3(a), onset_s=r3(f["t0"]), tau_s=r3(f["tau"]), steady_speed=r3(f["S"], 4), rms_m=r3(f["rms"]), n=f["n"])
    return None


def arrival(log, servo, t0, summary):
    """How the approach ended: 'board' (servo arrival: the pose is reset to the sweet spot) or 'dead_reckoning' (board not fresh, the DR goal tolerance 0.12 m);
    the last sighting before the vantage, the DR path driven after it, the final still range when the board stays in view."""
    tv = next((t for t, n in summary["events"] if n == "VANTAGE_REACHED"), None)
    if tv is None:
        return None
    ts = np.array([r["t"] - t0 for r in servo])
    rg = np.array([r["range_m"] for r in servo])
    before = ts <= tv + 0.05
    near = before & (ts >= tv - 0.6)
    mode = "board" if near.any() and float(rg[near][-1]) <= 0.9 else "dead_reckoning"      # servo arrival needs a fresh sighting (0.6 s) at or under the stop range
    last_t = float(ts[before].max()) if before.any() else None
    last_r = float(rg[before][ts[before].argmax()]) if before.any() else None
    blind = [r for r in log if last_t is not None and last_t <= r["t"] <= tv]
    blind_m = sum(math.hypot(b_["x_m"] - a_["x_m"], b_["y_m"] - a_["y_m"]) for a_, b_ in zip(blind, blind[1:]) if b_["cmd_v"] > 0 or a_["cmd_v"] > 0) if mode == "dead_reckoning" else 0.0
    still = (ts >= tv + 0.15) & (ts <= tv + 0.8)          # the first turn-to-centre pulse starts at once; an in-place turn hardly changes the range
    return dict(mode=mode, vantage_t=r3(tv), last_sighting_t=r3(last_t), last_sighting_range=r3(last_r), seconds_blind=r3(tv - last_t) if last_t is not None else None,
                dr_m_driven_blind=r3(blind_m), range_after_stop=r3(float(np.median(rg[still]))) if still.sum() else None, range_after_stop_n=int(still.sum()),
                overshoot_m=r3(0.87 - float(np.median(rg[still]))) if still.sum() and mode == "board" else None)


# ---------------------------------------------------------------- handshake rule replay (Part A trials)
def windowed_verify(times, flags, span=5.0, min_frames=6, frac=0.7):
    """deploy_live.WindowedHandshake on a list of answers: -> the first time the rule says in view, or None."""
    for i, t in enumerate(times):
        w = [f for tt, f in zip(times[:i + 1], flags[:i + 1]) if t - tt <= span]
        if len(w) >= min_frames and sum(w) / float(len(w)) >= frac:
            return t
    return None


def handshake_trials(folder=ROOT / "handshake" / "class_door"):
    res = json.loads((folder / "results.json").read_text())
    rows = []
    for tr in res["trials"]:
        files = sorted((folder / "trials" / tr["trial"]).glob("f*.jpg"))
        times = [float(p.stem.split("_")[1]) for p in files]
        scored = [t for t in times if t >= 1.5]
        flags = [c == "1" for c in tr["frame_flags"]]
        ok = len(scored) == len(flags)
        tv = windowed_verify(scored, flags) if ok else None
        rows.append(dict(trial=tr["trial"], kind=tr["kind"], frames_scored=tr["frames_scored"], fraction_in_view=tr["fraction_in_view"], times_matched=ok,
                         windowed_rule_verifies=tv is not None, windowed_rule_first_s=r3(tv)))
    acc = [r for r in rows if r["kind"] == "accept"]
    rej = [r for r in rows if r["kind"] == "reject"]
    return dict(primary=dict(correct_accepts=res["correct_accepts"], accepts=res["accepts"], correct_rejects=res["correct_rejects"], rejects=res["rejects"]),
                secondary_3_consecutive=res["secondary_3_consecutive"],
                windowed_5s_6_70=dict(correct_accepts=sum(r["windowed_rule_verifies"] for r in acc), accepts=len(acc), correct_rejects=sum(not r["windowed_rule_verifies"] for r in rej),
                                      rejects=len(rej), note="replayed offline on ALL trial frames (5-8 fps); live the detector answers fewer frames per second"),
                trials=rows)


# ---------------------------------------------------------------- motion_check runs (class_1, class_2)
def _tracker(anchors=None):
    from sentry.nav.localization import LocalizationTracker
    tr = LocalizationTracker(motion_calib=None, camera_calib="calib/camera.json", max_marker_distance_m=1e6)
    if anchors:
        tr.load_anchors_csv(anchors)
        tr.set_pose(0.0, 0.0, 0.0)
    return tr


def marker_series(frames):
    """[(t, image)] -> {marker id: [(t, range, bearing)]}"""
    tr = _tracker()
    out = {}
    for t, img in frames:
        for d in tr.detect_markers(img):
            out.setdefault(d.marker_id, []).append((t, d.distance_m, d.bearing_rad))
    return out


def motion_check_analysis(label, anchors, model):
    """The tool's own rest-pose analysis (functions of tools.motion_check, nothing written) plus a bearing-only analysis: per segment, the median bearing of each board in the
    1.2 s rest window before and after; a board seen at both rests gives turn = -(change of bearing); forward drives also give the range slope (speed) and the heading change
    from the board geometry (board in the robot frame before, forward distance from the range change, lateral assumed 0)."""
    from tools.motion_check import analyse, load_run, rest_poses
    run = ROOT / "motion_check" / label
    cmds, frames, segs, rest_s = load_run(run)
    poses = rest_poses(segs, frames, rest_s, lambda: _tracker(anchors), 2.2)
    tool_rows = analyse(segs, poses, cmds, model)
    series = marker_series(frames)
    info = json.loads((run / "segments.json").read_text())

    def med(mid, a, b):
        pts = [(r, br) for t, r, br in series.get(mid, []) if a <= t <= b]
        return (float(np.median([p[0] for p in pts])), float(np.median([p[1] for p in pts])), len(pts)) if len(pts) >= 3 else None
    rows = []
    for i, sg in enumerate(segs):
        prev_end = segs[i - 1]["t1"] + rest_s if i else sg["t0"]
        w_before, w_after = (max(prev_end - 1.2, sg["t0"] - 1.2), sg["t0"]), (sg["t1"] + rest_s - 1.2, sg["t1"] + rest_s)
        row = dict(name=sg["name"], kind=sg["kind"], dur=r3(sg["t1"] - sg["t0"]), boards_before=[], boards_after=[])
        for mid in sorted(series):
            pb, pa = med(mid, *w_before), med(mid, *w_after)
            if pb:
                row["boards_before"].append(mid)
            if pa:
                row["boards_after"].append(mid)
            if pb and pa:
                row.setdefault("by_board", {})[str(mid)] = dict(range_before=r3(pb[0]), range_after=r3(pa[0]), bearing_before=r3(pb[1]), bearing_after=r3(pa[1]),
                                                                turn_rad=r3(-(pa[1] - pb[1]), 4))
                if sg["kind"] == "forward":
                    x0, y0 = pb[0] * math.cos(pb[1]), pb[0] * math.sin(pb[1])
                    lat, th = 0.0, 0.0
                    for _ in range(3):                      # a constant-curvature path: lateral offset = forward * heading change / 2
                        f = x0 - math.sqrt(max(0.0, pa[0] ** 2 - (y0 - lat) ** 2))
                        th = math.atan2(y0 - lat, x0 - f) - pa[1]
                        lat = f * th / 2
                    row["by_board"][str(mid)].update(forward_m=r3(f), heading_change_rad=r3(th, 4), drift_rad_per_m=r3(th / f, 3) if f > 0.05 else None)
                    m = [(t, r) for t, r, br in series[mid] if sg["t0"] + 0.5 <= t <= sg["t1"] + 0.15]
                    if len(m) >= 6:
                        s, se, _ = linfit([p[0] for p in m], [p[1] for p in m])
                        row["by_board"][str(mid)].update(range_slope_speed=r3(-s, 4), range_slope_se=r3(se, 4), n_moving=len(m))
        if sg["kind"] != "forward" and "by_board" not in row and all(s_["kind"] != "forward" for s_ in segs[:i]):
            anc = {int(q["marker_id"]): (float(q["x_m"]), float(q["y_m"])) for q in csv.DictReader(open(anchors))}
            hb = [math.atan2(anc[m][1], anc[m][0]) - med(m, *w_before)[1] for m in row["boards_before"] if m in anc]
            ha = [math.atan2(anc[m][1], anc[m][0]) - med(m, *w_after)[1] for m in row["boards_after"] if m in anc]
            if hb and ha:                                  # robot assumed at the start point (0, 0): spins before the first drive only; board positions from the anchors CSV (partly ASSUMED)
                d = math.atan2(math.sin(ha[0] - hb[0]), math.cos(ha[0] - hb[0]))
                row["cross_board_turn_rad"] = r3(d, 4)
        rows.append(row)
    for r, tr_ in zip(rows, tool_rows):
        r["tool"] = tr_
        if r["kind"] != "forward":
            r["model_turn_rad"] = r3(model_turn(model, 1 if r["kind"] == "spin_left" else -1, r["dur"]), 4)
        else:
            r["model_forward_m"] = r3(model.body_speeds(0.55, 0.0)[0] * r["dur"], 4)
    return dict(label=label, battery_v=info.get("battery_v"), ended=info.get("ended"), segments=len(segs), frames=len(frames),
                frames_with_marker={str(k): len(v) for k, v in series.items()}, rows=rows)


# ---------------------------------------------------------------- furniture / camera geometry
def expected_row(geom, forward_m, u):
    """Rectified image row whose floor intersection (at column u) is forward_m ahead, by bisection; None if not on the floor."""
    lo, hi = 0.0, geom.size[1] - 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        p = geom.ground_point(u, mid)
        if p is None or p.forward_m > forward_m:
            lo = mid
        else:
            hi = mid
    p = geom.ground_point(u, hi)
    return hi if p is not None and abs(p.forward_m - forward_m) < 0.01 else None


def horizon_row(geom, u):
    lo, hi = 0.0, geom.size[1] - 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        cr, sr = math.cos(geom.roll), math.sin(geom.roll)
        du, dv = u - geom.K[0, 2], mid - geom.K[1, 2]
        down = (-sr * du + cr * dv) / geom.K[1, 1]
        if math.sin(geom.pitch) + math.cos(geom.pitch) * down > 0:
            hi = mid
        else:
            lo = mid
    return hi


def pitch_for_contact(geom, u, v, forward_m):
    """The pitch (deg, down +) that would put the floor point forward_m ahead at row v (same K, roll and height)."""
    from sentry.perception.camera import CameraGeometry  # noqa: F401  (geom is one)
    keep = geom.pitch
    lo, hi = -20.0, 20.0
    try:
        for _ in range(60):
            mid = (lo + hi) / 2
            geom.pitch = math.radians(mid)
            p = geom.ground_point(u, v)
            if p is None or p.forward_m > forward_m:
                lo = mid
            else:
                hi = mid
        return hi
    finally:
        geom.pitch = keep


def furniture_analysis(yolo=False):
    import cv2
    from sentry.config import load
    from sentry.perception.camera import CameraGeometry
    from sentry.perception.contact import ReflectionContactEstimator
    from tools.estimate_camera_tilt import undistorter
    from tools.self_pose import collect
    pose_path = "calib/camera_pose_self_1030_2.json"
    geom = CameraGeometry.from_files("calib/camera.json", pose_path)
    cfg = load()
    est = ReflectionContactEstimator(cfg["obstacle"])
    K, und = undistorter(json.load(open("calib/camera.json")))
    out = dict(pose_file=pose_path, pose_pitch_down_deg=json.loads(Path(pose_path).read_text())["pitch_down_deg"], principal_row=r3(geom.K[1, 2], 1), fy=r3(geom.K[1, 1], 1))
    u = 272.0
    out["horizon_row_at_u272"] = r3(horizon_row(geom, u), 1)
    out["expected_contact_row_u272"] = {str(d): r3(expected_row(geom, d, u), 1) for d in (0.6, 1.0, 1.2, 1.5, 2.0, 2.4, 3.0)}
    sens = {}
    for d in (1.2, 2.4):
        v = expected_row(geom, d, u)
        p1 = geom.ground_point(u, v + 1.0)
        sens[str(d)] = dict(m_per_px=r3(d - p1.forward_m, 3) if p1 else None)
        keep = geom.pitch
        geom.pitch = keep + math.radians(1.0)
        p2 = geom.ground_point(u, v)
        geom.pitch = keep
        sens[str(d)]["m_per_deg_pitch"] = r3(d - p2.forward_m, 3) if p2 else None
    out["sensitivity_at_pose"] = sens
    per = {}
    for label, tape in (("chair_1.2m", 1.2), ("chair_2.4m", 2.4)):
        res = json.loads((ROOT / "furniture" / label / "result.json").read_text())
        files = sorted((ROOT / "furniture" / label / "frames").glob("*.jpg"))
        imgs = [cv2.imread(str(p)) for p in files]
        pitches, rolls, _ = collect(imgs, K, und, 0.15, 0.132, 0.100)        # the ArUco page standing on the floor next to the chair (page bottom on the floor: ASSUMED)
        d = dict(tape_m=tape, frames=len(imgs), frames_with_detection=res["frames_with_detection"], marker_pitch_frames=len(pitches),
                 marker_pitch_down_deg=r3(float(np.median(pitches)), 2) if pitches else None, marker_pitch_spread_deg=r3(float(np.std(pitches)), 2) if pitches else None,
                 marker_roll_deg=r3(float(np.median(rolls)), 2) if rolls else None)
        boxes = [o["xyxy"] for r in res["rows"] for o in r if o["cls"] == 56]
        if boxes:
            bx = np.median(np.array(boxes, float), axis=0)
            d["chair_box_median_xyxy"] = [r3(x, 1) for x in bx]
            d["box_bottom_ground_at_pose"] = None if geom.ground_point((bx[0] + bx[2]) / 2, bx[3]) is None else r3(geom.ground_point((bx[0] + bx[2]) / 2, bx[3]).forward_m)
            d["pitch_that_puts_box_bottom_at_tape_deg"] = r3(pitch_for_contact(geom, (bx[0] + bx[2]) / 2, bx[3], tape), 2)
            contacts = []
            for img, r in zip(imgs, res["rows"]):
                for o in r:
                    if o["cls"] == 56:
                        c = est(geom.undistort(img), tuple(float(x) for x in o["xyxy"]), geom.valid)
                        contacts.append(None if c is None else r3(c.v, 1))
            d["reflection_contact_rows"] = contacts
            d["box_width_px"], d["box_height_px"] = r3(bx[2] - bx[0], 1), r3(bx[3] - bx[1], 1)
            d["implied_chair_width_m_pinhole"] = r3((bx[2] - bx[0]) / geom.K[0, 0] * tape)
        per[label] = d
        if yolo:
            from ultralytics import YOLO
            m = YOLO("data/models/yolov8n.pt")
            found = []
            for img in imgs:
                r = m.predict(geom.undistort(img), imgsz=640, conf=0.05, classes=[56, 57, 59, 60], verbose=False, device="cpu")[0].boxes
                found.append([dict(cls=int(c), conf=r3(float(p), 2), xyxy=[r3(float(x), 0) for x in b]) for b, c, p in zip(r.xyxy.cpu().numpy(), r.cls.cpu().numpy(), r.conf.cpu().numpy())])
            d["yolo_conf_0.05"] = found
    out["labels"] = per
    if "chair_1.2m" in per and per["chair_1.2m"].get("marker_pitch_down_deg") is not None:
        keep = geom.pitch
        geom.pitch = math.radians(per["chair_1.2m"]["marker_pitch_down_deg"])
        bx = per["chair_1.2m"]["chair_box_median_xyxy"]
        p = geom.ground_point((bx[0] + bx[2]) / 2, bx[3])
        out["box_bottom_ground_with_marker_pitch_1.2m"] = r3(p.forward_m) if p else None
        out["expected_contact_row_u272_marker_pitch"] = {str(dd): r3(expected_row(geom, dd, u), 1) for dd in (1.2, 2.4)}
        cr = [c for c in per["chair_1.2m"]["reflection_contact_rows"] if c is not None]
        if cr:
            q = geom.ground_point((bx[0] + bx[2]) / 2, float(np.median(cr)))
            out["reflection_contact_ground_with_marker_pitch_1.2m"] = r3(q.forward_m) if q else None
        out["sensitivity_at_marker_pitch"] = {str(dd): dict(m_per_px=r3(dd - geom.ground_point(u, expected_row(geom, dd, u) + 1.0).forward_m, 3)) for dd in (1.2, 2.4)}
        geom.pitch = keep
    return out


def frame_quality(run, t0, t_end):
    """Approach frames of a run: share with board id 1 detected, mean grey level and sharpness (variance of the Laplacian), first and second half of the approach."""
    import cv2
    tr = _tracker()
    files = [f for f in sorted((ROOT / "deploy" / run / "frames").glob("*.jpg")) if 0 <= float(f.stem) - t0 <= t_end]
    out = {}
    for half, fs in (("first_half", files[:len(files) // 2]), ("second_half", files[len(files) // 2:])):
        det, grey, sharp = 0, [], []
        for f in fs:
            img = cv2.imread(str(f))
            g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            grey.append(float(g.mean()))
            sharp.append(float(cv2.Laplacian(g, cv2.CV_64F).var()))
            det += any(d.marker_id == 1 for d in tr.detect_markers(img))
        out[half] = dict(frames=len(fs), share_with_board2=r3(det / max(1, len(fs))), grey_mean=r3(float(np.mean(grey)), 1) if grey else None,
                         sharpness_median=r3(float(np.median(sharp)), 1) if sharp else None)
    return out


def deploy_frame_pitch(run, max_frames=400):
    """Camera pitch from board 2 in the run's own frames (the page stands on the floor: ASSUMED): indicative, the robot moves in most frames."""
    import cv2
    from tools.estimate_camera_tilt import undistorter
    from tools.self_pose import collect
    files = sorted((ROOT / "deploy" / run / "frames").glob("*.jpg"))[:max_frames]
    if not files:
        return None
    K, und = undistorter(json.load(open("calib/camera.json")))
    p, r, _ = collect((cv2.imread(str(f)) for f in files), K, und, 0.15, 0.132, 0.100, 1)
    return dict(frames=len(files), accepted=len(p), pitch_down_deg=r3(float(np.median(p)), 2) if p else None, spread_deg=r3(float(np.std(p)), 2) if p else None)


# ---------------------------------------------------------------- 8a: does --motion-session block the marker fixes? (replay of the control loop with a fake fix feed)
def fix_gating_replay(session=None, seconds=12.0):
    from sentry.app.deploy_runner import DeployRunner, DeploySettings
    from sentry.app.state_machine import StateMachine, StateMachineConfig
    from sentry.nav.wheel_model import WheelModel
    from tools.deploy_live import control_loop

    class Speaker:
        def play(self, clip):
            pass
    clock = {"t": 1000.0}
    model = WheelModel.from_session(session) if session else WheelModel()
    sm = StateMachine(StateMachineConfig())
    runner = DeployRunner(sm, Speaker(), vantage_xy=(0.0, -1.8), centre_xy=(-2.0, -1.8), settings=DeploySettings())
    feed = {"n": 0, "last": 0.0}

    def get_fix():                     # a still robot at the start seeing a board: a new marker pose every 0.2 s (as MarkerFix.measure would publish)
        if clock["t"] - feed["last"] >= 0.2:
            feed["n"] += 1
            feed["last"] = clock["t"]
        return (feed["n"], 0.0, 0.0, 0.0, 1.4) if feed["n"] else None
    end = {"reason": None}
    control_loop(runner, model, {"v": 0, "w": 0, "t": 0}, end, lambda now: False, lambda now: None, seconds,
                 clock=lambda: clock["t"], sleep=lambda s: clock.__setitem__("t", clock["t"] + 1 / 30.0), get_fix=get_fix)
    return dict(session=session, fixes_applied=end["fixes"], fix_feed_published=feed["n"], end=end["reason"])


def marker_fix_on_frames(run, anchors="data/anchors_class_1030b.csv", max_range_m=1.5):
    """sentry.nav.marker_fix.MarkerFix (as deploy_live --anchors) over a run's saved frames: does the measurement give fixes on this approach path?"""
    import cv2
    from sentry.nav.marker_fix import MarkerFix
    mf = MarkerFix(anchors, max_range_m=max_range_m)
    fs = sorted((ROOT / "deploy" / run / "frames").glob("*.jpg"))
    ok = [g for g in (mf.measure(cv2.imread(str(f))) for f in fs) if g]
    return dict(frames=len(fs), fixes=len(ok), last_fix_xy_yaw=[r3(ok[-1][1]), r3(ok[-1][2]), r3(ok[-1][3])] if ok else None)


# ---------------------------------------------------------------- catalogue
def git_tracked():
    try:
        out = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True).stdout.split("\n")
    except Exception:
        return set(), {}
    tracked = set(out)
    hashes = {}
    for p in tracked:
        if p.startswith("reports/DoanQuocKien/week-04/classroom_1030/") and p.endswith((".csv", ".json")) and "/analysis/" not in p and os.path.exists(p):
            hashes[sha256(p)] = p
    return tracked, hashes


def _span_csv(path):
    try:
        rows = read_csv(path)
    except Exception:
        return len(open(path, encoding="utf-8", errors="replace").read().splitlines()) - 1, None
    ts = [r["t"] for r in rows if isinstance(r.get("t"), float)]
    return len(rows), (r3(ts[-1] - ts[0], 2) if len(ts) > 1 else None)


def catalogue():
    tracked, committed = git_tracked()
    rows = []

    def add(path, run, what):
        p = Path(path)
        if p.is_dir():
            files = [f for f in p.rglob("*") if f.is_file()]
            names = sorted(f.stem for f in files if f.suffix == ".jpg")
            span = None
            try:
                tt = [float(n.split("_")[-1]) for n in names if "." in n.split("_")[-1]]
                span = r3(max(tt) - min(tt), 1) if len(tt) > 1 else None
            except ValueError:
                pass
            rows.append(dict(path=p.as_posix(), kind="folder", run=run, what=what, bytes=sum(f.stat().st_size for f in files), files=len(files), rows_or_frames=len(names),
                             time_span_s=span, sha256="", storage="local only (data/ is git-ignored)", privacy="robot/ESP32 video: may show people; never copy" if names else ""))
            return
        if not p.exists():
            rows.append(dict(path=p.as_posix(), kind="MISSING", run=run, what=what, bytes=0, files=0, rows_or_frames="", time_span_s="", sha256="", storage="", privacy=""))
            return
        n, span = _span_csv(p) if p.suffix == ".csv" else ("", None)
        h = sha256(p)
        posix = p.as_posix()
        storage = "committed" if posix in tracked else ("local only; identical copy committed: " + committed[h] if h in committed else "local only")
        rows.append(dict(path=posix, kind=p.suffix[1:], run=run, what=what, bytes=p.stat().st_size, files=1, rows_or_frames=n, time_span_s=span, sha256=h, storage=storage, privacy=""))

    for run in sorted(os.listdir(ROOT / "deploy")):
        for f, what in (("summary.json", "run summary (events, battery, handshake counts)"), ("log.csv", "30 Hz control log: t, DR pose, command, state, handshake flag"),
                        ("servo.csv", "board id 1 sightings: wall t, range, bearing, command"), ("frames", "robot video, JPEG q80, name = wall time at receipt")):
            if (ROOT / "deploy" / run / f).exists():
                add(ROOT / "deploy" / run / f, run, what)
    for lab in sorted(os.listdir(ROOT / "motion_check")):
        for f, what in (("commands.csv", "commands as sent (perf_counter t, v, w)"), ("segments.json", "segment times, rest, battery, end"),
                        ("summary.json", "tool result (rest-pose rows, fit refused)"), ("frames", "robot video ~10 fps, name = index_perf_counter")):
            add(ROOT / "motion_check" / lab / f, "motion_check " + lab, what)
    for lab in sorted(os.listdir(ROOT / "furniture")):
        add(ROOT / "furniture" / lab / "result.json", "furniture " + lab, "detector result per frame (tools/furniture_check.py)")
        add(ROOT / "furniture" / lab / "frames", "furniture " + lab, "robot frames, robot still")
    for f in ("results.json", "results_run1_primary.json", "trials.json", "eval_rerun.log"):
        add(ROOT / "handshake" / "class_door" / f, "Part A handshake (classroom door)", "handshake_test result / trial list / rerun log")
    for f in ("ref", "sweep", "trials"):
        add(ROOT / "handshake" / "class_door" / f, "Part A handshake (classroom door)", "ESP32 frames (" + f + ")")
    add(ROOT / "handshake" / "cafe_arch" / "results.json", "handshake rehearsal (cafe, 2026-10-28)", "handshake_test result")
    add(ROOT / "entrance" / "class_door" / "entrance.json", "entrance enrolment (classroom door)", "robot-eye entrance reference config")
    add(ROOT / "entrance" / "class_door" / "robot_00.jpg", "entrance enrolment (classroom door)", "one robot frame of the door (local; may show people)")
    for f in sorted(glob.glob(str(ROOT / "speed_runs" / "*.csv"))):
        add(f, "Week 2 speed runs 2026-10-15 (glossy)", "marker range per frame during a straight drive")
    for f, what in (("summary.json", "explore_live dry run 2026-10-30 09:48 (robot still, pose file rugged_1018, ended no_frame)"), ("log.csv", "explore_live log"), ("grid.npz", "explore map")):
        add(ROOT / "explore" / "class_dry_1" / f, "explore class_dry_1 (2026-10-30)", what)
    for f in sorted(glob.glob(str(ROOT / "turn_runs" / "*.csv"))):
        add(f, "Week 2 turn runs 2026-10-15 (glossy)", "marker heading per frame during an in-place turn")
    for d in sorted(glob.glob(str(ROOT / "dr_path" / "*"))):
        for f in ("commands.csv", "summary.json", "frames"):
            add(Path(d) / f, "dr_path " + Path(d).name, "Week 3 dead-reckoning run")
    for f in sorted(glob.glob(str(ROOT / "anchors_class_1030*.csv")) + glob.glob(str(ROOT / "dr_anchors_*.csv"))):
        add(f, "anchors", "board positions (marker_id, x, y, z, yaw) in the start frame; 1030: partly tape, partly assumed")
    for f in ("calib/motion.json", "calib/camera.json", "calib/motion_session_1030_provisional.json") + tuple(sorted(glob.glob("calib/camera_pose_*.json"))):
        add(f, "calibration", "calibration file")
    for f in ("reports/DoanQuocKien/week-02/motion_runs.csv", "reports/DoanQuocKien/week-02/motion_v07_rugged_tape.csv"):
        add(f, "Week 2 tape runs", "tape-measured drives/turns")
    return rows


# ---------------------------------------------------------------- speed vs battery
def week2_speeds():
    from tools.speedfit import fit_start
    out = []
    for f in sorted(glob.glob(str(ROOT / "speed_runs" / "*.csv"))):
        name = os.path.basename(f)
        if name not in WEEK2_BATTERY:
            continue
        rows = read_csv(f)
        drive = [r for r in rows if r["cmd_v"] > 0]
        if not drive:
            continue
        v = drive[0]["cmd_v"]
        t_stop = drive[-1]["t"]
        fit = fit_start([r["t"] for r in rows], [r["range_m"] for r in rows], t_stop)
        out.append(dict(file=name, v=v, motor=r3(v * 0.3, 4), battery_v=WEEK2_BATTERY[name], steady_speed=r3(fit["S"], 4) if fit else None, tau_s=r3(fit["tau"]) if fit else None,
                        rms_m=r3(fit["rms"]) if fit else None, n=fit["n"] if fit else 0))
    return out


def fit_m0_vs_battery(points, k=1.64):
    """points: [(battery V, motor, speed m/s, weight)] -> m0(V) = a + b (V - 11.5) by weighted least squares with k fixed (the Week 2 slope); and k(V) with m0 fixed 0.038."""
    V = np.array([p[0] for p in points])
    m0 = np.array([p[1] - p[2] / k for p in points])
    wts = np.array([p[3] for p in points])
    A = np.c_[np.ones_like(V), V - 11.5]
    W = np.sqrt(wts)
    coef, *_ = np.linalg.lstsq(A * W[:, None], m0 * W, rcond=None)
    res = m0 - A @ coef
    kk = np.array([p[2] / (p[1] - 0.038) for p in points])
    B = np.c_[np.ones_like(V), V - 11.5]
    kc, *_ = np.linalg.lstsq(B * W[:, None], kk * W, rcond=None)
    return dict(m0_at_11_5=float(coef[0]), m0_per_volt=float(coef[1]), m0_resid_std=float(res.std(ddof=2)) if len(res) > 2 else None,
                k_at_11_5=float(kc[0]), k_per_volt=float(kc[1]), n=len(points))


def bootstrap_m0(points, n=2000, seed=1030):
    rng = np.random.default_rng(seed)
    a, b = [], []
    for _ in range(n):
        s = [points[i] for i in rng.integers(0, len(points), len(points))]
        if len(set(p[0] for p in s)) < 3:
            continue
        f = fit_m0_vs_battery(s)
        a.append(f["m0_at_11_5"])
        b.append(f["m0_per_volt"])
    return dict(m0_at_11_5_ci95=[r3(np.percentile(a, 2.5), 4), r3(np.percentile(a, 97.5), 4)], m0_per_volt_ci95=[r3(np.percentile(b, 2.5), 4), r3(np.percentile(b, 97.5), 4)], resamples=len(a))


# ---------------------------------------------------------------- main
def deploy_analysis(model, prov):
    runs = {}
    for run in ALL_RUNS:
        d = ROOT / "deploy" / run
        s = json.loads((d / "summary.json").read_text())
        log = read_csv(d / "log.csv")
        ev = {n: t for t, n in s["events"]}
        r = dict(battery_start=s["battery_v_start"], battery_end=s["battery_v_end"], end_reason=s["end_reason"], dry_run=s["dry_run"], no_robot=s["no_robot"],
                 loop_last_t=log[-1]["t"], ended_print_s=ENDED_S.get(run), vantage_t=ev.get("VANTAGE_REACHED"), verified_t=ev.get("ESP32_VERIFIED"),
                 standby_t=next((t for t, st in s["state_changes"] if st == "STANDBY"), None), handshake_frames=s["handshake"]["frames"],
                 handshake_in_view_frames=s["handshake"]["in_view_frames"], marker_fixes=s.get("marker_fixes"), anchors=s.get("anchors"))
        r["prompt_to_verified_s"] = r3(r["verified_t"] - r["vantage_t"]) if r["verified_t"] and r["vantage_t"] else None
        r["wait_camera_s"] = r3((r["verified_t"] or log[-1]["t"]) - r["vantage_t"]) if r["vantage_t"] is not None else None
        r["detector_answers_per_s"] = r3(s["handshake"]["frames"] / (log[-1]["t"] + 0.4), 2)
        pulses_ = spin_pulses(log)
        r["approach_spin_pulses"] = sum(1 for p in pulses_ if p[3] == "APPROACH_VANTAGE")
        r["approach_drive_s"] = r3(sum(e - a for a, e, st in segments(log, lambda q: q["cmd_v"] > 0) if st == "APPROACH_VANTAGE"))
        r["approach_drive_segments"] = sum(1 for a, e, st in segments(log, lambda q: q["cmd_v"] > 0) if st == "APPROACH_VANTAGE")
        r["first_drive_t"] = next((q["t"] for q in log if q["cmd_v"] > 0), None)
        r["pulse_pattern_ok"] = all(0.15 <= e - a <= 0.25 for a, e, sg, st, nx in pulses_ if nx - e > 0.3) if pulses_ else None
        r["longest_spin_command_s"] = r3(max((e - a for a, e, *_ in pulses_), default=0.0))
        if run in SERVO_RUNS:
            sv = read_csv(d / "servo.csv")
            t0, votes, matched = align_t0(log, sv)
            r["t0_wall"], r["align_votes"] = t0, "%d of %d" % (votes, matched)
            r["servo_sightings"] = len(sv)
            frames = sorted((d / "frames").glob("*.jpg"))
            r["robot_frames"] = len(frames)
            if frames:
                ft = [float(f.stem) for f in frames]
                r["robot_fps"] = r3(len(ft) / (ft[-1] - ft[0]), 1)
                r["first_frame_after_t0_s"] = r3(ft[0] - t0)
            r["first_sighting_t"] = r3(sv[0]["t"] - t0)
            ap = [x for x in sv if x["t"] - t0 <= (r["vantage_t"] or 1e9)]
            r["sightings_per_s_in_approach"] = r3(len(ap) / r["vantage_t"], 2) if r["vantage_t"] else None
            r["pulses"] = pulse_turns(log, sv, t0)
            r["drives"] = drive_fits(log, sv, t0, model)
            r["startup"] = startup_lag(log, sv, t0)
            r["arrival"] = arrival(log, sv, t0, s)
            r["tool_servo_motion"] = s.get("servo_motion")
            ds = [x for x in r["drives"] if x["n"] >= 15 and x["span_s"] >= 2.0]
            if ds:
                w = np.array([1 / x["speed_se"] ** 2 for x in ds])
                sp = np.array([x["speed"] for x in ds])
                r["speed_weighted"] = r3(float((w * sp).sum() / w.sum()), 4)
                r["speed_weighted_se"] = r3(float(1 / math.sqrt(w.sum())), 4)
                r["speed_segments_used"] = len(ds)
                dr = [x["drift_rad_per_m"] for x in ds if x["drift_rad_per_m"] is not None]
                r["drift_rad_per_m_mean"] = r3(float(np.mean(dr)), 3) if dr else None
        runs[run] = r
    return runs


def plots(res, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.2))
    sp = [(r["battery_mean"], r["speed"], r["speed_se"], k) for k, r in res["speed_vs_battery"]["today_runs"].items()]
    for V, s, se, k in sp:
        ax[0].errorbar(V, s, yerr=1.96 * se, fmt="o", color="#2a6fbb", capsize=3)
        ax[0].annotate(k.replace("_1", ""), (V, s), textcoords="offset points", xytext=(4, 4), fontsize=8)
    m = res["speed_vs_battery"]["fit_today_only"]
    VV = np.linspace(11.25, 11.75, 20)
    ax[0].plot(VV, 1.64 * (0.165 - (m["m0_at_11_5"] + m["m0_per_volt"] * (VV - 11.5))), "-", color="#888", label="m0(V) fit to these runs, k = 1.64")
    ax[0].axhline(1.64 * (0.165 - 0.038), ls="--", color="#c55", label="Week 2 model at v = 0.55 (12.0-12.2 V)")
    ax[0].set_xlabel("battery (V, mean of start and end)")
    ax[0].set_ylabel("steady speed from board 2 range (m/s)")
    ax[0].set_title("Drive speed at v = 0.55 vs battery (95 % CI)")
    ax[0].legend(fontsize=8)
    used = {(a, b) for a, b in res["turning"]["used"]}
    P = [p for k, r in res["deploy"].items() for p in r.get("pulses", []) if (k, p["start"]) in used]
    for sign, c in ((-1, "#2a6fbb"), (1, "#d08020")):
        xs = [res["deploy"][k]["battery_start"] for k, r in res["deploy"].items() for p in r.get("pulses", []) if p["sign"] == sign and (k, p["start"]) in used]
        ys = [abs(p["turn_rad"]) for k, r in res["deploy"].items() for p in r.get("pulses", []) if p["sign"] == sign and (k, p["start"]) in used]
        ax[1].plot(xs, ys, "o", color=c, alpha=0.75, label="right pulses" if sign < 0 else "left pulses")
    ax[1].axhline(res["turning"]["model_turn_per_pulse_0_2s"]["default_wheel_model"], ls="--", color="#c55", label="default wheel model, 0.2 s")
    ax[1].set_xlabel("battery at run start (V)")
    ax[1].set_ylabel("turn per 0.2 s spin pulse (rad, still to still)")
    ax[1].set_title("Spin pulse w = 0.45 for 0.2 s, approach pulses after a still pause (n = %d)" % len(P), fontsize=9)
    ax[1].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out / "speed_and_turn_vs_battery.png", dpi=110)
    plt.close(fig)


def write_models(res, out):
    """speed_vs_battery.json and floor_model_1030.json from the results (provisional, this floor and this pack only)."""
    sv, tu = res["speed_vs_battery"], res["turning"]
    f = sv["fit_today_only"]
    m0 = lambda V: f["m0_at_11_5"] + f["m0_per_volt"] * (V - 11.5)
    kV = lambda V: f["k_at_11_5"] + f["k_per_volt"] * (V - 11.5)
    table = [dict(battery_v=V, m0=r3(m0(V), 4), speed_v055_option_a=r3(1.64 * (0.165 - m0(V)), 4), k_option_b=r3(kV(V), 3), speed_v055_option_b=r3(kV(V) * (0.165 - 0.038), 4),
                  spin_rad_s_w045_option_a=r3(2 * 1.64 * (0.135 - m0(V)) / 0.137, 3), spin_rad_s_w045_option_b=r3(2 * kV(V) * (0.135 - 0.038) / 0.137, 3))
             for V in (11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8)]
    speed = dict(label="PROVISIONAL: classroom glossy tile, 2026-10-30, one JetBot, one pack; fitted on 5 runs at ONE command (v = 0.55, motor 0.165) between 11.28 and 11.70 V",
                 law="wheel speed = k * (|motor| - m0), motor = mix(v, w) * 0.3 after the dead zone 0.12 (sentry/nav/wheel_model.py)",
                 data=sv["today_runs"], week2_published_steady_12V=sv["week2_published_steady"],
                 option_a_m0_of_v=dict(k=1.64, m0_at_11_5=r3(f["m0_at_11_5"], 4), m0_per_volt=r3(f["m0_per_volt"], 4), bootstrap=sv["bootstrap_today_only"]),
                 option_b_k_of_v=dict(m0=0.038, k_at_11_5=r3(f["k_at_11_5"], 3), k_per_volt=r3(f["k_per_volt"], 3)),
                 table=table, pearson_r_speed_vs_battery=sv["pearson_r_speed_vs_battery_today"],
                 combined_with_week2=dict(fit=sv["fit_k_fixed"], bootstrap=sv["bootstrap_today_plus_week2"],
                                          note="Week 2 (12.0-12.2 V, 2026-10-15) gives m0 = 0.038, HIGHER than today's 0.031 at 11.5 V: across sessions the offset did not grow as the battery fell; another day, possibly tyres/floor/robot state, cannot be separated"),
                 cannot_separate=["k(V) and m0(V): every run today used the same command (0.165 motor units), so options a and b predict the same 0.55 speed; they differ at other commands (see the spin columns: option a predicts a faster spin than b at low voltage)",
                                  "battery from time/order: the voltage fell monotonically during the session, so any drift over the morning (warm motors, floor dust) is confounded with the voltage",
                                  "the measured spin rate (no battery trend, r = %s over 14 pulses) is closer to option a's flat dependence than to b, but 14 short pulses cannot decide it" % tu["pearson_r_turn_vs_battery"]])
    (out / "speed_vs_battery.json").write_text(json.dumps(speed, indent=1))
    arr = [res["deploy"][k]["arrival"] for k in SERVO_RUNS if res["deploy"][k].get("arrival") and res["deploy"][k]["arrival"]["mode"] == "board"]
    ov = [a["overshoot_m"] for a in arr if a["overshoot_m"] is not None]
    mc = res.get("motion_check", {})
    open_drift = [b_["drift_rad_per_m"] for lab in mc.values() for r_ in lab["rows"] if r_["kind"] == "forward" for b_ in r_.get("by_board", {}).values() if b_.get("drift_rad_per_m") is not None]
    tvd = res.get("turn_vs_duration", {})
    fm = dict(label="PROVISIONAL floor model, measured on the classroom glossy tile floor on 2026-10-30 (one robot, one pack, 11.2-11.7 V). Not valid on other floors or below 11.2 V.",
              generated_by="python -m tools.analyse_classroom_1030", loader="tools/floor_model.py",
              wheel=dict(k=1.64, m0_at_11_5=r3(f["m0_at_11_5"], 4), m0_per_volt=r3(f["m0_per_volt"], 4), track=0.137, max_speed=0.3, min_pwm=0.12, valid_battery_v=[11.28, 11.70],
                         source="speed_vs_battery.json option a (k fixed at the Week 2 slope)"),
              turn=dict(rate_rad_per_s_at_w_0_45=tvd.get("rate_rad_per_s"), lag_s=tvd.get("lag_s"), n=tvd.get("n"), spin_durations_s=tvd.get("durations"),
                        pulse_0_2s_right=tu["right"], pulse_0_2s_left=tu["left"], left_right_note="not distinguishable: 12 right and 2 left pulses (0.2 s), 1 left + 1 right 0.4 s spin, 2 + 2 cross-board 0.8 s spins",
                        battery_correlation=tu["pearson_r_turn_vs_battery"]),
              startup=dict(drive_onset_s=res["startup"]["onset"], note="time from the drive command to the first range change in the received video = motor start + video latency (not separable)"),
              video=dict(latency_upper_bound_s=tu["latency"]["earliest_final_after_pulse_end_s"], still_after_pulse_start_s=tu["latency"]["per_pulse_unchanged"],
                         sim_latency_s=0.12, note="the sim value 0.12 s is a choice inside the measured bounds (<= 0.153 s on the best pulse; frames still unchanged 0.06-0.17 s after a pulse start). One pulse (sup5 1.4 s) looks like frames 0.5-0.7 s stale at a run start: probable, not proven"),
              drift=dict(closed_loop_steady_rad_per_m=res["drift"]["servo_segments"], open_loop_from_rest_rad_per_m=summary_of(open_drift), sign="left +",
                         sim_rad_per_m=0.45, note="0.45 = between the steady closed-loop mean 0.38 and the open-loop-from-rest mean; per-run spread is real, simulate it (e.g. normal, sd 0.12)"),
              stop=dict(overshoot_m=summary_of(ov), speed_m_s=0.22, equivalent_delay_s=r3(float(np.mean(ov)) / 0.22, 3) if ov else None,
                        rule="stop when range <= target + speed * 0.2 s (0.044 m at 0.22 m/s)"),
              camera=dict(pitch_down_deg_marker=dict(furniture_1_2m=res.get("furniture", {}).get("labels", {}).get("chair_1.2m", {}).get("marker_pitch_down_deg"),
                                                     deploy_runs={k: (v or {}).get("pitch_down_deg") for k, v in res.get("deploy_pitch", {}).items()}),
                          pose_file_pitch_deg=2.15, height_m=0.100))
    (out / "floor_model_1030.json").write_text(json.dumps(fm, indent=1))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--yolo", action="store_true")
    ap.add_argument("--no-frames", action="store_true", help="skip the analyses that read video frames (motion_check bearings, furniture, pitch)")
    a = ap.parse_args()
    from sentry.nav.wheel_model import WheelModel
    model, prov = WheelModel(), WheelModel.from_session("calib/motion_session_1030_provisional.json")
    OUT.mkdir(parents=True, exist_ok=True)
    res = dict(generated_by="python -m tools.analyse_classroom_1030", model_default=dict(k=model.k, m0=model.m0, track=model.track))
    res["deploy"] = deploy_analysis(model, prov)

    # ---- speed vs battery
    today = {}
    for k in SERVO_RUNS:
        r = res["deploy"][k]
        if r.get("speed_weighted"):
            today[k] = dict(battery_mean=r3((r["battery_start"] + r["battery_end"]) / 2, 3), speed=r["speed_weighted"], speed_se=r["speed_weighted_se"],
                            segments=r["speed_segments_used"], tool_ratio=(r["tool_servo_motion"] or {}).get("speed_ratio"))
    w2 = week2_speeds()
    w2_pub = [(0.5, 0.185), (0.6, 0.238), (0.7, 0.276), (0.85, 0.357), (1.0, 0.435)]       # Week 2 README steady speeds (v 0.4 left out: motor 0.12 = the dead zone); 0.7 = mean of 0.269 and 0.283
    pts = [(v["battery_mean"], 0.165, v["speed"], 1.0 / max(v["speed_se"], 0.003) ** 2) for v in today.values()]
    pts_all = pts + [(12.1, v * 0.3, s_, 1.0 / 0.006 ** 2) for v, s_ in w2_pub]
    sv = dict(today_runs=today, week2_refit_of_data_speed_runs=w2, week2_published_steady=[dict(v=v, motor=v * 0.3, speed=s_, battery_v="12.02-12.18") for v, s_ in w2_pub], fit_k_fixed=fit_m0_vs_battery(pts_all), fit_today_only=fit_m0_vs_battery(pts), bootstrap_today_plus_week2=bootstrap_m0(pts_all), bootstrap_today_only=bootstrap_m0(pts))
    corr = np.corrcoef([v["battery_mean"] for v in today.values()], [v["speed"] for v in today.values()])[0, 1] if len(today) > 2 else None
    sv["pearson_r_speed_vs_battery_today"] = r3(corr)
    res["speed_vs_battery"] = sv

    # ---- turning
    P = [dict(p, run=k, battery=res["deploy"][k]["battery_start"]) for k in SERVO_RUNS for p in res["deploy"][k].get("pulses", [])]
    full0 = [p for p in P if 0.18 <= p["dur"] <= 0.23 and p["state"] == "APPROACH_VANTAGE"]
    med = float(np.median([abs(p["turn_rad"]) for p in full0]))
    full = [p for p in full0 if p["turn_rad"] * p["sign"] > 0 and abs(p["turn_rad"]) <= 1.6 * med]
    anomalies = [p for p in P if p not in full]
    turn = dict(model_turn_per_pulse_0_2s=dict(default_wheel_model=r3(abs(model_turn(model, 1, 0.2)), 4), provisional_left=r3(abs(model_turn(prov, 1, 0.2)), 4),
                                               provisional_right=r3(abs(model_turn(prov, -1, 0.2)), 4), week2_turn_fit_7_2=r3(7.2 * (0.45 - 0.13) * 0.2, 4)),
                pulses_all=len(P), pulses_full_0_2s=len(full), excluded=anomalies, used=[[p["run"], p["start"]] for p in full],
                right=summary_of([abs(p["turn_rad"]) for p in full if p["sign"] < 0]), left=summary_of([abs(p["turn_rad"]) for p in full if p["sign"] > 0]),
                all_full=summary_of([abs(p["turn_rad"]) for p in full]),
                rate_per_commanded_s=summary_of([abs(p["turn_rad"]) / p["dur"] for p in full]),
                latency=dict(latest_unchanged_after_pulse_start_s=r3(max(p["latest_unchanged_after_start"] for p in full if p["latest_unchanged_after_start"] is not None)),
                             earliest_final_after_pulse_end_s=r3(min(p["earliest_final_after_end"] for p in full if p["earliest_final_after_end"] is not None)),
                             per_pulse_unchanged=summary_of([p["latest_unchanged_after_start"] for p in full]), per_pulse_final=summary_of([p["earliest_final_after_end"] for p in full])))
    vb = [(p["battery"], abs(p["turn_rad"])) for p in full]
    turn["pearson_r_turn_vs_battery"] = r3(np.corrcoef(*zip(*vb))[0, 1]) if len(vb) > 2 else None
    res["turning"] = turn
    starts = [res["deploy"][k]["startup"] for k in SERVO_RUNS if res["deploy"][k].get("startup")]
    res["startup"] = dict(runs={k: res["deploy"][k]["startup"] for k in SERVO_RUNS}, onset=summary_of([x["onset_s"] for x in starts]), tau=summary_of([x["tau_s"] for x in starts]))

    # ---- drift
    segs = [x for k in SERVO_RUNS for x in res["deploy"][k].get("drives", []) if x["n"] >= 15 and x["span_s"] >= 2.0 and x["drift_rad_per_m"] is not None]
    res["drift"] = dict(servo_segments=summary_of([x["drift_rad_per_m"] for x in segs]), mean_steer_w=summary_of([x["mean_steer_w"] for x in segs]),
                        per_run={k: res["deploy"][k].get("drift_rad_per_m_mean") for k in SERVO_RUNS})

    # ---- handshake, fixes
    res["handshake_part_a"] = handshake_trials()
    res["fix_gating"] = [fix_gating_replay(None), fix_gating_replay("calib/motion_session_1030_provisional.json")]

    # ---- frames
    if not a.no_frames:
        res["motion_check"] = {lab: motion_check_analysis(lab, anc, model) for lab, anc in (("class_1", "data/anchors_class_1030.csv"), ("class_2", "data/anchors_class_1030b.csv"))}
        mc_turns = [(r["dur"], abs(b_["turn_rad"])) for lab in res["motion_check"].values() for r in lab["rows"] if r["kind"] != "forward" for b_ in r.get("by_board", {}).values()]
        res["motion_check_turns_same_board"] = mc_turns
        cross = [(r["dur"], abs(r["cross_board_turn_rad"])) for lab in res["motion_check"].values() for r in lab["rows"] if r.get("cross_board_turn_rad") is not None]
        res["motion_check_turns_cross_board"] = cross
        mc_turns = mc_turns + cross
        res["furniture"] = furniture_analysis(a.yolo)
        res["deploy_pitch"] = {k: deploy_frame_pitch(k) for k in ("sup5_1", "sup6_1", "t2_1", "t2_3", "t2_5")}
        res["marker_fix_on_saved_frames"] = {k: marker_fix_on_frames(k) for k in ("sup6_1", "t2_2")}
        res["frame_quality"] = {k: frame_quality(k, res["deploy"][k]["t0_wall"], res["deploy"][k]["vantage_t"]) for k in SERVO_RUNS if res["deploy"][k].get("robot_frames")}
        # turn vs spin duration: deploy 0.2 s pulses + motion_check spins measured on one board (turn = rate * (T - lag))
        D = [(p["dur"], abs(p["turn_rad"])) for p in full] + mc_turns
        if len({round(d, 1) for d, _ in D}) >= 2:
            A = np.c_[[d for d, _ in D], np.ones(len(D))]
            coef, *_ = np.linalg.lstsq(A, [t for _, t in D], rcond=None)
            res["turn_vs_duration"] = dict(rate_rad_per_s=r3(coef[0]), intercept_rad=r3(coef[1], 4), lag_s=r3(-coef[1] / coef[0]) if coef[0] else None, n=len(D),
                                           durations=sorted({round(d, 2) for d, _ in D}))
    res["catalogue_rows"] = len(cat := catalogue())
    with open(OUT / "catalogue.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(cat[0]))
        w.writeheader()
        w.writerows(cat)
    (OUT / "results.json").write_text(json.dumps(res, indent=1, default=float))
    plots(res, OUT)
    write_models(res, OUT)
    print("wrote", OUT / "results.json", OUT / "catalogue.csv", OUT / "speed_and_turn_vs_battery.png")


if __name__ == "__main__":
    main()
