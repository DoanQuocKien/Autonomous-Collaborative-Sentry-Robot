"""Angle-calibration check: stop-and-look visual servo on the marker's bearing.
Each cycle: measure the marker bearing at rest (median of 5 frames), send N pulses of w=+-W (one 30 Hz packet each) then a stop, wait, measure again.
Log degrees turned per packet = the effective turn gain, to compare with calib/motion.json (w_gain 6.48 rad/s at w=1.0 -> W*6.48*0.033 s per packet).
Run:  python turn_test.py   (robot armed, hold R1 for the whole run; start with the robot rotated 10-30 deg off the marker)"""
import json, math, sys, time, statistics
W, PACKET_S, NOM_DEG = 0.5, 1 / 30, None
MOTION = json.load(open("calib/motion.json"))
NOM_DEG = math.degrees(MOTION["w_gain_rad_per_s"] * W * PACKET_S)             # nominal turn per packet if the gain is linear in w
MAX_PULSES, SETTLE_S, MAX_CYCLES = 10, 0.7, 12
DEADBAND_DEG = 0.55 * NOM_DEG                                                  # one packet is the resolution; a smaller deadband makes it hunt

def plan_pulses(bearing_deg, nominal_deg=None):
    """-> (signed w, number of packets); bearing positive = marker to the left = turn left (positive w)."""
    nominal_deg = NOM_DEG if nominal_deg is None else nominal_deg
    if abs(bearing_deg) < DEADBAND_DEG: return 0.0, 0
    return math.copysign(W, bearing_deg), max(1, min(MAX_PULSES, round(abs(bearing_deg) / nominal_deg)))

def servo(measure, pulse, settle, log=print):
    """measure() -> bearing deg; pulse(w, n) sends n packets then a stop; settle() waits. Returns the cycles [(before, n, after, deg_per_packet)]."""
    cycles, skipped = [], 0
    b = measure(); log("start bearing %+.2f deg (deadband %.1f)" % (b, DEADBAND_DEG))
    for _ in range(MAX_CYCLES):
        w, n = plan_pulses(b)
        if n == 0: log("inside the deadband: done at %+.2f deg" % b); break
        moved = pulse(w, n); settle()
        if moved is not None and moved < 0.5 * n * PACKET_S:                 # the robot's own log says the wheels hardly moved: R1 was not held, this pulse says nothing about the floor
            skipped += 1; log("  R1 not held (wheels moved %.3f s of %.3f s commanded): pulse ignored, not counted" % (moved, n * PACKET_S))
            if skipped >= 6: log("too many ignored pulses: hold R1 for the whole run"); break
            continue
        a = measure()
        turned = (b - a)                                                   # positive = the marker moved toward the centre
        cycles.append((b, n, a, math.copysign(1, b) * turned / n)); log("bearing %+6.2f deg -> %d pulse(s) -> %+6.2f deg | %.2f deg/packet (nominal %.2f)%s" % (b, n, a, cycles[-1][3], NOM_DEG, "" if moved is None else " | wheels moved %.3f s" % moved))
        b = a
    return cycles

if __name__ == "__main__":
    import threading
    from sentry.config import load
    from sentry.net.udp_tx import UDPSender
    from sentry.net.zmq_rx import ZMQReceiver
    sys.path.insert(0, ".")
    import cv2, numpy as np
    from sentry.perception.camera import CameraGeometry
    from sentry.perception.camera_pose import detect_corners
    cfg = load()["calibration"]; S = cfg["aruco_marker_m"] / 2
    geo = CameraGeometry.from_files("calib/camera.json", "calib/camera_pose_tilt_ref.json"); K = geo.K
    obj = np.array([[-S, S, 0], [S, S, 0], [S, -S, 0], [-S, -S, 0]], np.float64)
    sender = UDPSender("10.35.172.160", load()["net"]["control_port"], 30)
    rx = ZMQReceiver().__enter__()
    def bearing_once():
        f = rx.read(timeout=5)
        if f is None: return None
        c = [geo.undistort_points(c) for i, c in detect_corners(f.frame_bgr)]      # detect in the RAW fisheye frame, undistort only the corners
        if not c: return None
        ctr = c[0].mean(0)
        return -math.degrees(math.atan((ctr[0] - K[0, 2]) / K[0, 0]))      # positive = left; marker centre column through the pinhole model
    def measure():
        v = []
        t0 = time.time()
        while len(v) < 5 and time.time() - t0 < 4:
            b = bearing_once()
            if b is not None: v.append(b)
        if len(v) < 3: raise SystemExit("marker lost")
        return statistics.median(v)
    from tools import jetbot_ssh
    from tools.calibrate_motion import LOG, _sh, moving_seconds
    ssh = jetbot_ssh.connect("10.35.172.160", "jetbot", __import__("os").environ.get("JETBOT_PASSWORD", "jetbot"))
    def pulse(w, n):
        before = int(_sh(ssh, "wc -l < %s" % LOG).strip() or 0)
        for _ in range(n):
            sender.send(0.0, w); time.sleep(PACKET_S)
        sender.stop()
        time.sleep(0.3)
        return moving_seconds(_sh(ssh, "tail -n +%d %s" % (before + 1, LOG)).splitlines())
    try:
        [__import__("winsound").Beep(1500, 300) for _ in range(3)]; print("hold R1 now", flush=True)
        cy = servo(measure, pulse, lambda: time.sleep(SETTLE_S))
        if cy:
            d = [c[3] for c in cy]; print("effective turn per packet: median %.2f deg (nominal %.2f, %+.0f%%) over %d cycles; final bearing %+.2f deg" % (statistics.median(d), NOM_DEG, 100 * (statistics.median(d) / NOM_DEG - 1), len(cy), cy[-1][2]))
    finally:
        sender.close(stop=True); rx.__exit__(None, None, None)
