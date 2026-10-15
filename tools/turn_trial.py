"""One in-place turn trial measured with the ArUco board: the robot turns for --seconds at constant w, the marker bearing before and after (at rest) is the turn angle (the robot rotates about its centre, the camera is about 7 cm off the axis: under 2 deg of error at 1.8 m). No protractor.

  python -m tools.turn_trial 1.0 0.15 --label classroom         # w = 1.0 (left positive) for 0.15 s: about 55 deg on a smooth floor (turn gain 6.48 rad/s)
  python -m tools.turn_trial 0.5 0.4 --label classroom

SETUP: the board 1.0-3.0 m away; rotate the robot BY HAND first so the marker starts on the side the robot turns AWAY from: for a left turn (w > 0) the robot points about 30 deg to the RIGHT of the board
(marker on the left, bearing about +30), so that the marker ends on the right after about 60 deg. Keep the turn under about 80 deg (the marker must stay detectable). E-stop armed (arm once); press R1 whenever
you are ready within --wait seconds after the beeps (the tool starts once R1 has been held for 0.5 s) and keep it down until the two short beeps.
OUTPUT: data/turn_runs/<label>_w<w>_<seconds>s_<n>.csv (t, bearing_deg, range_m, cmd_w) and a summary: turned angle (left +) = bearing before - bearing after, wheel seconds from the robot's log,
degrees per wheel second and the turn gain in rad/s per unit of w.
"""
import argparse
import csv
import math
import os
import threading
import time

import numpy as np

