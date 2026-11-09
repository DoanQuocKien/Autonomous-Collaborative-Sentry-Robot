"""LIVE pursuit of one person with the JetBot (first version, 2026-11-05): robot video -> person detector + ByteTrack -> foot-point ground distance -> InterceptionController (PD pursuit at 1.2 m,
HOLD when the target stops) -> (v, w) over UDP, with the same safety interlock as tools.deploy_live. Supervised only: it does NOT avoid obstacles.

  python -m tools.pursue_live --label home_1 --camera-pose calib/camera_pose_self_<today>.json --dry-run            # robot connected, video processed, NO commands sent
  python -m tools.pursue_live --label home_1 --camera-pose calib/camera_pose_self_<today>.json                      # drives: hold R1 (e-stop armed: hold Start 1.5 s first)
  python -m tools.pursue_live --label try --camera-pose calib/camera_pose_self_<today>.json --replay data/some_frames   # no robot: images in a folder, commands only printed and logged

SAFETY (all of them apply, none can be turned off):
  * the robot moves only while R1 is held with the e-stop armed (latch file polled over SSH every 0.2 s; two failed polls stop the run); `--no-estop` does not exist here;
  * every command is legal for the motors (controllers.py) and the sender repeats a command only while it is fresh (0.25 s), then sends a stop; the robot's own watchdog is 0.3 s;
  * no person tracked for 0.6 s, or no fresh frame for 0.5 s: stop. A lost target for --lost-end-s (5 s) ends the run (no searching, no switching to another person);
  * feet cut off by the image bottom or no floor intersection: no translation, yaw centring only;
  * a start battery below --min-battery (11.4 V) refuses to start; run `python -m tools.self_pose` on today's floor first and pass its file as --camera-pose (a stale pitch gives wrong distances).
The target is the largest person within --lock-range (3.5 m) at the first valid frame, kept by its ByteTrack id. One person in the scene is the first test.

OUTPUT data/pursuit/<label>_<n>/: log.csv (one row per processed frame), summary.json (the T2 numbers of plan 4.3: fraction of tracked frames with the distance within 1.2 +/- 0.2 m and the box centre within +/- 10 % of the frame width,
hold events, end reason, battery). Video frames are NOT saved unless --save-frames (people are in them: local only, never committed).
"""
import argparse
import csv
import dataclasses
import json
import math
import os
import sys
import threading
import time
from pathlib import Path

import numpy as np

from sentry.nav.explore import fresh_command
from sentry.perception.body_range import iou, trunk_range
from sentry.perception.camera import GroundPoint

ESTOP_LATCH = "/home/jetbot/sentry/ESTOP"
MIN_BATTERY_V = 11.4
LINK_STALE_S = 0.5
OBS_STALE_S = 0.6
YAW_PULSE_S = 0.08                            # a yaw-only pulse is sent for at most this long (wall clock, enforced by the sender)
FRESH_S = 0.25                                # command freshness on the wire (sentry.nav.explore.fresh_command default)
DIST_MEDIAN_N = 5                             # frames in the median that decides the standoff dead band (the foot-row range jitters by 0.2 m when the robot starts or stops)
TRUNK_WINDOW = 10                             # causal median over the last frames of the trunk-based range (0.5 s at 20 fps)
TRUNK_IOU = 0.4                               # pose person matched to a tracked box by IoU
TIME_CAP_S = 0.25                             # an interval between two processed frames counts at most this much in the time-based fractions
CENTRE_TOL_WIDTH = 0.10                       # plan: bbox centre within +/- 10 % of the FULL frame width
MAX_PROCESS_S = 0.5                           # longer than this for one frame: stop instead of driving on it
FEET_MARGIN_PX = 3
YAW_DEADBAND = 0.10                           # |yaw_err| inside the +/-10 % centre band: no yaw-only command (the smallest legal turn, 0.45, is about 125 deg/s)
YAW_PULSE_PERIOD = 3                          # yaw-only commands: one frame on, two frames off (about 6 deg per pulse instead of 14+ deg bursts)
REACQ_YAW_GATE = 0.6                          # re-lock gate: the only person in view within this yaw_err (normalised, 0.6 = about 48 deg) and 1.0 m of the last position
REACQ_DIST_GATE_M = 1.0
REACQ_MAX_LOST_S = 3.0


