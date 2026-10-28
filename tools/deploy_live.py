"""Live Phase 1 deployment (the T2 deployment sequence): the robot drives to the sweet spot, the laptop prompts, the ESP32 handshake is checked, the robot backs up to standby.

  python -m tools.deploy_live --label cafe --vantage 1.2 0.6 --centre 3.0 0.0 --handshake data/handshake/cafe_arch --no-robot     # laptop rehearsal: real ESP32 handshake + prompts, a simulated pose
  python -m tools.deploy_live --label class --vantage 1.8 0.5 --centre 4.0 0.0 --handshake data/handshake/class_door --dry-run    # robot connected, NO motor commands
  python -m tools.deploy_live --label class --vantage 1.8 0.5 --centre 4.0 0.0 --handshake data/handshake/class_door --camera-pose calib/camera_pose_x.json   # the real run

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


def fresh_flag(feed, now, max_age=ESP_FRESH_S):
    """feed: dict with in_view and t (when the detector last answered), or None -> True only for a fresh in-view answer."""
    return bool(feed and feed.get("t") is not None and now - feed["t"] <= max_age and feed.get("in_view"))


def control_loop(runner, model, cmd, end, get_flag, get_link, seconds, clock=time.time, sleep=time.sleep, rate_hz=30.0, key=lambda: None):
    """The 30 Hz loop: dead-reckon the pose from the command the robot was given, step the runner, publish the command, check the safety conditions.
    get_link(now) -> None (no robot) or dict(stale=bool, blocked=bool). Returns (rows, final pose, dead-reckoned path length). Ends by setting end['reason']."""
    x = y = yaw = 0.0
    path, prev, rows, manual_until = 0.0, (0.0, 0.0), [], 0.0
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
        link = get_link(now)
        if link is not None and link["stale"]:
            end["reason"] = "no robot frame for %.1f s" % LINK_STALE_S
            break
        if k == "v":
            manual_until = now + 0.5                          # the key latches for 0.5 s: the runner needs 3 consecutive in-view ticks
        flag = get_flag(now) or now < manual_until
        v, w = runner.step(t, (x, y, yaw), flag)
        if link is not None and link["blocked"] and v > 0.0:
            end["reason"] = "obstacle ahead while driving (stopped; this tool does not avoid)"
            v = w = 0.0
            cmd.update(v=0.0, w=0.0, t=now)
            break
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
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--label", default="run")
    ap.add_argument("--vantage", type=float, nargs=2, required=True, metavar=("X", "Y"))
    ap.add_argument("--centre", type=float, nargs=2, required=True, metavar=("X", "Y"))
    ap.add_argument("--handshake", default="manual", help="folder with ref/ and sweep/ from tools.handshake_test, or 'manual' (press v)")
    ap.add_argument("--esp-ip", default="10.195.93.9")
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
    ap.add_argument("--no-audio", action="store_true", help="do not speak (rehearsal in a quiet room); the prompts are still logged")
    a = ap.parse_args()
    a.dry_run = a.dry_run or a.no_robot
    if not 10 <= a.seconds <= 300:
        ap.error("seconds in [10, 300]")

    model, done = WheelModel(), threading.Event()
    cmd = {"v": 0.0, "w": 0.0, "t": time.time()}
    end = {"reason": None}
    r1 = {"held": True, "fail": 0}
    link = {"t": time.time(), "blocked": False}
    esp = {"in_view": False, "t": None, "frames": 0, "in_view_frames": 0, "inliers": 0}
    threads, ssh, rx, volts0, volts1, password = [], None, None, None, None, None
    speaker = AudioPromptPlayer(sender=LocalSpeaker(backend=(lambda path: None) if a.no_audio else None))

    detector = None if a.handshake == "manual" else make_handshake(a.handshake)

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
                esp.update(in_view=bool(res.in_view), t=time.time(), inliers=int(res.inliers))
                esp["frames"] += 1
                esp["in_view_frames"] += int(res.in_view)
        except Exception as exc:
            esp["error"] = repr(exc)

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
                if obs_det is not None:
                    try:
                        obs = obs_det(f.frame_bgr, time.time(), mode="explore", floor_type=a.floor)
                        link["blocked"] = explorer.blocking(obs)[0]
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
    for th in threads:
        th.daemon = True
        th.start()

    sm = StateMachine(StateMachineConfig())
    runner = DeployRunner(sm, speaker, vantage_xy=a.vantage, centre_xy=a.centre, settings=DeploySettings())
    get_link = (lambda now: None) if a.no_robot else (lambda now: {"stale": now - link["t"] > LINK_STALE_S, "blocked": link["blocked"]})
    t_wall = time.time()
    try:
        rows, final, path = control_loop(runner, model, cmd, end, lambda now: fresh_flag(esp, now), get_link, a.seconds, key=key_pressed)
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
    summary = {"label": a.label, "dry_run": a.dry_run, "no_robot": a.no_robot, "end_reason": end["reason"], "success": end["reason"] == "STANDBY reached",
               "vantage_target": a.vantage, "room_centre": a.centre, "dr_pose_at_vantage_reached": vp[0] if vp else None,
               "dr_error_at_vantage_m": round(math.hypot(vp[0][0] - a.vantage[0], vp[0][1] - a.vantage[1]), 3) if vp else None,
               "state_changes": runner.log, "events": [(round(t, 2), name) for t, name, _ in runner.events], "prompts": runner.prompts,
               "handshake": {"mode": a.handshake, "frames": esp["frames"], "in_view_frames": esp["in_view_frames"], "last_inliers": esp["inliers"], "error": esp.get("error")},
               "dr_path_m": round(path, 2), "dr_final_pose": [round(v, 3) for v in final], "battery_v_start": volts0, "battery_v_end": volts1,
               "camera_pose_file": a.camera_pose, "obstacle_check": bool(a.camera_pose), "tape_answers": answers, "date": time.strftime("%Y-%m-%d %H:%M")}
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=1))
    print("saved", run_dir)


if __name__ == "__main__":
    main()
