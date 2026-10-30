"""Live Phase 1 deployment (the T2 deployment sequence): the robot drives to the sweet spot, the laptop prompts, the ESP32 handshake is checked, the robot backs up to standby.

  python -m tools.deploy_live --label cafe --vantage 1.2 0.6 --centre 3.0 0.0 --handshake data/handshake/cafe_arch --no-robot     # laptop rehearsal: real ESP32 handshake + prompts, a simulated pose
  python -m tools.deploy_live --label class --vantage 1.8 0.5 --centre 4.0 0.0 --handshake data/handshake/class_door --dry-run    # robot connected, NO motor commands
  python -m tools.deploy_live --label class --vantage 1.8 0.5 --centre 4.0 0.0 --handshake data/handshake/class_door --camera-pose calib/camera_pose_x.json   # the real run

SECOND MODE (Phase 1 chain, `--door`): instead of typing the sweet spot, declare the room and let the tool choose it:
  python -m tools.deploy_live --label p1 --door 5.1 0.0 --box -1 -2 5 2 --wall 5.1 -2.1 5.1 2.1 --wall -1.1 -2.1 -1.1 2.1 --wall -1.1 2.1 5.1 2.1 --wall -1.1 -2.1 5.1 -2.1 \
        --centre 2 0 --entrance sim --handshake manual --no-robot --no-audio          # laptop rehearsal: a simulated entrance detector, the key v verifies
The robot scans in short pulses until the entrance detector (--entrance <folder from tools.enroll_entrance>, `sim`, or `manual` = the key e) sees the door, picks the best sweet spot
inside the declared room (sentry/nav/declared_room.py: line of sight, 1.5-3.0 m from the door with --distance-margin on each side, close to a wall, reachable in a straight line) and deploys.
The map is DECLARED from your tape measurements (box = cleared floor, walls and door occupied), not explored: say so in the report. No sweet spot or no entrance: the run stops with the reason.

Coordinates are in the START frame, metres, measured with a tape: the robot starts at (0, 0) facing +x, y is to its left. --vantage is where it must stop (the sweet spot: line of
sight to the door, 1.5-3.0 m from it, near a wall or furniture), --centre the room centre it turns to face. --handshake is a folder with ref/ and sweep/ made by tools.handshake_test
(the ESP32's own reference frames of the door and a sweep of the room without it); `manual` replaces the detector by the key v (verify). Close every other reader of the ESP32 stream.
SEQUENCE: start checks (battery, frames, optional obstacle check, handshake models) -> 3 beeps -> HOLD R1 -> the robot drives, the laptop says "place the entrance camera", you hold the ESP32 toward
the door, the laptop says "camera verified", the robot reverses and stops (STANDBY) -> 2 beeps -> a few questions for the T2 sheet (tape distances).
SAFETY: the robot only moves while R1 is held (robot_udp + estop, speed cap 0.3). The run also stops on: R1 released, the e-stop poll failing twice, no robot frame for 0.5 s, the time limit, q
in this window, and (only with --camera-pose) a blocker seen by the obstacle detector while driving forward: it STOPS, it does not avoid. A cleared floor is the operator's job; people are not
obstacles to the detector. Commands are legal for the motor dead zone (sentry/app/deploy_runner.py); the pose is dead reckoning (indicative only: heading error about +-10 deg per metre).
OUTPUT: data/deploy/<label>_<n>/ with log.csv and summary.json (events, prompts, end reason, DR error at the vantage, handshake statistics, battery, your tape answers).
"""
import argparse
import csv
import json
import math
import os
import sys
import threading
import time
from pathlib import Path

from sentry.app.audio import AudioPromptPlayer, LocalSpeaker
from sentry.app.deploy_runner import DeployRunner, DeploySettings
from sentry.app.state_machine import State, StateMachine, StateMachineConfig
from sentry.nav.explore import ExploreSettings, Explorer, fresh_command
from sentry.nav.wheel_model import WheelModel

ESTOP_LATCH = "/home/jetbot/sentry/ESTOP"
MIN_BATTERY_V = 11.3
ESP_FRESH_S = 1.0           # a handshake result older than this counts as "not in view"
LINK_STALE_S = 0.5          # no robot frame for this long: stop
LINK_GRACE_S = 1.0          # extra time for the first frame after the threads start