COLS = ["t", "track_id", "dist_m", "forward_m", "left_m", "yaw_err", "feet_cut", "range_src", "foot_forward_m", "v_req", "w_req", "v", "w", "suppressed", "mode", "event", "tracks"]


def command_to_send(cmd, now):
    """-> (v, w) the sender may transmit at `now`. Freshness as everywhere (0.25 s), and a yaw-only command (a pulse) expires YAW_PULSE_S after it was computed,
    whatever the video does: a stalled next frame must not turn a one-frame pulse into 0.25 s of rotation (HNHL review of PR #99)."""
    if cmd["v"] == 0.0 and cmd["w"] != 0.0 and now - cmd["t"] > YAW_PULSE_S:
        return 0.0, 0.0
    return fresh_command(cmd["v"], cmd["w"], cmd["t"], now)


def save_run(out, label, rows, summary, saved):
    """Write log.csv, summary.json and (optionally) the frames into a NEW run directory <out>/<label>_<n>; -> the directory."""
    out_dir = Path(out)
    n = 1 + len(list(out_dir.glob(label + "_*"))) if out_dir.exists() else 1
    run_dir = out_dir / ("%s_%d" % (label, n))
    run_dir.mkdir(parents=True, exist_ok=True)
    with open(run_dir / "log.csv", "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=COLS)
        wr.writeheader()
        wr.writerows(rows)
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=1, allow_nan=False))
    if saved:
        (run_dir / "frames").mkdir(exist_ok=True)
        for t_, jpg in saved:
            (run_dir / "frames" / ("%.3f.jpg" % t_)).write_bytes(jpg)
    return run_dir


def foot_point(ground_point, undistort_points, xyxy, size, feet_row_offset_px=0.0):
    """-> (GroundPoint or None, feet_cut, yaw_err). The feet are the bottom centre of the person box (raw pixels, undistorted for the floor ray). yaw_err = (image centre - box centre) / half width, + = the person is to the LEFT.
    feet_cut: the box touches the bottom image edge, so its lower edge is not the floor contact.
    feet_row_offset_px: the detector box bottom sits a few pixels below the real floor contact (2.5-6 px measured on 2026-11-07, bare feet); the floor ray is taken that many pixels higher."""
    w, h = size
    x1, y1, x2, y2 = xyxy
    feet_cut = y2 >= h - FEET_MARGIN_PX
    (uf, vf), (uc, _) = undistort_points([[(x1 + x2) / 2.0, y2 - feet_row_offset_px], [(x1 + x2) / 2.0, (y1 + y2) / 2.0]])
    yaw_err = (w / 2.0 - uc) / (w / 2.0)
    gp = None if feet_cut else ground_point(float(uf), float(vf))
    return gp, feet_cut, float(yaw_err)


