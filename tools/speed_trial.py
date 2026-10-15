"""One speed trial toward an ArUco board: constant v for --seconds, the marker range recorded per frame, speed measured from the range (no tape).

  python -m tools.speed_trial 0.7 4 --label classroom            # open loop (default): the robot goes wherever its heading takes it
  python -m tools.speed_trial 0.6 4 --label classroom --steer    # also steer toward the marker (P controller; it lags about 0.5 s on the rugged floor, so it does not hold the heading)

SETUP: the board (id 0, 150 mm, `aruco_marker_m` in config.toml) upright at the far end, facing the robot, 1.4-2.6 m away (the start check refuses otherwise); the floor CLEAR for 1 m on both
sides of the path (on 2026-10-15 an open-loop run veered 1 m sideways into a bean bag); e-stop armed.
SEQUENCE: start check -> 3 beeps -> HOLD R1 (any time within --wait seconds; the tool polls the robot's e-stop latch and starts the command once R1 has been held for 0.5 s) -> v for --seconds -> stop -> 1.5 s of rest -> 2 short beeps (only then release R1 and touch the robot).
GUARDS: the commands stop when the marker is closer than --stop-at m, not seen for 0.4 s, or more than 25 deg off the heading. The robot moves only while R1 is held; the real wheel seconds come
from the robot's log, so a late or early R1 does not spoil the speed (distance / wheel seconds).
OUTPUT: data/speed_runs/<label>_v<v>_<n>.csv (t, range_m, bearing_deg, cmd_v, cmd_w) and a printed summary: net displacement / wheel seconds = AVERAGE SPEED (robust), plus the steady speed and
start-up lag from tools.speedfit when the marker was seen densely enough.
"""
import argparse
import csv
import math
import os
import sys
import threading
import time

import cv2
import numpy as np

from sentry.config import load
from sentry.net.udp_tx import UDPSender
from sentry.net.zmq_rx import ZMQReceiver
from sentry.perception.camera import CameraGeometry
from sentry.perception.camera_pose import detect_corners
from tools import jetbot_ssh
from tools.calibrate_motion import LOG, _sh, moving_seconds
from tools.jetbot_status import ina219_bus_volts
from tools.speedfit import fit_start

LOST_S, MAX_BEARING = 0.4, 25.0
ESTOP_LATCH = "/home/jetbot/sentry/ESTOP"
KP, W_GAIN = 2.5, 6.48                                   # --steer: w = KP * bearing(rad) / W_GAIN
MIN_PWM, MAX_SPEED = 0.12, 0.3


def beep(freq, ms):
    try:
        import winsound
        winsound.Beep(freq, ms)
    except ImportError:
        sys.stdout.write("\a"); sys.stdout.flush()