def beep(freq, ms):
    try:
        import winsound
        winsound.Beep(freq, ms)
    except ImportError:
        sys.stdout.write("\a")
        sys.stdout.flush()


def key_pressed():
    try:
        import msvcrt
        if msvcrt.kbhit():
            return msvcrt.getwch().lower()
    except ImportError:
        pass
    return None


class WindowedHandshake(object):
    """Live handshake rule over the detector's per-frame answers: "in view" only when, in the last `span_s` seconds, there are at least `min_frames` answers and at least `frac` of them
    are in view. WHY: on 2026-10-30 at the classroom door, a single-frame detector answered "in view" for isolated frames and short runs of 4-8 frames even when the ESP32 pointed
    away (21 in a row at the glazed partition): the state machine's rule of 3 consecutive frames would have verified in 7 of 10 reject trials, and a latched single answer (what this
    tool did before) would verify on ONE frame. The placed camera is still, so a real placement gives a steady majority for seconds."""

    def __init__(self, span_s=5.0, min_frames=6, frac=0.7):
        self.span_s, self.min_frames, self.frac = span_s, min_frames, frac
        self.results = []                                    # (t, in_view)
        self.since = float("-inf")                           # answers older than this do not count (reset): a timestamp, not a clear, so the reader thread cannot put old answers back

    def add(self, t, in_view):
        self.results.append((t, bool(in_view)))
        self.results = [(tt, v) for tt, v in list(self.results) if t - tt <= self.span_s]

    def reset(self, t):
        self.since = t

    def _window(self, now):
        return [v for tt, v in list(self.results) if now - tt <= self.span_s and tt >= self.since]

    def in_view(self, now):
        w = self._window(now)
        return len(w) >= self.min_frames and sum(w) / float(len(w)) >= self.frac

    def stats(self, now):
        w = self._window(now)
        return len(w), (sum(w) / float(len(w)) if w else 0.0)


def make_flag(esp, window, sm, waiting_state=State.WAIT_CAMERA):
    """The handshake flag for the control loop. The window is CLEARED each time the machine enters the waiting state (the prompt "place the entrance camera"): evidence gathered
    BEFORE the request must not verify the camera (the first classroom rehearsal on 2026-10-30 verified 0.1 s after the prompt because the ESP32 already faced the door)."""
    seen = {"state": None}

    def flag(now):
        esp["in_view"] = window.in_view(now) if esp.get("t") is not None else esp["in_view"]
        if sm.state != seen["state"]:
            if sm.state == waiting_state:
                window.reset(now)
                esp["in_view"], esp["t"] = False, None
            seen["state"] = sm.state
        return fresh_flag(esp, now)
    return flag


def fresh_flag(feed, now, max_age=ESP_FRESH_S):
    """feed: dict with in_view and t (when the detector last answered), or None -> True only for a fresh in-view answer."""
    return bool(feed and feed.get("t") is not None and now - feed["t"] <= max_age and feed.get("in_view"))


def servo_motion(log, model):
    """Measured motion from the followed board: log = [(t, range_m, bearing_rad, cmd_v, cmd_w)] (one row per sighting, the command in force then).
    -> dict(speed_ratio, turn_ratio_left, turn_ratio_right) = measured / the model's prediction (None when there was no such motion in view); drives: range change over time while v > 0 and the steering is small;
    spins: bearing change over time while the command is a spin (the board's bearing moves opposite to the robot's turn)."""
    import numpy as np
    out = dict(speed_ratio=None, turn_ratio_left=None, turn_ratio_right=None)
    drive = [r for r in log if r[3] > 0 and abs(r[4]) < FIX_MAX_W]
    if len(drive) >= 5 and drive[-1][0] - drive[0][0] >= 1.0:
        slope = np.polyfit([r[0] for r in drive], [r[1] for r in drive], 1)[0]        # m/s, negative when closing in
        pred = np.mean([model.body_speeds(r[3], r[4])[0] for r in drive])
        out["speed_ratio"] = round(float(-slope / pred), 3) if pred > 0 else None
    for name, sign in (("turn_ratio_left", 1), ("turn_ratio_right", -1)):
        num = den = pred = 0.0
        for r0, r1 in zip(log, log[1:]):
            if r0[3] == 0 and r1[3] == 0 and r0[4] * sign > 0.3 and r1[4] * sign > 0.3 and 0 < r1[0] - r0[0] < 0.3:
                num += -(r1[2] - r0[2])
                den += r1[0] - r0[0]
                pred += model.body_speeds(0.0, r0[4])[1] * (r1[0] - r0[0])
        if den >= 0.15 and pred:
            out[name] = round(num / pred, 3)
    return out


