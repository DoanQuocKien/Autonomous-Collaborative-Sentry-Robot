"""One speed trial toward the marker board: constant (v, 0) for `seconds`, marker range recorded per frame, steady speed and start-up lag fitted afterwards.
  python speed_trial.py <v> <seconds> [label]       (run from the repo root with PYTHONPATH=. ; scratchpad/speed_runs/<label>_v<v>_<n>.csv is written)
Sequence: start check (marker 1.4-2.6 m away) -> 3 beeps -> commands zero for 3 s (hold R1 now) -> v for `seconds` -> stop -> 1.5 s of rest. Guards: the commands stop when the marker is closer than 0.8 m
or not seen for 0.4 s. The robot only moves while R1 is held; the real wheel seconds come from the robot's log."""
import csv, math, os, sys, threading, time, winsound
import cv2, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from speedfit import fit_start
from sentry.config import load
from sentry.net.udp_tx import UDPSender
from sentry.net.zmq_rx import ZMQReceiver
from sentry.perception.camera import CameraGeometry
from sentry.perception.camera_pose import detect_corners
from tools import jetbot_ssh
from tools.calibrate_motion import LOG, _sh, moving_seconds
from tools.jetbot_status import ina219_bus_volts

IP, PW = "10.35.172.160", os.environ.get("JETBOT_PASSWORD", "jetbot")
STOP_AT_M, LOST_S, WAIT_S = 0.8, 0.4, 3.0
KP, W_GAIN, MAX_BEARING = 2.5, 6.48, 25.0                         # steering: w = KP * bearing(rad) / W_GAIN toward the marker; the commands stop beyond MAX_BEARING deg
MIN_PWM, MAX_SPEED = 0.12, 0.3
SP = os.path.dirname(os.path.abspath(__file__))
v, seconds = float(sys.argv[1]), float(sys.argv[2])
label = sys.argv[3] if len(sys.argv) > 3 else "run"
cfg = load()["calibration"]; S = cfg["aruco_marker_m"] / 2
g = CameraGeometry.from_files("calib/camera.json", "calib/camera_pose_tilt_ref.json"); K = g.K
obj = np.array([[-S, S, 0], [S, S, 0], [S, -S, 0], [-S, -S, 0]], np.float64)


def marker_range(raw):
    """Floor-plane distance (m) from the camera to the marker, and the bearing (deg, left +); None without a marker."""
    f = detect_corners(raw)
    if not f:
        return None
    c = g.undistort_points(f[0][1])
    n, rv, tv, er = cv2.solvePnPGeneric(obj, c, K, None, flags=cv2.SOLVEPNP_IPPE)
    best = None
    for r, t, e in zip(rv, tv, er):
        R, _ = cv2.Rodrigues(r); t = t.reshape(3); C = -R.T @ t
        if C[2] > 0 and np.isfinite(e).all() and (best is None or float(e.ravel()[0]) < best[0]):
            best = (float(e.ravel()[0]), C)
    if best is None:
        return None
    C = best[1]
    return math.hypot(C[0], C[2]), -math.degrees(math.atan((c.mean(0)[0] - K[0, 2]) / K[0, 0]))


cmd = {"v": 0.0, "w": 0.0}; done = threading.Event()
def sender():
    s = UDPSender(IP, load()["net"]["control_port"], 30)
    try:
        while not done.is_set():
            s.send(cmd["v"], cmd["w"]); time.sleep(s.period_s)
    finally:
        s.close(stop=True)