class Pursuit(object):
    """The pure decision logic (no hardware): feed it the tracked boxes of each frame, get (v, w) and a log row. Testable with fakes."""

    def __init__(self, controller, model, ground_point, undistort_points, size, lock_range_m=3.5, lost_stop_s=OBS_STALE_S, lost_end_s=5.0, feet_row_offset_px=0.0, integrate=True, trunk_fn=None):
        self.trunk_fn = trunk_fn                   # callable(kxy, kconf) -> (forward_m, left_m) or None; None = foot-row range only
        self._trunk_hist = {}                      # track id -> recent (forward, left) from the trunk length
        self.integrate = integrate                 # False in dry-run and replay: no command reaches the robot, so the dead-reckoned pose must not move
        self.ctl, self.model, self.ground_point, self.undistort_points, self.size = controller, model, ground_point, undistort_points, size
        self.lock_range_m, self.lost_stop_s, self.lost_end_s = lock_range_m, lost_stop_s, lost_end_s
        self.feet_row_offset_px = feet_row_offset_px
        self.target_id = None
        self.pose = [0.0, 0.0, 0.0]               # dead reckoning from the commands: the hold detector needs the robot's own motion
        self.cmd, self.t_prev, self.t_seen = (0.0, 0.0), None, None
        self.end_reason = None
        self.rows = []
        self.hold_events = []
        self.last_seen = None                      # (yaw_err, distance or None) of the target when last seen
        self._yaw_phase = 0
        self._dist_hist = []                       # recent ranges of the target (m), for the dead band

    def _advance(self, t):
        """Integrate the command the robot actually received since the last frame: it stays on the wire for its freshness window (FRESH_S, a yaw pulse only YAW_PULSE_S),
        whatever the frame gap, then the robot is stopped. Sub-stepped so a long interval stays accurate. Simulated pose (commands, not odometry)."""
        if self.t_prev is not None and self.integrate:
            v, w = self.cmd
            fresh = YAW_PULSE_S if (v == 0.0 and w != 0.0) else FRESH_S
            applied = max(0.0, min(t - self.t_prev, fresh))
            if applied > 0.0:
                n = max(1, int(math.ceil(applied / 0.02)))
                h = applied / n
                v_m, w_r = self.model.body_speeds(v, w)
                x, y, yaw = self.pose
                for _ in range(n):
                    x += v_m * math.cos(yaw) * h
                    y += v_m * math.sin(yaw) * h
                    yaw = math.atan2(math.sin(yaw + w_r * h), math.cos(yaw + w_r * h))
                self.pose = [x, y, yaw]
        self.t_prev = t

    def override_command(self, v, w):
        """The caller did not send the command computed by update() (a slow frame): the pose and the log must describe what was really sent."""
        self.cmd = (v, w)
        if self.rows:
            self.rows[-1].update(v=round(v, 3), w=round(w, 3), suppressed=1)

    def update(self, t, tracks, people=None):
        """tracks: [(track_id, (x1, y1, x2, y2))] of this frame in raw pixels; people: [(box, keypoints_xy, keypoints_conf)] from the pose model (only with trunk_fn). -> (v, w)."""
        self._advance(t)
        row = dict(t=round(t, 3), track_id=None, dist_m=None, forward_m=None, left_m=None, yaw_err=None, feet_cut=None, range_src=None, foot_forward_m=None, v_req=0.0, w_req=0.0, v=0.0, w=0.0, suppressed=0, mode="NO_TARGET", event=None,
                   tracks=";".join("%d:%d,%d,%d,%d" % ((tid,) + tuple(int(q) for q in xyxy)) for tid, xyxy in tracks))
        valid, reacq = {}, False
        for tid, xyxy in tracks:
            gp, cut, ye = foot_point(self.ground_point, self.undistort_points, xyxy, self.size, self.feet_row_offset_px)
            valid[tid] = (xyxy, gp, cut, ye)
        src = {}
        if self.trunk_fn is not None:
            for tid, (xyxy, gp, cut, ye) in list(valid.items()):
                best = max(((iou(xyxy, pb), (kx, kc)) for pb, kx, kc in (people or [])), key=lambda m: m[0], default=None)
                est = self.trunk_fn(*best[1]) if best is not None and best[0] >= TRUNK_IOU else None
                if est is None:
                    src[tid] = "foot"
                    continue
                hist = (self._trunk_hist.get(tid, []) + [est])[-TRUNK_WINDOW:]
                self._trunk_hist[tid] = hist
                fwd, left = float(np.median([h[0] for h in hist])), float(np.median([h[1] for h in hist]))
                src[tid] = "trunk"
                valid[tid] = (xyxy, GroundPoint(fwd, left), cut, ye)                 # the trunk range replaces the foot-row range (the feet may even be cut off)
                src[tid] = ("trunk", gp.forward_m if gp is not None else None)
        if self.target_id is None:
            cands = [(max(0.0, (b[0][2] - b[0][0]) * (b[0][3] - b[0][1])), tid) for tid, b in valid.items() if b[1] is not None and b[1].distance_m <= self.lock_range_m]
            if cands:
                self.target_id = max(cands)[1]
        if self.target_id is not None and self.target_id not in valid and self.t_seen is not None and self.last_seen is not None and t - self.t_seen <= REACQ_MAX_LOST_S:
            # the tracker may have given the same person a new id after a blur: re-lock only on ONE person near the last position
            near = [tid for tid, b in valid.items() if abs(b[3] - self.last_seen[0]) <= REACQ_YAW_GATE
                    and (b[1] is None or self.last_seen[1] is None or abs(b[1].distance_m - self.last_seen[1]) <= REACQ_DIST_GATE_M)]
            if len(valid) == 1 and len(near) == 1:
                self.target_id = near[0]
                reacq = True
        if self.target_id is not None and self.target_id in valid:
            self.t_seen = t
            xyxy, gp, cut, ye = valid[self.target_id]
            row.update(track_id=self.target_id, yaw_err=round(ye, 4), feet_cut=int(cut))
            tr = src.get(self.target_id)
            if self.trunk_fn is not None:
                row.update(range_src=("trunk" if isinstance(tr, tuple) else "foot"), foot_forward_m=(round(tr[1], 3) if isinstance(tr, tuple) and tr[1] is not None else None))
            if gp is None:                                           # feet cut off / no floor intersection: no translation, yaw centring only
                v, w, _ = self.ctl.hold.compute(t, ye)
                row.update(mode="YAW_ONLY")
            else:
                out = self.ctl.step(t, tuple(self.pose), (gp.forward_m, gp.left_m), ye)
                v, w = out.v, out.w
                row.update(dist_m=round(gp.distance_m, 3), forward_m=round(gp.forward_m, 3), left_m=round(gp.left_m, 3), mode=out.mode, event=out.event)
                if out.event:
                    self.hold_events.append((round(t, 2), out.event))
            row.update(v_req=round(v, 3), w_req=round(w, 3))
            if gp is not None:
                self._dist_hist = (self._dist_hist + [gp.distance_m])[-DIST_MEDIAN_N:]
                band = self.ctl.pursuit.cfg.distance_tolerance_m
                if v != 0.0 and abs(float(np.median(self._dist_hist)) - self.ctl.pursuit.cfg.target_distance_m) <= band:
                    v = 0.0                                          # inside the plan's standoff band: stand still (no creeping, no reversing); the hold detector can then see a still target
            self.last_seen = (ye, gp.distance_m if gp is not None else None)
            if abs(v) < 1e-9 and w != 0.0:                           # yaw-only: dead band, then short pulses
                self._yaw_phase = (self._yaw_phase + 1) % YAW_PULSE_PERIOD
                if abs(ye) <= YAW_DEADBAND or self._yaw_phase != 1:
                    w = 0.0
            else:
                self._yaw_phase = 0
        else:
            v = w = 0.0                                              # no target this frame: stop now (the sender also stops a stale command)
            if self.target_id is not None and self.t_seen is not None and t - self.t_seen >= self.lost_end_s:
                self.end_reason = "target lost for %.1f s" % self.lost_end_s
        self.cmd = (v, w)
        row.update(v=round(v, 3), w=round(w, 3))
        if reacq:
            row["event"] = "REACQUIRE"
        self.rows.append(row)
        return v, w

    def _weights(self):
        """Seconds each row stands for: the gap to the next row, at most TIME_CAP_S (the last row counts 0.05 s). Longer gaps are unobserved time, not credit."""
        ts = [r["t"] for r in self.rows]
        return [min(b - a, TIME_CAP_S) for a, b in zip(ts, ts[1:])] + ([0.05] if ts else [])

    def summary(self, pursuit_band=0.2):
        rows, wts = self.rows, self._weights()
        target = self.ctl.pursuit.cfg.target_distance_m
        tracked = [(r, w) for r, w in zip(rows, wts) if r["yaw_err"] is not None]
        ranged = [(r, w) for r, w in tracked if r["dist_m"] is not None]
        pursue = [r for r, _ in ranged if r["mode"] != "HOLD"]
        near_f = [r for r in pursue if abs(r["dist_m"] - target) <= pursuit_band]
        centred_f = [r for r, _ in tracked if abs(r["yaw_err"]) / 2.0 <= CENTRE_TOL_WIDTH]
        run_s = sum(wts)
        tracked_s = sum(w for _, w in tracked)
        ranged_s = sum(w for _, w in ranged)
        in_band_s = sum(w for r, w in ranged if abs(r["dist_m"] - target) <= pursuit_band)
        centred_s = sum(w for r, w in tracked if abs(r["yaw_err"]) / 2.0 <= CENTRE_TOL_WIDTH)

        def frac(a, b):
            return round(a / b, 3) if b > 0 else None
        return {"frames": len(rows), "frames_with_distance": len(ranged), "pursue_frames": len(pursue),
                "run_time_s": round(run_s, 2), "tracked_time_s": round(tracked_s, 2), "coverage_tracked_fraction": frac(tracked_s, run_s),
                "time_fraction_distance_in_band_of_tracked": frac(in_band_s, ranged_s), "time_fraction_distance_in_band_of_run": frac(in_band_s, run_s),
                "time_fraction_centred_of_tracked": frac(centred_s, tracked_s), "time_fraction_centred_of_run": frac(centred_s, run_s),
                "diag_frame_fraction_distance_in_band": frac(len(near_f), len(pursue)), "diag_frame_fraction_centred": frac(len(centred_f), len(tracked)),
                "centre_unit": "|bbox centre - image centre| / full frame width <= %.2f (yaw_err in the log is relative to HALF the width: divided by 2 here)" % CENTRE_TOL_WIDTH,
                "hold_events": self.hold_events, "reacquires": sum(1 for r in rows if r["event"] == "REACQUIRE"), "target_id": self.target_id,
                "acceptance": "NOT EVALUATED: first supervised trials; the time fractions are diagnostics (no-target time counts in the 'of_run' versions), not the plan's 80 % acceptance",
                "plan_thresholds": "distance 1.2 +/- 0.2 m and bbox centre within +/- 10 % of the frame width for 80 % of the time (plan 4.3 'Pursuit PD')"}