SPIN_PULSE_S, SPIN_PAUSE_S, FIX_STILL_S, FIX_MAX_W = 0.2, 0.5, 0.4, 0.15


def blend_fix(pose, fix, gain):
    """Move the dead-reckoned pose toward a marker pose by `gain` (yaw along the short way)."""
    x, y, yaw = pose
    return (x + gain * (fix[0] - x), y + gain * (fix[1] - y), math.atan2(math.sin(yaw + gain * math.atan2(math.sin(fix[2] - yaw), math.cos(fix[2] - yaw))), math.cos(yaw + gain * math.atan2(math.sin(fix[2] - yaw), math.cos(fix[2] - yaw)))))


def control_loop(runner, model, cmd, end, get_flag, get_link, seconds, clock=time.time, sleep=time.sleep, rate_hz=30.0, key=lambda: None, pose_cb=None, get_fix=None):
    """The 30 Hz loop: dead-reckon the pose from the command the robot was given, step the runner, publish the command, check the safety conditions.
    get_link(now) -> None (no robot) or dict(stale=bool, blocked=bool). Returns (rows, final pose, dead-reckoned path length). Ends by setting end['reason']."""
    x = y = yaw = 0.0
    path, prev, rows, manual_until = 0.0, (0.0, 0.0), [], 0.0
    fix_seen, last_moving, spin_start, pause_until, end["fixes"] = 0, clock(), None, 0.0, 0     # get_fix(): (n, x, y, yaw, distance) of the newest marker pose or None
    t0 = last = clock()
    runner.start(0.0, 0.0)
    while end["reason"] is None:
        now = clock()
        t = now - t0
        k = key()
        if k == "q":
            end["reason"] = "operator pressed q"
            break
        dt = min(now - last, 0.1)
        last = now
        v_m, w_r = model.body_speeds(*prev)                  # the pose follows what the robot was told to do during dt
        x += v_m * math.cos(yaw) * dt
        y += v_m * math.sin(yaw) * dt
        yaw = math.atan2(math.sin(yaw + w_r * dt), math.cos(yaw + w_r * dt))
        path += abs(v_m) * dt
        if get_fix is not None:
            if abs(prev[1]) >= FIX_MAX_W or prev[0] < 0:
                last_moving = now                             # turning (or reversing): the frame is older than the pose, so no fix until the robot has been still for FIX_STILL_S
            fx = get_fix()
            if fx is not None and fx[0] != fix_seen:
                fix_seen = fx[0]
                if now - last_moving >= FIX_STILL_S:
                    x, y, yaw = blend_fix((x, y, yaw), fx[1:4], 0.3 if fx[4] <= 1.5 else 0.2)
                    end["fixes"] += 1
        if pose_cb is not None:
            pose_cb((x, y, yaw))
        link = get_link(now)
        if link is not None and link["stale"]:
            end["reason"] = "no robot frame for %.1f s" % LINK_STALE_S
            break
        if k == "v":
            manual_until = now + 0.5                          # the key latches for 0.5 s: the runner needs 3 consecutive in-view ticks
        flag = get_flag(now) or now < manual_until
        v, w = runner.step(t, (x, y, yaw), flag)
        reset = getattr(runner, "pose_reset", None)
        if reset is not None:
            x, y, yaw = reset
            runner.pose_reset = None
        failed = getattr(runner, "failed", None)                 # a chain runner (Phase1Runner) says why it cannot go on
        if failed:
            end["reason"] = failed
            cmd.update(v=0.0, w=0.0, t=now)
            break
        if link is not None and link["blocked"] and v > 0.0:
            end["reason"] = "obstacle ahead while driving (stopped; this tool does not avoid)"
            v = w = 0.0
            cmd.update(v=0.0, w=0.0, t=now)
            break
        if get_fix is not None and v == 0.0 and w != 0.0:        # a spin goes in pulses so that the marker fix can look at a still robot between them
            if now < pause_until:
                w = 0.0
            elif spin_start is None:
                spin_start = now
            elif now - spin_start >= SPIN_PULSE_S:
                spin_start, pause_until, w = None, now + SPIN_PAUSE_S, 0.0
        else:
            spin_start = None
        prev = (v, w)
        cmd.update(v=v, w=w, t=now)
        rows.append((round(t, 3), round(x, 3), round(y, 3), round(yaw, 3), v, round(w, 3), runner.sm.state.value, int(flag)))
        if runner.sm.state == State.STANDBY:
            end["reason"] = "STANDBY reached"
            break
        if t > seconds:
            end["reason"] = "time limit"
            break
        sleep(max(0.0, 1.0 / rate_hz - (clock() - now)))
    return rows, (x, y, yaw), path