from sentry.config import load
from sentry.net.udp_tx import UDPSender
from sentry.net.zmq_rx import ZMQReceiver
from sentry.perception.camera import CameraGeometry
from tools import jetbot_ssh
from tools.calibrate_motion import LOG, _sh, moving_seconds
from tools.jetbot_status import ina219_bus_volts
from tools.speed_trial import ESTOP_LATCH, beep, marker_range


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("w", type=float)
    ap.add_argument("seconds", type=float)
    ap.add_argument("--label", default="run")
    ap.add_argument("--wait", type=float, default=20.0, help="seconds to wait for R1 after the beeps")
    ap.add_argument("--ip", default="auto", help="the robot's address, or auto to search the network")
    ap.add_argument("--user", default="jetbot")
    ap.add_argument("--password", default=os.environ.get("JETBOT_PASSWORD"))
    ap.add_argument("--camera", default="calib/camera.json")
    ap.add_argument("--pose", default="calib/camera_pose_nowedge.json", help="only K and D are used here")
    ap.add_argument("--out", default="data/turn_runs")
    a = ap.parse_args()
    if not (0 < abs(a.w) <= 1 and 0 < a.seconds <= 1.5):
        ap.error("0 < |w| <= 1 and 0 < seconds <= 1.5 (a longer turn leaves the marker's field of view)")
    from sentry.net.discover import resolve
    a.ip = resolve(a.ip)
    password = jetbot_ssh.password(a.password)
    S = load()["calibration"]["aruco_marker_m"] / 2
    g = CameraGeometry.from_files(a.camera, a.pose)
    obj = np.array([[-S, S, 0], [S, S, 0], [S, -S, 0], [-S, -S, 0]], np.float64)
    c = jetbot_ssh.connect(a.ip, a.user, password)
    before = int(_sh(c, "wc -l < %s" % LOG).strip() or 0)
    cmd = {"w": 0.0}
    done = threading.Event()

    def sender():
        s = UDPSender(a.ip, load()["net"]["control_port"], 30)
        try:
            while not done.is_set():
                s.send(0.0, cmd["w"])
                time.sleep(s.period_s)
        finally:
            s.close(stop=True)

    th = threading.Thread(target=sender)
    th.start()
    rows = []
    with ZMQReceiver() as rx:
        r0 = None
        for _ in range(8):
            f = rx.read(timeout=5)
            r0 = marker_range(g, obj, f.frame_bgr) if f is not None else None
            if r0:
                break
        if r0 is None or not 1.0 <= r0[0] <= 3.0 or abs(r0[1]) > 55:
            done.set()
            th.join()
            print("ABORT: start check failed (%s)" % ("marker not seen" if r0 is None else "marker %.2f m away at %+.0f deg: need 1-3 m and within 55 deg" % r0))
            raise SystemExit(1)
        want = "left" if a.w > 0 else "right"
        print("start: marker %.2f m away, bearing %+.1f deg. The robot will turn %s: the marker should start on the %s side (bearing %s) so that it stays in view." % (
            r0[0], r0[1], want, want, "+" if a.w > 0 else "-"), flush=True)
        if (a.w > 0) != (r0[1] > 10) and abs(r0[1]) < 10:
            print("  note: the marker is near the centre: after the turn it may leave the view; rotate the robot by hand first and rerun if the result says so")
        t0 = time.time()
        for _ in range(3):
            beep(1500, 300)
        t_end_wait = time.time() + a.wait
        t_go = t_cmd1 = None
        held_since, last_poll = None, 0.0
        while True:
            now = time.time()
            if t_go is None and now - last_poll >= 0.25:
                last_poll = now
                held = _sh(c, "test -e %s && echo no || echo yes" % ESTOP_LATCH).strip() == "yes"
                held_since = (held_since or now) if held else None
                if held_since and now - held_since >= 0.5:
                    t_go = now
                    print("R1 held: starting the turn", flush=True)
                elif now > t_end_wait:
                    done.set()
                    th.join()
                    print("ABORT: R1 was not held (and the e-stop armed) within %.0f s of the beeps" % a.wait)
                    raise SystemExit(1)
            if t_go is not None and t_cmd1 is None and cmd["w"] == 0.0 and now >= t_go:
                cmd["w"] = a.w
                t_cmd0 = now
            if t_go is not None and cmd["w"] != 0.0 and now - t_cmd0 >= a.seconds:
                cmd["w"] = 0.0
                t_cmd1 = now
            if t_cmd1 is not None and now - t_cmd1 > 2.0:
                break
            f = rx.read(timeout=5)
            if f is None:
                break
            mr = marker_range(g, obj, f.frame_bgr)
            if mr is not None:
                rows.append((time.time() - t0, mr[1], mr[0], cmd["w"]))
    done.set()
    th.join()
    time.sleep(0.6)
    moving = moving_seconds(_sh(c, "tail -n +%d %s" % (before + 1, LOG)).splitlines())
    volts = ina219_bus_volts(jetbot_ssh.sudo(c, "i2cget -y 1 0x41 0x02 w", password))
    os.makedirs(a.out, exist_ok=True)
    n = 1 + len([x for x in os.listdir(a.out) if x.startswith("%s_w%g_%gs_" % (a.label, a.w, a.seconds))])
    path = os.path.join(a.out, "%s_w%g_%gs_%d.csv" % (a.label, a.w, a.seconds, n))
    with open(path, "w", newline="") as fh:
        csv.writer(fh).writerows([("t", "bearing_deg", "range_m", "cmd_w")] + [("%.3f" % t, "%.2f" % b, "%.3f" % r, w) for t, b, r, w in rows])
    arr = np.array(rows)
    print("TURN w=%+.2f for %.2f s | the wheels turned %.2f s | battery %.2f V | %d frames" % (a.w, a.seconds, moving, volts, len(arr)))
    if len(arr) < 8 or moving < 0.05:
        print("  no usable turn (R1 not held in time, or the marker was not seen): repeat")
    else:
        pre = arr[arr[:, 3] == 0][:8, 1] if (arr[:, 3] == 0).any() else arr[:5, 1]
        post = arr[-10:, 1]
        turned = float(np.median(pre) - np.median(post))                    # left turn: the marker moves to the right: bearing decreases
        print("  bearing %+.1f -> %+.1f deg: TURNED %+.1f deg (left +) in %.2f wheel seconds = %.0f deg/s = %.2f rad/s (per unit of w: %.2f rad/s; old gain 6.48)" % (
            np.median(pre), np.median(post), turned, moving, turned / moving, math.radians(turned) / moving, math.radians(turned) / moving / a.w))
        if abs(np.median(post)) > 60 or abs(np.median(pre)) > 60:
            print("  warning: the marker was near the edge of the view; the angle may be off")
    print("  saved", path)
    beep(1000, 300)
    beep(1000, 300)


if __name__ == "__main__":
    main()