def marker_range(geometry, obj, raw):
    """(floor-plane distance in m from the camera to the marker, bearing in deg with left +), or None without a marker. Detection in the RAW frame, only the corners are undistorted."""
    found = detect_corners(raw)
    if not found:
        return None
    K = geometry.K
    c = geometry.undistort_points(found[0][1])
    n, rv, tv, er = cv2.solvePnPGeneric(obj, c, K, None, flags=cv2.SOLVEPNP_IPPE)
    best = None
    for r, t, e in zip(rv, tv, er):
        R, _ = cv2.Rodrigues(r)
        t = t.reshape(3)
        C = -R.T @ t
        if C[2] > 0 and np.isfinite(e).all() and (best is None or float(e.ravel()[0]) < best[0]):
            best = (float(e.ravel()[0]), C)
    if best is None:
        return None
    C = best[1]
    return math.hypot(C[0], C[2]), -math.degrees(math.atan((c.mean(0)[0] - K[0, 2]) / K[0, 0]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("v", type=float)
    ap.add_argument("seconds", type=float)
    ap.add_argument("--label", default="run")
    ap.add_argument("--steer", action="store_true", help="steer toward the marker (off by default)")
    ap.add_argument("--wait", type=float, default=20.0, help="seconds to wait for R1 after the beeps; the command starts once R1 has been held for 0.5 s")
    ap.add_argument("--stop-at", type=float, default=0.8, help="stop the commands when the marker is closer than this (m)")
    ap.add_argument("--ip", default="auto", help="the robot's address, or auto to search the network")
    ap.add_argument("--user", default="jetbot")
    ap.add_argument("--password", default=os.environ.get("JETBOT_PASSWORD"))
    ap.add_argument("--camera", default="calib/camera.json")
    ap.add_argument("--pose", default="calib/camera_pose_nowedge.json", help="only K and D are used here")
    ap.add_argument("--out", default="data/speed_runs")
    a = ap.parse_args()
    if not 0 < a.v <= 1 or not 0 < a.seconds <= 8:
        ap.error("v in (0, 1], seconds in (0, 8]")
    if a.v < MIN_PWM / MAX_SPEED:
        print("note: v < %.2f is a clean stop at speed cap %.1f (motor value below min_pwm %.2f): the robot will not move" % (MIN_PWM / MAX_SPEED, MAX_SPEED, MIN_PWM))
    from sentry.net.discover import resolve
    a.ip = resolve(a.ip)
    password = jetbot_ssh.password(a.password)
    marker_m = load()["calibration"]["aruco_marker_m"]
    S = marker_m / 2
    g = CameraGeometry.from_files(a.camera, a.pose)
    obj = np.array([[-S, S, 0], [S, S, 0], [S, -S, 0], [-S, -S, 0]], np.float64)
    c = jetbot_ssh.connect(a.ip, a.user, password)
    before = int(_sh(c, "wc -l < %s" % LOG).strip() or 0)
    cmd = {"v": 0.0, "w": 0.0}
    done = threading.Event()

    def sender():
        s = UDPSender(a.ip, load()["net"]["control_port"], 30)
        try:
            while not done.is_set():
                s.send(cmd["v"], cmd["w"])
                time.sleep(s.period_s)
        finally:
            s.close(stop=True)

    th = threading.Thread(target=sender)
    th.start()
    rows, why, t_cmd0, t_cmd1 = [], "time", None, None

    def stop(reason):
        nonlocal why, t_cmd1
        cmd["v"] = cmd["w"] = 0.0
        t_cmd1 = t_cmd1 or time.time()
        why = reason

    with ZMQReceiver() as rx:
        r0 = None
        for _ in range(8):
            f = rx.read(timeout=5)
            r0 = marker_range(g, obj, f.frame_bgr) if f is not None else None
            if r0:
                break
        if r0 is None or not 1.4 <= r0[0] <= 2.6:
            done.set()
            th.join()
            print("ABORT: start check failed (%s)" % ("marker not seen" if r0 is None else "marker %.2f m away, need 1.4-2.6 m" % r0[0]))
            raise SystemExit(1)
        print("start: marker %.2f m away, bearing %+.1f deg. HOLD R1 at the beeps." % r0, flush=True)
        t0 = time.time()
        for _ in range(3):
            beep(1500, 300)
        t_wait_end = time.time() + a.wait
        t_go = None                                                  # set when R1 has been held for 0.5 s
        r1_since = None
        last_poll = 0.0
        seen = time.time()
        while True:
            now = time.time()
            if t_go is None and now - last_poll >= 0.25:             # the e-stop latch file exists whenever motion is NOT allowed (R1 up or not armed)
                last_poll = now
                held = _sh(c, "test -e %s && echo no || echo yes" % ESTOP_LATCH).strip() == "yes"
                r1_since = (r1_since or now) if held else None
                if r1_since and now - r1_since >= 0.5:
                    t_go = now
                    print("R1 held: starting the command", flush=True)
                elif now > t_wait_end:
                    done.set()
                    th.join()
                    print("ABORT: R1 was not held (and the e-stop armed) within %.0f s of the beeps" % a.wait)
                    raise SystemExit(1)
            if t_cmd0 is None and t_go is not None and now >= t_go:
                cmd["v"] = a.v
                t_cmd0 = now
            if t_cmd0 is not None and t_cmd1 is None and now - t_cmd0 >= a.seconds:
                cmd["v"] = cmd["w"] = 0.0
                t_cmd1 = now
            if t_cmd1 is not None and now - t_cmd1 > 1.5:
                break
            f = rx.read(timeout=5)
            if f is None:
                stop("no frames")
                break
            mr = marker_range(g, obj, f.frame_bgr)
            now = time.time()
            if mr is None:
                if cmd["v"] > 0 and now - seen > LOST_S:
                    stop("marker lost")
                continue
            seen = now
            if cmd["v"] > 0 and a.steer:
                wmax = max(0.0, min(0.2, a.v - MIN_PWM / MAX_SPEED - 1e-3))        # both wheels must stay above the dead zone
                cmd["w"] = max(-wmax, min(wmax, KP * math.radians(mr[1]) / W_GAIN))
            rows.append((now - t0, mr[0], mr[1], cmd["v"], cmd["w"]))
            if cmd["v"] > 0 and mr[0] < a.stop_at:
                stop("marker closer than %.1f m" % a.stop_at)
            elif cmd["v"] > 0 and abs(mr[1]) > MAX_BEARING:
                stop("marker %.0f deg off the heading (guard %.0f)" % (mr[1], MAX_BEARING))
    done.set()
    th.join()
    time.sleep(0.6)
    moving = moving_seconds(_sh(c, "tail -n +%d %s" % (before + 1, LOG)).splitlines())
    volts = ina219_bus_volts(jetbot_ssh.sudo(c, "i2cget -y 1 0x41 0x02 w", password))
    os.makedirs(a.out, exist_ok=True)
    n = 1 + len([x for x in os.listdir(a.out) if x.startswith("%s_v%g_" % (a.label, a.v))])
    path = os.path.join(a.out, "%s_v%g_%d.csv" % (a.label, a.v, n))
    with open(path, "w", newline="") as fh:
        csv.writer(fh).writerows([("t", "range_m", "bearing_deg", "cmd_v", "cmd_w")] + [("%.3f" % t, "%.4f" % d, "%.2f" % b, v_, "%.4f" % w_) for t, d, b, v_, w_ in rows])
    arr = np.array(rows)
    print("TRIAL v=%.2f, %.1f s commanded (%s), ended by: %s | the wheels turned %.2f s | battery %.2f V | %d frames" % (a.v, a.seconds, "steered" if a.steer else "open loop", why, moving, volts, len(arr)))
    if len(arr) and moving > 0.5:
        pre = arr[arr[:, 3] == 0][:8, 1] if (arr[:, 3] == 0).any() else arr[:5, 1]
        post = arr[-10:, 1]
        disp = float(np.median(pre) - np.median(post))
        print("  NET DISPLACEMENT %.3f m (start %.2f, final %.2f, medians) in %.2f wheel seconds = AVERAGE SPEED %.3f m/s (%.3f per unit of command)" % (disp, np.median(pre), np.median(post), moving, disp / moving, disp / moving / a.v))
        print("  marker bearing: start %+.1f deg, at rest %+.1f deg (a change beyond a few degrees = the heading turned)" % (np.median(arr[:8, 2]), np.median(arr[-8:, 2])))
        if a.steer:
            ws = arr[arr[:, 3] > 0][:, 4]
            if len(ws):
                print("  steering: median w %+.3f, mean |w| %.3f" % (np.median(ws), np.mean(abs(ws))))
        t_end = (t_cmd1 - t0 + 0.5) if t_cmd1 else arr[-1, 0]
        fit = fit_start(arr[:, 0], arr[:, 1], t_stop=t_end) if len(arr) > 120 else None
        if fit:
            print("  steady speed %.3f m/s (%.3f per unit) | start-up lag tau %.2f s | fit rms %.3f m" % (fit["S"], fit["S"] / a.v, fit["tau"], fit["rms"]))
    if moving <= 0.5:
        print("  no usable motion (R1 not held in time?): repeat")
    print("  saved", path)
    beep(1000, 300)
    beep(1000, 300)


if __name__ == "__main__":
    main()
