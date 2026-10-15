"""One in-place turn trial measured with ArUco markers: the robot turns for --seconds at constant w and the heading change is followed through the whole turn. No protractor.

MULTI-MARKER (several ids placed around the robot, e.g. taped to chairs, 1.5-2.5 m away, about 40-60 deg apart over the arc of the turn, upright, at 0.05-0.25 m height): a marker is a fixed direction in
the room, so the heading is (marker direction - its bearing in the image). The first frame is the reference (heading 0); a marker seen together with a known one gets its direction from it, then carries the
heading on when the known one leaves the view (the camera sees about +-45 deg). Frames where no known marker is visible have no heading; if the chain breaks (only an unknown marker is seen after a gap) the run is
flagged. With ONE marker this is the earlier method: it works while the marker stays in view (turns up to about 80 deg). The camera is about 7 cm off the rotation axis: under 2 deg of parallax at 1.8 m.

  python -m tools.turn_trial 1.0 0.15 --label classroom         # w = 1.0 (left positive) for 0.15 s: about 55 deg on a smooth floor (turn gain 6.48 rad/s)
  python -m tools.turn_trial 0.5 0.4 --label classroom

SETUP: the board 1.0-3.0 m away; rotate the robot BY HAND first so the marker starts on the side the robot turns AWAY from: for a left turn (w > 0) the robot points about 30 deg to the RIGHT of the board
(marker on the left, bearing about +30), so that the marker ends on the right after about 60 deg. Keep the turn under about 80 deg (the marker must stay detectable). E-stop armed (arm once); press R1 whenever
you are ready within --wait seconds after the beeps (the tool starts once R1 has been held for 0.5 s) and keep it down until the two short beeps.
OUTPUT: data/turn_runs/<label>_w<w>_<seconds>s_<n>.csv (t, heading_deg, known_markers, cmd_w, visible_ids) and a summary: turned angle (left +) = bearing before - bearing after, wheel seconds from the robot's log,
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
from tools.speed_trial import ESTOP_LATCH, beep
from sentry.perception.camera_pose import detect_corners


def heading_track(frames):
    """frames: list of (t, {marker_id: bearing_deg}) (bearing positive = marker to the left). -> list of (t, heading_deg or None, number_of_known_markers), heading = change since the first frame (left +)."""
    phi, out, broken = {}, [], False
    for t, d in frames:
        if not d:
            out.append((t, None, 0))
            continue
        if not phi:
            for i, b in d.items():
                phi[i] = b                                  # the first frame is heading 0: the direction of a marker is its bearing
        known = [i for i in d if i in phi]
        if not known:
            out.append((t, None, 0))                        # only unknown markers: no heading (the chain is broken until a known one returns)
            broken = True
            continue
        th = sum(phi[i] - d[i] for i in known) / len(known)
        for i, b in d.items():
            if i not in phi:
                phi[i] = th + b                             # first sighting together with a known marker
        for i in known:                                     # refine a direction from the others (slow average)
            others = [j for j in known if j != i]
            if others:
                phi[i] += 0.1 * (sum(phi[j] - d[j] for j in others) / len(others) + d[i] - phi[i])
        out.append((t, th, len(known)))
    return out


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
    g = CameraGeometry.from_files(a.camera, a.pose)
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
    frames = []
    with ZMQReceiver() as rx:
        seen_ids = {}
        for _ in range(8):
            f = rx.read(timeout=5)
            if f is None:
                continue
            for mid, corners in detect_corners(f.frame_bgr):
                ctr = g.undistort_points(corners).mean(0)
                seen_ids[int(mid)] = -math.degrees(math.atan((ctr[0] - g.K[0, 2]) / g.K[0, 0]))
            if seen_ids:
                break
        if not seen_ids:
            done.set()
            th.join()
            print("ABORT: start check failed (no marker seen)")
            raise SystemExit(1)
        print("start: markers seen %s (bearing, deg: left +). One marker = turns under about 80 deg; several markers all around = any angle. The robot will turn %s." % (
            {k: round(v, 1) for k, v in seen_ids.items()}, "left" if a.w > 0 else "right"), flush=True)
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
            dets = {}
            for mid, corners in detect_corners(f.frame_bgr):
                ctr = g.undistort_points(corners).mean(0)
                dets[int(mid)] = -math.degrees(math.atan((ctr[0] - g.K[0, 2]) / g.K[0, 0]))
            frames.append((time.time() - t0, dets, cmd["w"]))
    done.set()
    th.join()
    time.sleep(0.6)
    moving = moving_seconds(_sh(c, "tail -n +%d %s" % (before + 1, LOG)).splitlines())
    volts = ina219_bus_volts(jetbot_ssh.sudo(c, "i2cget -y 1 0x41 0x02 w", password))
    os.makedirs(a.out, exist_ok=True)
    n = 1 + len([x for x in os.listdir(a.out) if x.startswith("%s_w%g_%gs_" % (a.label, a.w, a.seconds))])
    path = os.path.join(a.out, "%s_w%g_%gs_%d.csv" % (a.label, a.w, a.seconds, n))
    track = heading_track([(t, d) for t, d, _ in frames])
    with open(path, "w", newline="") as fh:
        csv.writer(fh).writerows([("t", "heading_deg", "known_markers", "cmd_w", "visible_ids")] + [
            ("%.3f" % t, "" if h is None else "%.2f" % h, k, w, " ".join(str(i) for i in sorted(d))) for (t, h, k), (_, d, w) in zip(track, frames)])
    print("TURN w=%+.2f for %.2f s | the wheels turned %.2f s | battery %.2f V | %d frames, markers seen: %s" % (
        a.w, a.seconds, moving, volts, len(frames), sorted({i for _, d, _ in frames for i in d})))
    valid = [(t, h) for t, h, _ in track if h is not None]
    on = [t for t, _, w in frames if w != 0.0]
    if len(valid) < 12 or moving < 0.05 or not on:
        print("  no usable turn (R1 not held in time, or no marker was seen): repeat")
    else:
        t_a, t_b = min(on), max(on)
        pre = [h for t, h in valid if t < t_a][:8]
        post = [h for t, h in valid if t > t_b + 0.8][-10:]
        gaps = sum(1 for t, h, _ in track if h is None and t_a - 0.2 <= t <= t_b + 0.8)
        if not pre or not post:
            print("  no heading before the command or at rest afterwards: the markers were not visible at both ends; repeat with markers all around")
        else:
            turned = float(np.median(post) - np.median(pre))
            hs = np.array(valid)
            peak = max((hs[k + 3, 1] - hs[k, 1]) / max(hs[k + 3, 0] - hs[k, 0], 1e-3) for k in range(len(hs) - 3))
            print("  TURNED %+.1f deg (left +) in %.2f wheel seconds = %.0f deg/s = %.2f rad/s per wheel second (per unit of w: %.2f rad/s; old gain 6.48); peak rate %.0f deg/s; per COMMANDED second %.2f rad/s" % (
                turned, moving, turned / moving, math.radians(turned) / moving, math.radians(turned) / moving / a.w, peak, math.radians(turned) / a.seconds))
            if gaps:
                print("  note: %d frames during the turn had no known marker in view (the heading was bridged through them only if a known marker returned): trust this less, add markers" % gaps)
    print("  saved", path)
    beep(1000, 300)
    beep(1000, 300)


if __name__ == "__main__":
    main()
