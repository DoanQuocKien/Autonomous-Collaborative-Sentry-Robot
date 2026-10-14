"""Turn response check by marker bearing: stop-and-look pulses (INCONCLUSIVE on the rugged floor, 2026-10-15: R1 and timing problems; the tape protocol of tools/motion_trial.py is the reference).

Each cycle: measure the marker bearing at rest (median of 5 frames), send N pulses of w = +-W (one 30 Hz packet each) then a stop, wait, measure again. Degrees turned per packet = the effective
turn response, to compare with calib/motion.json (w_gain 6.48 rad/s at w = 1.0 -> W * 6.48 * 0.033 s per packet). The robot's own log is read after every pulse: a pulse whose wheels moved less than
half of the commanded time (R1 not held) is flagged and not counted.

  python -m tools.turn_test      (robot armed, marker board 1.4-2.6 m away and in view, floor clear, robot rotated 10-30 deg off the marker; HOLD R1 for the whole run, about 15 s)
"""
import argparse
import json
import math
import os
import statistics
import time

W, PACKET_S = 0.5, 1 / 30
MAX_PULSES, SETTLE_S, MAX_CYCLES = 10, 0.7, 12


def nominal_deg(w_gain_rad_per_s, w=W):
    """Degrees per packet if the turn rate is proportional to w."""
    return math.degrees(w_gain_rad_per_s * w * PACKET_S)


def plan_pulses(bearing_deg, nominal, w=W):
    """-> (signed w, number of packets); bearing positive = marker to the left = turn left (positive w). One packet is the resolution, so the deadband is 0.55 of it."""
    if abs(bearing_deg) < 0.55 * nominal:
        return 0.0, 0
    return math.copysign(w, bearing_deg), max(1, min(MAX_PULSES, round(abs(bearing_deg) / nominal)))


def servo(measure, pulse, settle, nominal, log=print):
    """measure() -> bearing deg; pulse(w, n) sends n packets then a stop and returns the wheel seconds (or None); settle() waits. -> [(before, n, after, deg_per_packet)]."""
    cycles, skipped = [], 0
    b = measure()
    log("start bearing %+.2f deg (deadband %.1f)" % (b, 0.55 * nominal))
    for _ in range(MAX_CYCLES):
        w, n = plan_pulses(b, nominal)
        if n == 0:
            log("inside the deadband: done at %+.2f deg" % b)
            break
        moved = pulse(w, n)
        settle()
        if moved is not None and moved < 0.5 * n * PACKET_S:
            skipped += 1
            log("  R1 not held (wheels moved %.3f s of %.3f s commanded): pulse ignored, not counted" % (moved, n * PACKET_S))
            if skipped >= 6:
                log("too many ignored pulses: hold R1 for the whole run")
                break
            continue
        a = measure()
        cycles.append((b, n, a, math.copysign(1, b) * (b - a) / n))
        log("bearing %+6.2f deg -> %d pulse(s) -> %+6.2f deg | %.2f deg/packet (nominal %.2f)%s" % (
            b, n, a, cycles[-1][3], nominal, "" if moved is None else " | wheels moved %.3f s" % moved))
        b = a
    return cycles


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ip", default="10.35.172.160")
    ap.add_argument("--user", default="jetbot")
    ap.add_argument("--password", default=os.environ.get("JETBOT_PASSWORD"))
    ap.add_argument("--motion", default="calib/motion.json")
    ap.add_argument("--camera", default="calib/camera.json")
    ap.add_argument("--pose", default="calib/camera_pose_nowedge.json", help="only K and D are used here")
    a = ap.parse_args()
    from sentry.config import load
    from sentry.net.udp_tx import UDPSender
    from sentry.net.zmq_rx import ZMQReceiver
    from sentry.perception.camera import CameraGeometry
    from sentry.perception.camera_pose import detect_corners
    from tools import jetbot_ssh
    from tools.calibrate_motion import LOG, _sh, moving_seconds
    from tools.speed_trial import beep

    nominal = nominal_deg(json.load(open(a.motion))["w_gain_rad_per_s"])
    password = jetbot_ssh.password(a.password)
    geo = CameraGeometry.from_files(a.camera, a.pose)
    K = geo.K
    ssh = jetbot_ssh.connect(a.ip, a.user, password)
    sender = UDPSender(a.ip, load()["net"]["control_port"], 30)
    rx = ZMQReceiver().__enter__()

    def bearing_once():
        f = rx.read(timeout=5)
        if f is None:
            return None
        c = [geo.undistort_points(c) for i, c in detect_corners(f.frame_bgr)]       # detect in the RAW fisheye frame, undistort only the corners
        if not c:
            return None
        return -math.degrees(math.atan((c[0].mean(0)[0] - K[0, 2]) / K[0, 0]))

    def measure():
        v, t0 = [], time.time()
        while len(v) < 5 and time.time() - t0 < 4:
            b = bearing_once()
            if b is not None:
                v.append(b)
        if len(v) < 3:
            raise SystemExit("marker lost")
        return statistics.median(v)

    def pulse(w, n):
        before = int(_sh(ssh, "wc -l < %s" % LOG).strip() or 0)
        for _ in range(n):
            sender.send(0.0, w)
            time.sleep(PACKET_S)
        sender.stop()
        time.sleep(0.3)
        return moving_seconds(_sh(ssh, "tail -n +%d %s" % (before + 1, LOG)).splitlines())

    try:
        for _ in range(3):
            beep(1500, 300)
        print("hold R1 now", flush=True)
        cy = servo(measure, pulse, lambda: time.sleep(SETTLE_S), nominal)
        if cy:
            d = [c[3] for c in cy]
            print("effective turn per packet: median %.2f deg (nominal %.2f, %+.0f%%) over %d cycles; final bearing %+.2f deg" % (
                statistics.median(d), nominal, 100 * (statistics.median(d) / nominal - 1), len(cy), cy[-1][2]))
    finally:
        sender.close(stop=True)
        rx.__exit__(None, None, None)


if __name__ == "__main__":
    main()