c = jetbot_ssh.connect(IP, "jetbot", PW)
before = int(_sh(c, "wc -l < %s" % LOG).strip() or 0)
th = threading.Thread(target=sender); th.start()
rows, why, t_cmd0, t_cmd1 = [], "time", None, None
with ZMQReceiver() as rx:
    for _ in range(8):
        f = rx.read(timeout=5); r0 = marker_range(f.frame_bgr)
        if r0: break
    if r0 is None or not 1.4 <= r0[0] <= 2.6:
        done.set(); th.join(); print("ABORT: start check failed (%s)" % ("marker not seen" if r0 is None else "marker %.2f m away, need 1.4-2.6 m" % r0[0])); raise SystemExit
    print("start: marker %.2f m away, bearing %+.1f deg" % r0, flush=True)
    t0 = time.time(); [winsound.Beep(1500, 300) for _ in range(3)]
    t_go = t0 + WAIT_S + 0.9                                    # the beeps take about 0.9 s
    seen = time.time()
    while True:
        now = time.time()
        if t_cmd0 is None and now >= t_go:
            cmd["v"] = v; t_cmd0 = now
        if t_cmd0 is not None and t_cmd1 is None and (now - t_cmd0 >= seconds):
            cmd["v"] = 0.0; cmd["w"] = 0.0; t_cmd1 = now
        if t_cmd1 is not None and now - t_cmd1 > 1.5:
            break
        f = rx.read(timeout=5)
        if f is None: why = "no frames"; break
        mr = marker_range(f.frame_bgr)
        now = time.time()
        if mr is None:
            if cmd["v"] > 0 and now - seen > LOST_S: cmd["v"] = cmd["w"] = 0.0; t_cmd1 = t_cmd1 or now; why = "marker lost"
            continue
        seen = now
        if cmd["v"] > 0:
            wmax = max(0.0, min(0.2, v - MIN_PWM / MAX_SPEED - 1e-3))      # both wheels must stay above the dead zone: (v -+ w) * 0.3 >= 0.12
            cmd["w"] = max(-wmax, min(wmax, KP * math.radians(mr[1]) / W_GAIN))
        rows.append((now - t0, mr[0], mr[1], cmd["v"], cmd["w"]))
        if cmd["v"] > 0 and mr[0] < STOP_AT_M: cmd["v"] = cmd["w"] = 0.0; t_cmd1 = t_cmd1 or now; why = "marker closer than %.1f m" % STOP_AT_M
        if cmd["v"] > 0 and abs(mr[1]) > MAX_BEARING: cmd["v"] = cmd["w"] = 0.0; t_cmd1 = t_cmd1 or now; why = "marker %.0f deg off the heading (guard %.0f)" % (mr[1], MAX_BEARING)
done.set(); th.join()
time.sleep(0.6)
moving = moving_seconds(_sh(c, "tail -n +%d %s" % (before + 1, LOG)).splitlines())
volts = ina219_bus_volts(jetbot_ssh.sudo(c, "i2cget -y 1 0x41 0x02 w", PW))
os.makedirs(os.path.join(SP, "speed_runs"), exist_ok=True)
n = 1 + len([x for x in os.listdir(os.path.join(SP, "speed_runs")) if x.startswith("%s_v%g_" % (label, v))])
path = os.path.join(SP, "speed_runs", "%s_v%g_%d.csv" % (label, v, n))
csv.writer(open(path, "w", newline="")).writerows([("t", "range_m", "bearing_deg", "cmd_v", "cmd_w")] + [("%.3f" % a, "%.4f" % b, "%.2f" % c_, d, "%.4f" % e) for a, b, c_, d, e in rows])
a = np.array(rows)
t_end = (t_cmd1 - t0 + 0.5) if t_cmd1 else a[-1, 0]
fit = fit_start(a[:, 0], a[:, 1], t_stop=t_end) if len(a) > 120 else None          # the continuous fit needs dense detections; the displacement below does not
pre = a[a[:, 3] == 0][:8, 1] if (a[:, 3] == 0).any() else a[:5, 1]
ws = a[a[:, 3] > 0][:, 4]
drift_w = float(np.median(ws)) if len(ws) else 0.0                       # the steering command that held the heading = the drift at this speed (w units; x 6.48 = rad/s)
post = a[-10:, 1]
disp = float(np.median(pre) - np.median(post))
print("TRIAL v=%.2f, %.1f s commanded (marker-steered), ended by: %s | the wheels turned %.2f s | battery %.2f V | %d frames, marker %.2f -> %.2f m" % (v, seconds, why, moving, volts, len(a), a[0, 1], a[-1, 1]))
if moving > 0.5:
    print("  STEERING needed to hold the heading: median w %+.3f (= %+.1f deg/s, about %+.2f rad per metre driven), mean |w| %.3f" % (drift_w, math.degrees(drift_w * W_GAIN), drift_w * W_GAIN / max(disp / moving, 0.05), np.mean(abs(ws)) if len(ws) else 0))
    print("  NET DISPLACEMENT %.3f m (start %.2f, final %.2f, medians) in %.2f wheel seconds = AVERAGE SPEED %.3f m/s (%.3f per unit of command)" % (disp, np.median(pre), np.median(post), moving, disp / moving, disp / moving / v))
if fit and moving > 0.5:
    print("  steady speed %.3f m/s (%.3f per unit of command) | start-up lag tau %.2f s | motion starts at t = %.1f s | fit rms %.3f m" % (fit["S"], fit["S"] / v, fit["tau"], fit["t0"], fit["rms"]))
if moving <= 0.5:
    print("  no usable motion (R1 not held in time?) - repeat")
print("  saved", path)
winsound.Beep(1000, 300); winsound.Beep(1000, 300)
