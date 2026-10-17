"""Live Phase 1 exploration (the Week 2 T2 session item): the robot drives itself around a cleared area, avoiding furniture, while the map is built.

  python -m tools.explore_live --label classroom --floor glossy --camera-pose calib/camera_pose_classroom_1015.json --dry-run       # NO commands: live frames, detector, decisions
  python -m tools.explore_live --label classroom --floor glossy --camera-pose calib/camera_pose_classroom_1015.json --seconds 180   # the T2 run

SETUP (read before every drive): a CLEARED area at least 3 x 3 m around the start with furniture the detector knows (chair, couch, plant, bed, table, tv,
fridge, suitcase); walls and anything else are NOT detected, so --box (default 1.5 m half-width from the start, by dead reckoning) keeps the run away from
walls; PEOPLE ARE NOT OBSTACLES to the detector: stay out of the arena; the camera pose file must match the CURRENT mount (run tools.preflight / the strips first);
e-stop armed (hold Start 1.5 s); the operator stands at the edge holding R1 and can stop at any time by releasing R1 or pressing q in this window.
SEQUENCE: start checks (battery, frames, detector, clear front) -> 3 beeps -> HOLD R1 within --wait s -> the run -> stop -> 2 beeps (then release R1).
SAFETY: the robot itself only moves while R1 is held (robot_udp + estop, speed cap 0.3); in addition this tool stops on: R1 released (one poll is enough), the e-stop poll
failing twice, no frame for 0.5 s, a detector error, a stalled control loop (the sender repeats a command for at most 0.25 s), the time limit, or stuck spinning.
Obstacles WITHOUT a distance (glossy-floor chairs, issue #43) count as blocking when their box reaches low in the image (sentry/nav/explore.py).
POSE: dead reckoning from the commands through the measured wheel model (sentry/nav/wheel_model.py), NOT KR's tracker: indicative only (heading error is about +/-10 deg/m).
OUTPUT: data/explore/<label>_<n>/ with log.csv, summary.json (end reason, path, states, nearest obstacle, battery, camera pose, collisions as told by the operator) and grid.npz.
"""
import argparse
import csv
import json
import math
import os
import sys
import threading
import time
from dataclasses import asdict
from pathlib import Path

from sentry.config import load
from sentry.nav.explore import ExploreSettings, Explorer, fresh_command
from sentry.nav.gridmap import OccupancyGrid, Pose2D
from sentry.nav.wheel_model import WheelModel
from sentry.net.discover import resolve
from sentry.net.udp_tx import UDPSender
from sentry.net.zmq_rx import ZMQReceiver
from sentry.perception.obstacle import ObstacleDetector
from tools import jetbot_ssh
from tools.calibrate_motion import _sh
from tools.jetbot_status import ina219_bus_volts

ESTOP_LATCH = "/home/jetbot/sentry/ESTOP"
MIN_BATTERY_V = 11.3
START_CLEAR_EXTRA_M = 0.25      # at the start nothing may be nearer than stop_m + this


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
        return msvcrt.kbhit() and msvcrt.getwch().lower() == "q"
    except ImportError:
        return False