def make_handshake(folder):
    """EntranceDetector enrolled with the ESP32's own reference frames and calibrated on the sweep (as tools.handshake_test eval)."""
    import cv2
    from sentry.perception.entrance import EntranceConfig, EntranceDetector
    root = Path(folder)
    refs = [cv2.imread(str(p)) for p in sorted((root / "ref").glob("r*.jpg"))]
    sweep = [cv2.imread(str(p)) for p in sorted((root / "sweep").glob("s*.jpg"))]
    if not refs or not sweep:
        raise SystemExit("%s needs ref/r*.jpg and sweep/s*.jpg (python -m tools.handshake_test ref|sweep --name ...)" % folder)
    det = EntranceDetector(None, EntranceConfig())
    det.enroll_esp32(refs)
    thr = det.calibrate(sweep[::2] if len(sweep) > 60 else sweep)
    print("handshake detector: %d reference frames, XFeat threshold %s" % (len(refs), thr[0]), flush=True)
    return det


def main():
    import cv2
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--label", default="run")
    ap.add_argument("--vantage", type=float, nargs=2, default=None, metavar=("X", "Y"), help="the sweet spot typed in (manual mode); not needed with --door")
    ap.add_argument("--door", type=float, nargs=2, default=None, metavar=("X", "Y"), help="Phase 1 chain: the door position (tape, start frame); the sweet spot is chosen from the declared room")
    ap.add_argument("--box", type=float, nargs=4, default=None, metavar=("X0", "Y0", "X1", "Y1"), help="the cleared floor of the declared room (with --door)")
    ap.add_argument("--wall", type=float, nargs=4, action="append", default=[], metavar=("X0", "Y0", "X1", "Y1"), help="a wall segment of the declared room (repeat); the door must lie on one")
    ap.add_argument("--entrance", default="manual", help="with --door: a folder from tools.enroll_entrance (the robot's own camera), 'sim' (simulated from the pose) or 'manual' (key e)")
    ap.add_argument("--scan-hold", type=float, default=0.8, help="with --door: seconds to hold still between scan pulses; the robot-eye entrance detector runs at about 4 fps (233 ms per frame), and the filter needs 3 in-view results in a row")
    ap.add_argument("--distance-margin", type=float, default=0.3, help="with --door: shrink the 1.5-3.0 m window by this on each side (dead reckoning error)")
    ap.add_argument("--centre", type=float, nargs=2, required=True, metavar=("X", "Y"))
    ap.add_argument("--handshake", default="manual", help="folder with ref/ and sweep/ from tools.handshake_test, or 'manual' (press v)")
    ap.add_argument("--esp-ip", default="auto", help="the ESP32-CAM address, or auto (found on the network: the hotspot hands out a new subnet on some days)")
    ap.add_argument("--camera-pose", default=None, help="camera pose JSON of the CURRENT mount: enables the obstacle stop (and the start check)")
    ap.add_argument("--floor", choices=("glossy", "matte", "unknown"), default="unknown")
    ap.add_argument("--seconds", type=float, default=120.0)
    ap.add_argument("--dry-run", action="store_true", help="robot connected (frames, battery) but NO motor commands and R1 not needed; the pose is integrated as if the commands were executed")
    ap.add_argument("--no-robot", action="store_true", help="no robot at all (laptop rehearsal): implies --dry-run")
    ap.add_argument("--wait", type=float, default=30.0, help="seconds to wait for R1 after the beeps")
    ap.add_argument("--ip", default="auto")
    ap.add_argument("--user", default="jetbot")
    ap.add_argument("--password", default=os.environ.get("JETBOT_PASSWORD"))
    ap.add_argument("--out", default="data/deploy")
    ap.add_argument("--motion-session", default=None, help="calib/motion_session_*.json from tools.motion_check: this floor's speed scale, left/right turn scales and drift for the dead reckoning (without it the robot veered off the line on 2026-10-30)")
    ap.add_argument("--anchors", default=None, help="ArUco board anchors CSV (marker_id,x_m,y_m,z_m,yaw_deg) in the frame of the start pose: the pose is corrected from the boards in the robot's video (spins go in pulses)")
    ap.add_argument("--fix-range", type=float, default=1.5, help="boards farther than this give no pose fix (their orientation is too noisy)")
    ap.add_argument("--servo-marker", type=int, default=None, help="approach by following this board (id) in the robot's video: spin in pulses until it is seen, drive at it steering by its bearing, stop at --servo-stop (dead reckoning only until it is first seen)")
    ap.add_argument("--servo-board", type=float, nargs=2, default=None, metavar=("X", "Y"), help="--servo-marker: the board's position in the start frame; on arrival the pose is set to the vantage with the heading toward it (so the turn to face the centre starts from the truth)")
    ap.add_argument("--servo-stop", type=float, default=0.87, help="--servo-marker: stop at this camera-to-board range (m) = the sweet spot's distance to the board")
    ap.add_argument("--no-save-frames", action="store_true", help="by default every robot video frame of the run is saved (JPEG q80, with its time) in <run>/frames for later analysis; faces may be in them: data/ stays local")
    ap.add_argument("--hs-span", type=float, default=5.0, help="handshake rule: window in seconds (the detector answers at about 1.5-2.2 fps in a live run: 5 s holds 7-11 answers)")
    ap.add_argument("--hs-frames", type=int, default=6, help="handshake rule: at least this many detector answers in the window")
    ap.add_argument("--hs-frac", type=float, default=0.7, help="handshake rule: at least this fraction of them in view (the camera is placed still: a real placement gives a steady majority)")
    ap.add_argument("--no-audio", action="store_true", help="do not speak (rehearsal in a quiet room); the prompts are still logged")
    a = ap.parse_args()
    a.dry_run = a.dry_run or a.no_robot
    if not 10 <= a.seconds <= 300:
        ap.error("seconds in [10, 300]")
    if (a.vantage is None) == (a.door is None):
        ap.error("give exactly one of --vantage (manual sweet spot) and --door (Phase 1 chain)")
    if a.door is not None and (a.box is None or not a.wall):
        ap.error("--door needs --box and at least one --wall (the declared room)")

    model, done = (WheelModel.from_session(a.motion_session) if a.motion_session else WheelModel()), threading.Event()
    cmd = {"v": 0.0, "w": 0.0, "t": time.time()}
    end = {"reason": None}
    r1 = {"held": True, "fail": 0}
    link = {"t": time.time(), "blocked": False}
    esp = {"in_view": False, "t": None, "frames": 0, "in_view_frames": 0, "inliers": 0}
    window = WindowedHandshake(a.hs_span, a.hs_frames, a.hs_frac)       # defaults 5 s / 6 answers / 70 %: measured live on 2026-10-30 (negative 3 % in view, 0 of 1337 ticks; positive verified 8.4 s after the prompt)
    threads, ssh, rx, volts0, volts1, password = [], None, None, None, None, None
    speaker = AudioPromptPlayer(sender=LocalSpeaker(backend=(lambda path: None) if a.no_audio else None))

    if a.handshake != "manual" and a.esp_ip == "auto":
        from sentry.net.discover import find_esp32
        a.esp_ip = find_esp32()
        if a.esp_ip is None:
            raise SystemExit("no ESP32 found on this network (is it powered and on the hotspot? give --esp-ip)")
        print("ESP32 found at %s" % a.esp_ip, flush=True)
    detector = None if a.handshake == "manual" else make_handshake(a.handshake)
    sm = StateMachine(StateMachineConfig())
    pose_now = {"p": (0.0, 0.0, 0.0)}
    fixer, fixed = None, {"m": None, "servo": None}

    def servo_obs():
        s = fixed["servo"]
        return (s[1], s[2]) if s is not None and time.time() - s[0] < 0.6 else None
    servo_tr, servo_log, frames_buf = None, [], []
    if a.servo_marker is not None:
        from sentry.nav.localization import LocalizationTracker
        servo_tr = LocalizationTracker(motion_calib=None, camera_calib="calib/camera.json", max_marker_distance_m=1e6)
    if a.anchors:
        from sentry.nav.marker_fix import MarkerFix
        fixer = MarkerFix(a.anchors, max_range_m=a.fix_range)
    manual = {"until": 0.0}
    grid = entrance_det = None
    if a.door is not None:
        from sentry.config import load as load_config
        from sentry.nav.declared_room import declared_grid
        from sentry.nav.vantage import VantageSelector
        from sentry.app.phase1_runner import Phase1Runner, Phase1Settings
        cfg = load_config()
        selector = VantageSelector(cfg["thresholds"]["entrance_min_m"] + a.distance_margin, cfg["thresholds"]["entrance_max_m"] - a.distance_margin,
                                   cfg["vantage"]["robot_radius_m"], cfg["vantage"]["boundary_weight"], cfg["vantage"]["distance_weight"])
        grid = declared_grid(a.box, a.wall, a.door)
        runner = Phase1Runner(sm, speaker, grid, selector, a.door, a.centre, settings=Phase1Settings(hold_s=a.scan_hold))
        if a.entrance not in ("sim", "manual"):
            from sentry.perception.entrance import Camera, EntranceDetector
            entrance_det = EntranceDetector.load(a.entrance, camera=Camera.from_json("calib/camera.json"))
            print("entrance detector loaded from %s" % a.entrance, flush=True)
    else:
        runner = DeployRunner(sm, speaker, vantage_xy=a.vantage, centre_xy=a.centre, settings=DeploySettings(),
                              servo=(lambda t: servo_obs()) if a.servo_marker is not None else None, servo_stop_m=a.servo_stop, servo_board_xy=a.servo_board)

    def entrance_feeder():
        """sim: the door counts as in view when the robot faces it (within 0.5 rad); manual: for 0.5 s after the key e. 20 Hz, like the robot's frames."""
        from sentry.perception.entrance import EntranceResult
        while not done.is_set():
            x, y, yaw = pose_now["p"]
            to_door = math.atan2(a.door[1] - y, a.door[0] - x)
            rel = math.atan2(math.sin(to_door - yaw), math.cos(to_door - yaw))
            seen = abs(rel) < 0.5 if a.entrance == "sim" else time.time() < manual["until"]
            runner.observe_entrance(EntranceResult(seen, 30, None, rel if seen else None, None), time.time())
            time.sleep(0.05)

    def esp_reader():
        import cv2
        import numpy as np
        from tools.record_d2 import jpegs
        try:
            for jpg in jpegs("http://%s:81/stream" % a.esp_ip):
                if done.is_set():
                    return
                frame = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
                if frame is None:
                    continue
                res = detector.detect(frame)
                now = time.time()
                window.add(now, res.in_view)
                esp.update(in_view=window.in_view(now), t=now, inliers=int(res.inliers), single_frame=bool(res.in_view))
                esp["frames"] += 1
                esp["in_view_frames"] += int(res.in_view)
        except Exception as exc:
            esp["error"] = repr(exc)

    obs_det = explorer = None
    if not a.no_robot:
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
        print("battery %.2f V" % volts0)
        if volts0 < MIN_BATTERY_V:
            raise SystemExit("ABORT: battery %.2f V < %.1f V: charge first" % (volts0, MIN_BATTERY_V))
        control_port = load()["net"]["control_port"]
        rx = ZMQReceiver(ip=a.ip)
        rx.start()
        obs_det = explorer = None
        if a.camera_pose:
            from sentry.perception.obstacle import ObstacleDetector
            obs_det = ObstacleDetector.from_config(camera_pose_path=a.camera_pose, floor_type=a.floor)
            explorer = Explorer(ExploreSettings(), obs_det.geometry.size)
        else:
            print("NO OBSTACLE CHECK (no --camera-pose): the floor must be cleared and you must hold R1", flush=True)

        def sender():
            s = UDPSender(a.ip, control_port, 30) if not a.dry_run else None
            try:
                while not done.is_set():
                    if s is not None:
                        v, w = fresh_command(cmd["v"], cmd["w"], cmd["t"], time.time())
                        s.send(v, w)
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
                if (not r1["held"]) and end["reason"] is None:
                    end["reason"] = "R1 released (e-stop latch present)"
                if r1["fail"] >= 2 and end["reason"] is None:
                    end["reason"] = "lost the SSH link to the robot (cannot see R1)"
                time.sleep(0.2)

        def frames():
            while not done.is_set():
                f = rx.read(timeout=0.5)
                if f is None:
                    continue
                link["t"] = time.time()
                if not a.no_save_frames:
                    ok_, jpg = cv2.imencode(".jpg", f.frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    if ok_:
                        frames_buf.append((time.time(), jpg.tobytes()))
                if servo_tr is not None:
                    for d in servo_tr.detect_markers(f.frame_bgr):
                        if d.marker_id == a.servo_marker:
                            fixed["servo"] = (time.time(), d.distance_m, d.bearing_rad)
                            servo_log.append((time.time(), d.distance_m, d.bearing_rad, cmd["v"], cmd["w"]))
                            break
                if fixer is not None:
                    try:
                        fixed["m"] = fixer.measure(f.frame_bgr) or fixed["m"]
                    except Exception as exc:
                        end["reason"] = end["reason"] or "marker fix error: %r" % exc
                if entrance_det is not None:
                    try:
                        runner.observe_entrance(entrance_det.detect(f.frame_bgr), time.time())
                    except Exception as exc:
                        end["reason"] = end["reason"] or "entrance detector error: %r" % exc
                if obs_det is not None:
                    try:
                        obs = obs_det(f.frame_bgr, time.time(), mode="explore", floor_type=a.floor)
                        link["blocked"] = explorer.blocking(obs)[0]
                        if grid is not None:                       # furniture the detector sees joins the declared map
                            from sentry.nav.gridmap import Pose2D
                            grid.update(Pose2D(*pose_now["p"]), obs.ground_points)
                    except Exception as exc:
                        end["reason"] = end["reason"] or "obstacle detector error: %r" % exc

        first = None
        for _ in range(40):
            first = rx.read(timeout=1.0)
            if first is not None:
                break
        if first is None:
            raise SystemExit("ABORT: no video frame from the robot")
        print("start checks passed: battery, frames", flush=True)
        if not a.dry_run:
            for _ in range(3):
                beep(1500, 300)
            print("HOLD R1 now (within %.0f s). Stop any time: release R1 or press q here." % a.wait, flush=True)
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
            print("R1 held: driving", flush=True)
        threads.extend([threading.Thread(target=sender), threading.Thread(target=watcher), threading.Thread(target=frames)])
    if detector is not None:
        threads.append(threading.Thread(target=esp_reader))
    if a.door is not None and a.entrance in ("sim", "manual"):
        threads.append(threading.Thread(target=entrance_feeder))
    link["t"] = time.time() + LINK_GRACE_S      # the watchdog counts from now: link["t"] was set at start-up, before the models and the SSH link, so the first tick looked stale (found by the dry run on 2026-10-30)
    for th in threads:
        th.daemon = True
        th.start()

    # the 0.5 s video watchdog guards the OBSTACLE detector; without --camera-pose the robot's video steers nothing, and a weak Wi-Fi link (2.5-5 fps measured in the classroom on 2026-10-30)
    # would abort every run for nothing. The robot's own 0.3 s command watchdog, R1 and the e-stop poll still stop it.
    get_link = (lambda now: None) if a.no_robot else (lambda now: {"stale": obs_det is not None and now - link["t"] > LINK_STALE_S, "blocked": link["blocked"]})
    t_wall = time.time()
    try:
        def key():
            k = key_pressed()
            if k == "e":                                          # manual entrance: in view for 0.5 s
                manual["until"] = time.time() + 0.5
            return k
        rows, final, path = control_loop(runner, model, cmd, end, make_flag(esp, window, sm), get_link, a.seconds, key=key,
                                         pose_cb=lambda p: pose_now.__setitem__("p", p), get_fix=(lambda: fixed["m"]) if fixer is not None else ((lambda: None) if servo_tr is not None else None))
    finally:
        cmd.update(v=0.0, w=0.0, t=time.time())            # the sender then repeats zero; its close() sends a final stop
        time.sleep(0.4)
        done.set()
        if rx is not None:
            rx.close()
    if ssh is not None:
        from tools import jetbot_ssh
        from tools.jetbot_status import ina219_bus_volts
        volts1 = ina219_bus_volts(jetbot_ssh.sudo(ssh, "i2cget -y 1 0x41 0x02 w", password))
    time.sleep(1.2)
    beep(1000, 300)
    beep(1000, 300)
    print("ENDED: %s | %.1f s | DR path %.1f m | final DR pose (%.2f, %.2f, %.0f deg) | prompts %s" % (end["reason"], time.time() - t_wall, path, final[0], final[1], math.degrees(final[2]), runner.prompts), flush=True)

    answers = {}
    if not a.dry_run:
        for key, q in (("door_distance_m_tape", "Distance from the robot to the entrance door (m, tape): "), ("line_of_sight_clear", "Clear line of sight to the entrance (y/n): "),
                       ("near_boundary_or_furniture", "Adjacent wall or furniture within 1 m (y/n): "), ("collisions", "Collisions or touches (number): ")):
            try:
                answers[key] = input(q).strip()
            except EOFError:
                answers[key] = ""
    out_dir = Path(a.out)
    n = 1 + len(list(out_dir.glob(a.label + "_*"))) if out_dir.exists() else 1
    run_dir = out_dir / ("%s_%d" % (a.label, n))
    run_dir.mkdir(parents=True, exist_ok=True)
    with open(run_dir / "log.csv", "w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(("t", "x_m", "y_m", "yaw_rad", "cmd_v", "cmd_w", "state", "handshake_in_view"))
        wr.writerows(rows)
    vp = [p for _, name, p in runner.events if name == "VANTAGE_REACHED"]
    chosen = getattr(runner, "vantage", None)
    target = (chosen.x_m, chosen.y_m) if chosen is not None else a.vantage
    if grid is not None:
        grid.save(run_dir / "grid.npz")
    summary = {"mode": "declared_room" if a.door is not None else "manual_vantage", "door": a.door, "box": a.box, "walls": a.wall, "entrance_mode": a.entrance if a.door is not None else None,
               "chosen_vantage": None if chosen is None else {"x": round(float(chosen.x_m), 3), "y": round(float(chosen.y_m), 3), "door_distance_m": round(float(chosen.door_distance_m), 3),
                                                              "boundary_distance_m": round(float(chosen.boundary_distance_m), 3)},
               "phase1_notes": getattr(runner, "notes", []), "door_bearing_error_deg": getattr(runner, "door_bearing_error_deg", None),
               "label": a.label, "dry_run": a.dry_run, "no_robot": a.no_robot, "end_reason": end["reason"], "success": end["reason"] == "STANDBY reached",
               "vantage_target": target, "room_centre": a.centre, "dr_pose_at_vantage_reached": vp[0] if vp else None,
               "dr_error_at_vantage_m": round(math.hypot(vp[0][0] - target[0], vp[0][1] - target[1]), 3) if vp and target else None,
               "state_changes": runner.log, "events": [(round(t, 2), name) for t, name, _ in runner.events], "prompts": runner.prompts,
               "handshake": {"mode": a.handshake, "rule": {"span_s": a.hs_span, "min_frames": a.hs_frames, "fraction": a.hs_frac}, "frames": esp["frames"], "in_view_frames": esp["in_view_frames"], "last_inliers": esp["inliers"], "error": esp.get("error")},
               "marker_fixes": end.get("fixes"), "servo_motion": servo_motion(servo_log, model) if servo_log else None, "servo_sightings": len(servo_log), "anchors": a.anchors, "dr_path_m": round(path, 2), "dr_final_pose": [round(v, 3) for v in final], "battery_v_start": volts0, "battery_v_end": volts1,
               "camera_pose_file": a.camera_pose, "obstacle_check": bool(a.camera_pose), "tape_answers": answers, "date": time.strftime("%Y-%m-%d %H:%M")}
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=1))
    if frames_buf:
        (run_dir / "frames").mkdir(exist_ok=True)
        for t_, jpg in frames_buf:
            (run_dir / "frames" / ("%.3f.jpg" % t_)).write_bytes(jpg)
        print("saved %d video frames" % len(frames_buf), flush=True)
    if servo_log:
        with open(run_dir / "servo.csv", "w", newline="") as fh:
            w_ = csv.writer(fh)
            w_.writerow(["t", "range_m", "bearing_rad", "cmd_v", "cmd_w"])
            w_.writerows([tuple(round(v, 4) for v in r) for r in servo_log])
        print("measured from the board (%d sightings; ratio = measured / model): %s" % (len(servo_log), summary["servo_motion"]), flush=True)
    print("saved", run_dir)


if __name__ == "__main__":
    main()