def make_pose(weights, cfg):
    """YOLOv8-pose -> callable(frame_bgr) -> [(box xyxy, keypoints (17, 2), confidences (17,))] (for the trunk-length range)."""
    from ultralytics import YOLO
    root = Path(__file__).resolve().parents[1]
    path = Path(weights) if weights else root / cfg["reid"].get("pose_weights", "data/models/yolov8n-pose.pt")
    if not path.exists():
        path = root / "yolov8n-pose.pt"
    if not path.exists():
        raise SystemExit("ABORT: no pose weights (%s): pass --pose-weights" % path)
    model, device = YOLO(str(path)), cfg["reid"].get("person_device", "0")

    def run(frame):
        r = model(frame, verbose=False, conf=0.3, device=device)[0]
        if r.keypoints is None or len(r.boxes) == 0:
            return []
        return [(tuple(float(v) for v in b), k, c) for b, k, c in zip(r.boxes.xyxy.cpu().numpy(), r.keypoints.xy.cpu().numpy(), r.keypoints.conf.cpu().numpy())]
    return run


def make_perception(device_cfg=None):
    """YOLO person detector + vendored ByteTrack; -> callable(frame_bgr) -> [(track_id, xyxy)]."""
    from sentry.config import load
    from sentry.perception.obstacle import YOLOPredictor
    from sentry.perception.tracker import VendoredByteTrackBackend
    cfg = load()
    rs, s = cfg["reid"], cfg["tracking"]
    root = Path(__file__).resolve().parents[1]
    detector = YOLOPredictor(root / rs["person_weights"], dict(cfg["obstacle"], class_ids=[0], confidence=s["track_low_thresh"], imgsz=rs["person_imgsz"], device=rs["person_device"]))
    backend = VendoredByteTrackBackend(s)

    def run(frame):
        h, w = frame.shape[:2]
        rows = [[max(0.0, d.xyxy[0]), max(0.0, d.xyxy[1]), min(float(w), d.xyxy[2]), min(float(h), d.xyxy[3]), d.confidence, 0] for d in detector(frame) if d.class_id == 0]
        out = backend.update(rows, frame.shape[:2])
        return [(int(r[4]), tuple(float(v) for v in r[:4])) for r in out]
    return run


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--label", required=True)
    ap.add_argument("--camera-pose", required=True, help="camera pose JSON of TODAY's mount (python -m tools.self_pose)")
    ap.add_argument("--camera", default="calib/camera.json")
    ap.add_argument("--motion-session", default=None, help="optional motion session JSON for the dead-reckoning model (the withdrawn 10-30 file is not usable)")
    ap.add_argument("--ip", default="auto")
    ap.add_argument("--user", default="jetbot")
    ap.add_argument("--password", default=os.environ.get("JETBOT_PASSWORD"))
    ap.add_argument("--seconds", type=float, default=60.0)
    ap.add_argument("--wait", type=float, default=60.0, help="seconds to arm the e-stop and hold R1 before the run is abandoned")
    ap.add_argument("--min-battery", type=float, default=MIN_BATTERY_V)
    ap.add_argument("--lock-range", type=float, default=3.5, help="lock the largest person within this ground distance (m)")
    ap.add_argument("--lost-end-s", type=float, default=5.0)
    ap.add_argument("--dry-run", action="store_true", help="robot connected and video processed, NO commands are sent")
    ap.add_argument("--replay", default=None, help="folder of images (no robot at all): commands are only logged")
    ap.add_argument("--save-frames", action="store_true", help="save the video frames (people are in them: stays under data/, never committed)")
    ap.add_argument("--feet-row-offset-px", type=float, default=None, help="box bottom sits this many px below the floor contact (session calibration; default [pursuit] feet_row_offset_px, 0 = uncalibrated)")
    ap.add_argument("--range-source", choices=("foot", "trunk"), default="foot", help="foot: floor distance of the box bottom (default); trunk: range from the shoulder-to-hip length with a population prior, foot-row fallback when the keypoints are not confident (a lead, see sentry/perception/body_range.py)")
    ap.add_argument("--pose-weights", default=None, help="YOLOv8-pose weights for --range-source trunk (default [reid] pose_weights, else yolov8n-pose.pt in the repo root)")
    ap.add_argument("--out", default="data/pursuit")
    a = ap.parse_args()
    a.dry_run = a.dry_run or a.replay is not None

    import cv2
    from sentry.nav.controllers import HoldBehaviorConfig, InterceptionController, PursuitConfig
    from sentry.nav.hold_detector import HoldConfig
    from sentry.nav.wheel_model import WheelModel
    from sentry.config import load
    from sentry.perception.camera import CameraGeometry

    geom = CameraGeometry.from_files(a.camera, a.camera_pose)
    ground_point = geom.ground_point
    pcfg, hbcfg, hdcfg = PursuitConfig.from_toml(), HoldBehaviorConfig.from_toml(), HoldConfig.from_toml()
    ctl = InterceptionController(pcfg, hbcfg, hdcfg)
    effective_config = {"pursuit": dataclasses.asdict(pcfg), "hold_behavior": dataclasses.asdict(hbcfg), "hold_detector": dataclasses.asdict(hdcfg)}
    model = WheelModel.from_session(a.motion_session) if a.motion_session else WheelModel()
    pursuit = Pursuit(ctl, model, ground_point, geom.undistort_points, geom.size, a.lock_range, lost_end_s=a.lost_end_s, feet_row_offset_px=a.feet_row_offset_px if a.feet_row_offset_px is not None else float(load()["pursuit"].get("feet_row_offset_px", 0.0)),
                      integrate=not a.dry_run)
    perceive = make_perception()
    trunk_m = float(load()["pursuit"].get("trunk_length_m", 0.50))
    trunk_conf = float(load()["pursuit"].get("trunk_conf_min", 0.8))
    pose_fn = None
    if a.range_source == "trunk":
        pose_fn = make_pose(a.pose_weights, load())
        pursuit.trunk_fn = lambda kxy, kconf: trunk_range(kxy, kconf, geom.undistort_points, geom.K, geom.pitch, trunk_m, trunk_conf)
    print("camera pose %s: pitch %.2f deg, lens %.3f m. NO OBSTACLE AVOIDANCE: keep the floor clear, hold R1, release at any problem." % (a.camera_pose, math.degrees(geom.pitch), geom.height_m), flush=True)

    cmd, end, done = {"v": 0.0, "w": 0.0, "t": 0.0}, {"reason": None}, threading.Event()
    link = {"t": time.time()}
    saved, volts0, volts1 = [], None, None
    rx = ssh = None

    def process(frame, t):
        t0 = time.time()
        tracks = perceive(frame)
        v, w = pursuit.update(t, tracks, pose_fn(frame) if pose_fn is not None else None)
        if time.time() - t0 > MAX_PROCESS_S:                    # a slow frame is an old view of the world: never drive on it
            v, w = 0.0, 0.0
            pursuit.override_command(v, w)                      # the pose and the log say what was really sent
        cmd.update(v=v, w=w, t=time.time())
        if pursuit.end_reason and end["reason"] is None:
            end["reason"] = pursuit.end_reason

    t_wall = time.time()
    written = {"done": False}

    def write_outputs():
        """Called from the live loop's finally (also after an error or Ctrl+C), so the evidence of a stopped run is never lost."""
        if written["done"]:
            return
        written["done"] = True
        summary = dict(pursuit.summary(), label=a.label, dry_run=a.dry_run, replay=a.replay, end_reason=end["reason"], camera_pose_file=a.camera_pose, pitch_down_deg=round(math.degrees(geom.pitch), 2),
                       feet_row_offset_px=pursuit.feet_row_offset_px, range_source=a.range_source, trunk_length_m=trunk_m, trunk_conf_min=trunk_conf, trunk_frames=sum(1 for r in pursuit.rows if r.get("range_src") == "trunk"), config=effective_config, battery_v_start=volts0, battery_v_end=volts1, seconds=round(time.time() - t_wall, 1), date=time.strftime("%Y-%m-%d %H:%M"), obstacle_avoidance=False)
        run_dir = save_run(a.out, a.label, pursuit.rows, summary, saved)
        print("ENDED: %s | %s" % (end["reason"], json.dumps({k: summary[k] for k in ("frames", "run_time_s", "coverage_tracked_fraction", "time_fraction_distance_in_band_of_run", "time_fraction_centred_of_run", "hold_events")})), flush=True)
        print("saved", run_dir, flush=True)

    if a.replay is not None:
        files = sorted(p for p in Path(a.replay).iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
        if not files:
            raise SystemExit("no images in %s" % a.replay)
        for i, p in enumerate(files):
            img = cv2.imread(str(p))
            if img is None or img.shape[1::-1] != tuple(geom.size):
                continue
            process(img, i / 10.0)
        end["reason"] = "replay finished"
    else:
        from sentry.config import load
        from sentry.net.discover import resolve
        from sentry.net.udp_tx import UDPSender
        from sentry.net.zmq_rx import ZMQReceiver
        from tools import jetbot_ssh
        from tools.calibrate_motion import _sh
        from tools.jetbot_status import ina219_bus_volts
        a.ip = resolve(a.ip)
        password = jetbot_ssh.password(a.password)
        ssh = jetbot_ssh.connect(a.ip, a.user, password)
        volts0 = ina219_bus_volts(jetbot_ssh.sudo(ssh, "i2cget -y 1 0x41 0x02 w", password))
        print("battery %.2f V" % volts0, flush=True)
        if volts0 < a.min_battery:
            raise SystemExit("ABORT: battery %.2f V < %.1f V: charge first" % (volts0, a.min_battery))
        control_port = load()["net"]["control_port"]
        rx = ZMQReceiver(ip=a.ip)
        rx.start()
        first = None
        for _ in range(40):
            first = rx.read(timeout=1.0)
            if first is not None:
                break
        if first is None:
            raise SystemExit("ABORT: no video frame from the robot")
        print("warming up the person detector (first frame is slow, done before R1 is needed)...", flush=True)
        for _ in range(3):
            perceive(first.frame_bgr)
        print("start checks passed: battery, video", flush=True)
        r1 = {"held": True, "fail": 0}
        if not a.dry_run:
            print("ARM the e-stop (hold Start 1.5 s) and HOLD R1 within %.0f s. Release R1 at any problem." % a.wait, flush=True)
            t_end, since = time.time() + a.wait, None
            while True:
                held = _sh(ssh, "test -e %s && echo no || echo yes" % ESTOP_LATCH).strip() == "yes"
                now = time.time()
                since = (since or now) if held else None
                if since and now - since >= 0.5:
                    break
                if now > t_end:
                    raise SystemExit("ABORT: R1 was not held (and the e-stop armed) in time")
                time.sleep(0.2)
            print("R1 held: pursuing for up to %.0f s (q = stop)" % a.seconds, flush=True)

        def sender():
            s = UDPSender(a.ip, control_port, 30) if not a.dry_run else None
            try:
                while not done.is_set():
                    if s is not None:
                        s.send(*command_to_send(cmd, time.time()))
                    time.sleep(1 / 30.0)
            finally:
                if s is not None:
                    s.close(stop=True)

        def watcher():
            while not done.is_set() and not a.dry_run:
                try:
                    r1["held"] = _sh(ssh, "test -e %s && echo no || echo yes" % ESTOP_LATCH).strip() == "yes"
                    r1["fail"] = 0
                except Exception:
                    r1["fail"] += 1
                if not r1["held"] and end["reason"] is None:
                    end["reason"] = "R1 released (e-stop latch present)"
                if r1["fail"] >= 2 and end["reason"] is None:
                    end["reason"] = "lost the SSH link to the robot (cannot see R1)"
                time.sleep(0.2)

        threads = [threading.Thread(target=sender), threading.Thread(target=watcher)]
        for th in threads:
            th.daemon = True
            th.start()
        t_wall = time.time()
        try:
            while end["reason"] is None:
                f = rx.read(timeout=0.5)
                now = time.time()
                if f is None:
                    if now - link["t"] > LINK_STALE_S:
                        cmd.update(v=0.0, w=0.0, t=now)                  # no video: stop at once
                    if now - link["t"] > 3.0:
                        end["reason"] = "no robot frame for 3 s"
                    continue
                link["t"] = now
                process(f.frame_bgr, now - t_wall)
                if a.save_frames:
                    ok_, jpg = cv2.imencode(".jpg", f.frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    if ok_:
                        saved.append((now - t_wall, jpg.tobytes()))
                if now - t_wall > a.seconds:
                    end["reason"] = "time limit"
                try:
                    import msvcrt
                    if msvcrt.kbhit() and msvcrt.getwch().lower() == "q":
                        end["reason"] = "operator pressed q"
                except ImportError:
                    pass
        except BaseException as e:                                            # inference error, Ctrl+C, ...: keep the reason in the evidence
            if end["reason"] is None:
                end["reason"] = "error: %s: %s" % (type(e).__name__, e)
            raise
        finally:
            cmd.update(v=0.0, w=0.0, t=time.time())
            time.sleep(0.4)
            done.set()
            try:
                rx.close()
            except Exception:
                pass
            try:
                from tools import jetbot_ssh as _js
                volts1 = ina219_bus_volts(_js.sudo(ssh, "i2cget -y 1 0x41 0x02 w", password))
            except Exception:
                volts1 = None                                                 # end voltage unknown: written as null
            write_outputs()
        time.sleep(0.8)

    write_outputs()                                                           # replay (live runs wrote them in the finally above)


if __name__ == "__main__":
    main()