def nearest_resolved(obs):
    d = [o.ground.distance_m for o in obs.obstacles if o.ground is not None]
    return min(d) if d else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="run")
    ap.add_argument("--floor", choices=("glossy", "matte", "unknown"), default="unknown", help="unknown -> every obstacle is unresolved (the robot then only turns away by box position)")
    ap.add_argument("--camera-pose", required=True, help="camera pose JSON of the CURRENT mount (required on purpose: a stale pose gives wrong distances)")
    ap.add_argument("--seconds", type=float, default=180.0)
    ap.add_argument("--box", type=float, default=1.5, help="half-width of the allowed square around the start (m, dead reckoning)")
    ap.add_argument("--dry-run", action="store_true", help="no commands are sent and R1 is not needed; live frames, detector and decisions only")
    ap.add_argument("--wait", type=float, default=30.0, help="seconds to wait for R1 after the beeps")
    ap.add_argument("--ip", default="auto")
    ap.add_argument("--user", default="jetbot")
    ap.add_argument("--password", default=os.environ.get("JETBOT_PASSWORD"))
    ap.add_argument("--out", default="data/explore")
    a = ap.parse_args()
    if not 5 <= a.seconds <= 300 or not 0.5 <= a.box <= 3.0:
        ap.error("seconds in [5, 300], box in [0.5, 3.0]")
    if a.dry_run:
        a.seconds = min(a.seconds, 60.0)
    a.ip = resolve(a.ip)
    password = jetbot_ssh.password(a.password)
    settings = ExploreSettings(box_half_m=a.box, max_time_s=a.seconds)
    ssh = jetbot_ssh.connect(a.ip, a.user, password)

    volts0 = ina219_bus_volts(jetbot_ssh.sudo(ssh, "i2cget -y 1 0x41 0x02 w", password))
    print("battery %.2f V" % volts0)
    if volts0 < MIN_BATTERY_V:
        raise SystemExit("ABORT: battery %.2f V < %.1f V: charge first" % (volts0, MIN_BATTERY_V))

    det = ObstacleDetector.from_config(camera_pose_path=a.camera_pose, floor_type=a.floor)
    geo = det.geometry
    print("camera pose %s | floor %s | box +/-%.1f m | %.0f s" % (geo.session, a.floor, a.box, a.seconds))
    explorer = Explorer(settings, geo.size)
    grid = OccupancyGrid.from_config()
    model = WheelModel()
    control_port = load()["net"]["control_port"]
    cmd = {"v": 0.0, "w": 0.0, "t": time.time()}
    done = threading.Event()
    end = {"reason": None}
    r1 = {"held": True, "fail": 0}
    threads = []
    x = y = yaw = 0.0
    path_m, rows, state_t = 0.0, [], {}
    min_near, n_unres, det_ms = None, 0, []
    t0 = time.time()
    run_dir = None

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

    # ---- start checks -------------------------------------------------------------------------------------------
    rx = ZMQReceiver(ip=a.ip)
    rx.start()
    try:
        first = None
        for _ in range(40):
            f = rx.read(timeout=1.0)
            if f is not None:
                first = f
                break
        if first is None:
            raise SystemExit("ABORT: no video frame from the robot")
        worst = None
        for _ in range(5):
            f = rx.read(timeout=1.0)
            if f is None:
                raise SystemExit("ABORT: video stopped during the start check")
            obs = det(f.frame_bgr, time.time(), mode="explore", floor_type=a.floor)
            blocked, _ = explorer.blocking(obs)
            near = nearest_resolved(obs)
            if blocked or (near is not None and near < settings.stop_m + START_CLEAR_EXTRA_M):
                worst = "an obstacle is within %.2f m (or one without a distance is low in the image): clear the front" % (settings.stop_m + START_CLEAR_EXTRA_M)
        if worst:
            raise SystemExit("ABORT: " + worst)
        print("start checks passed: frames, detector, clear front")

        # ---- wait for R1 ---------------------------------------------------------------------------------------------
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

        # ---- threads: the command sender and the R1 / SSH watcher start only now
        threads.extend([threading.Thread(target=sender), threading.Thread(target=watcher)])
        for th in threads:
            th.start()

        # ---- the run ------------------------------------------------------------------------------------------
        out_dir = Path(a.out)
        n = 1 + len([p for p in out_dir.glob(a.label + "_*")]) if out_dir.exists() else 1
        run_dir = out_dir / ("%s_%d" % (a.label, n))
        run_dir.mkdir(parents=True, exist_ok=True)
        t0 = last = time.time()
        prev = (0.0, 0.0)
        last_print = 0.0
        while end["reason"] is None:
            if key_pressed():
                end["reason"] = "operator pressed q"
                break
            f = rx.read(timeout=0.5)
            now = time.time()
            obs, ms = None, 0.0
            if f is not None:
                try:
                    c0 = time.perf_counter()
                    obs = det(f.frame_bgr, now, mode="explore", floor_type=a.floor)
                    ms = (time.perf_counter() - c0) * 1000
                except Exception as exc:
                    end["reason"] = "detector error: %r" % exc
                    break
            dt = min(now - last, 0.2)
            last = now
            if not a.dry_run:                                   # the pose follows what the robot was told to do during dt
                v_m, w_r = model.body_speeds(*prev)
                x += v_m * math.cos(yaw) * dt
                y += v_m * math.sin(yaw) * dt
                yaw += w_r * dt
                path_m += abs(v_m) * dt
            c = explorer.step(obs, (x, y, yaw), dt)
            prev = (c.v, c.w)
            cmd.update(v=c.v, w=c.w, t=now)
            state_t[c.state] = state_t.get(c.state, 0.0) + dt
            if obs is not None:
                grid.update(Pose2D(x, y, yaw), obs.ground_points)
                near = nearest_resolved(obs)
                if near is not None and (min_near is None or near < min_near):
                    min_near = near
                n_unres += int(obs.unresolved)
                det_ms.append(ms)
                rows.append((round(now - t0, 3), round(x, 3), round(y, 3), round(yaw, 3), c.v, round(c.w, 3), c.state, c.reason,
                             "" if near is None else round(near, 3), len(obs.obstacles), int(obs.unresolved), round(obs.repulsive_w, 3), round(ms, 1)))
            if now - last_print >= 0.5:
                last_print = now
                print("t %5.1f  %-7s v %.2f w %+.2f  pos (%+.2f, %+.2f) yaw %+4.0f  nearest %s  unresolved %s  detect %.0f ms" % (
                    now - t0, c.state, c.v, c.w, x, y, math.degrees(yaw), "-" if obs is None or nearest_resolved(obs) is None else "%.2f" % nearest_resolved(obs),
                    "-" if obs is None else int(obs.unresolved), ms), flush=True)
            if c.state == "STOP":
                end["reason"] = "policy stop: " + c.reason
                break
    finally:
        cmd.update(v=0.0, w=0.0, t=time.time())        # the sender then repeats zero; its close() sends a final stop
        time.sleep(0.4)
        done.set()
        for th in threads:
            th.join()
        rx.close()

    volts1 = ina219_bus_volts(jetbot_ssh.sudo(ssh, "i2cget -y 1 0x41 0x02 w", password))
    time.sleep(1.2)
    beep(1000, 300)
    beep(1000, 300)
    print("ENDED: %s | %.1f s | path %.1f m | battery %.2f -> %.2f V" % (end["reason"], time.time() - t0, path_m, volts0, volts1))
    collisions = None
    if not a.dry_run:
        try:
            raw = input("Collisions or touches during the run (number, Enter to skip): ").strip()
            collisions = int(raw) if raw else None
        except (EOFError, ValueError):
            collisions = None
    if run_dir is None:
        raise SystemExit("nothing to save: the run never started")
    with open(run_dir / "log.csv", "w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(("t", "x_m", "y_m", "yaw_rad", "cmd_v", "cmd_w", "state", "reason", "nearest_m", "n_obstacles", "any_unresolved", "repulsive_w", "detect_ms"))
        wr.writerows(rows)
    grid.save(run_dir / "grid.npz")
    summary = {"label": a.label, "dry_run": a.dry_run, "end_reason": end["reason"], "seconds": round(time.time() - t0, 1), "path_m_dead_reckoned": round(path_m, 2),
               "time_in_state_s": {k: round(v, 1) for k, v in state_t.items()}, "min_resolved_distance_m": min_near, "frames_with_unresolved_obstacle": n_unres,
               "frames": len(rows), "detect_ms_mean": round(sum(det_ms) / len(det_ms), 1) if det_ms else None, "battery_v_start": volts0, "battery_v_end": volts1,
               "camera_pose_session": geo.session, "camera_pose_file": a.camera_pose, "floor_type": a.floor, "settings": asdict(settings),
               "collisions_reported_by_operator": collisions, "date": time.strftime("%Y-%m-%d %H:%M")}
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=1))
    print("saved", run_dir)


if __name__ == "__main__":
    main()
