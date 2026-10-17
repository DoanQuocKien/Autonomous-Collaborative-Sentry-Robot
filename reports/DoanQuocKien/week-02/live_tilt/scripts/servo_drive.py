"""Drive toward the marker, steering continuously to keep it centred; stop when the live-tilt ground distance reaches 0.5 m.
Cross-checks: bearing error over time; mean commanded turn per metre driven vs calib/motion.json drift (-0.186 rad/m => about +0.19 rad/m needed)."""
import csv, json, math, os, threading, time, winsound
import cv2, numpy as np
from sentry.config import load
from sentry.net.udp_tx import UDPSender
from sentry.net.zmq_rx import ZMQReceiver
from sentry.perception.camera import CameraGeometry
from sentry.perception.camera_pose import LiveTilt, detect_corners
V, KP, W_MAX, TARGET_M, HARD_M, TOTAL_S, LOST_S = 0.6, 0.8, 0.2, 0.50, 0.40, 45, 0.5
MOTION = json.load(open("calib/motion.json")); W_GAIN, DRIFT = MOTION["w_gain_rad_per_s"], MOTION["drift_rad_per_m"]
cfg = load()["calibration"]; S = cfg["aruco_marker_m"] / 2
BASE_Y = -(cfg["aruco_square_above_page_m"] + S) + cfg["aruco_page_bottom_h_m"]
live = CameraGeometry.from_files("calib/camera.json", "calib/camera_pose_tilt_ref.json")
fixed = CameraGeometry.from_files("calib/camera.json", "calib/camera_pose_tilt_ref.json")
lt = LiveTilt.from_config(live, cfg, every=1); K = live.K
obj = np.array([[-S, S, 0], [S, S, 0], [S, -S, 0], [-S, -S, 0]], np.float64)

def truth_and_pixel(raw):
    f = [live.undistort_points(c) for i, c in detect_corners(raw)]                  # detect in the RAW fisheye frame, undistort only the corners
    if not f: return None
    n, rv, tv, er = cv2.solvePnPGeneric(obj, f[0].astype(np.float64), K, None, flags=cv2.SOLVEPNP_IPPE)
    best = None
    for r, t, e in zip(rv, tv, er):
        R, _ = cv2.Rodrigues(r); t = t.reshape(3); C = -R.T @ t
        if C[2] > 0 and np.isfinite(e).all() and (best is None or float(e.ravel()[0]) < best[0]): best = (float(e.ravel()[0]), R, t, C)
    if best is None: return None
    _, R, t, C = best
    fwd = R.T @ np.array([0, 0, 1.0]); fh = np.array([fwd[0], 0, fwd[2]]); fh /= np.linalg.norm(fh)
    d = np.array([-C[0], 0, -C[2]]); left = np.cross([0, 1, 0], fh)
    pc = R @ np.array([0, BASE_Y, 0.0]) + t
    ctr = f[0].mean(0)
    return dict(fwd=float(d @ fh), left=float(d @ left), perp=float(C[2]), u=float(K[0, 0] * pc[0] / pc[2] + K[0, 2]), v=float(K[1, 1] * pc[1] / pc[2] + K[1, 2]),
                bearing=-math.degrees(math.atan((ctr[0] - K[0, 2]) / K[0, 0])))        # positive = marker to the left

cmd = {"v": 0.0, "w": 0.0}; done = threading.Event()
def sender():
    s = UDPSender("10.35.172.160", load()["net"]["control_port"], 30)
    try:
        while not done.is_set():
            s.send(cmd["v"], cmd["w"]); time.sleep(s.period_s)
    finally:
        s.close(stop=True)
th = threading.Thread(target=sender); th.start()
def belief(g, tr):
    p = g.ground_point(tr["u"], tr["v"]); return p.forward_m if p else float("nan")
rec, rows, why, t0, seen, last = [], [], "time", time.time(), time.time(), 0
omega_int = 0.0                                               # integral of the commanded turn rate (rad), left positive
with ZMQReceiver() as rx:
    for _ in range(6):
        f = rx.read(timeout=5); tr0 = truth_and_pixel(f.frame_bgr)
        if tr0: break
    if tr0 is None or tr0["fwd"] < 1.0 or abs(tr0["bearing"]) > 55:
        done.set(); th.join(); print("ABORT: start check failed (%s)" % ("marker not seen" if tr0 is None else "at %.2f m, bearing %+.0f deg" % (tr0["fwd"], tr0["bearing"]))); raise SystemExit
    print("start: marker %.2f m ahead, bearing %+.1f deg, lateral %+.2f m" % (tr0["fwd"], tr0["bearing"], tr0["left"]))
    [winsound.Beep(1500, 300) for _ in range(3)]; print("window open: hold R1 now", flush=True)
    cmd["v"] = V; tprev = time.time(); moved = False; lastbeep = time.time()
    while time.time() - t0 < TOTAL_S:
        f = rx.read(timeout=5)
        if f is None: why = "no frames"; break
        now = time.time()
        if not moved and rows and (abs(rows[-1][3] - rows[0][3]) > 0.05 or abs(rows[-1][1] - rows[0][1]) > 1.0): moved = True
        if not moved:
            if now - lastbeep > 4: lastbeep = now; winsound.Beep(1500, 200); winsound.Beep(1500, 200); winsound.Beep(1500, 200)
            if now - t0 > 25: why = "no motion for 25 s: R1 not held while the commands ran"; break
        rec.append((now - t0, cmd["v"] > 0, f.jpeg if isinstance(f.jpeg, (bytes, bytearray)) else cv2.imencode(".jpg", f.frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 95])[1].tobytes()))
        lt.raw(f.frame_bgr); tr = truth_and_pixel(f.frame_bgr)
        if tr is None:
            if now - seen > LOST_S: why = "marker lost %.1f s" % LOST_S; break
            continue
        if rows and abs(tr["fwd"] - rows[-1][3]) > 0.3: continue
        seen = now
        w = max(-W_MAX, min(W_MAX, KP * math.radians(tr["bearing"]) / W_GAIN)); cmd["w"] = w
        omega_int += w * W_GAIN * (now - tprev); tprev = now
        row = (now - t0, tr["bearing"], w, tr["fwd"], belief(fixed, tr), belief(live, tr), math.degrees(live.pitch), tr["left"], tr["perp"], omega_int); rows.append(row)
        if now - last >= 0.5: last = now; print("t=%4.1f  bearing %+5.1f deg  w %+.3f  true %.3f  fixed %.3f  live %.3f  pitch %.2f  left %+.3f" % row[:8], flush=True)
        if len(rows) >= 3 and np.nanmedian([r[5] for r in rows[-3:]]) <= TARGET_M: why = "live belief reached %.2f m" % TARGET_M; break
        if tr["fwd"] < HARD_M: why = "hard floor %.2f m" % HARD_M; break
    cmd["v"] = cmd["w"] = 0.0; time.sleep(2.0)
    rest = []; t1 = time.time()
    while time.time() - t1 < 2.5:
        f = rx.read(timeout=5)
        if f is None: break
        rec.append((time.time() - t0, False, f.jpeg if isinstance(f.jpeg, (bytes, bytearray)) else cv2.imencode(".jpg", f.frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 95])[1].tobytes()))
        lt.raw(f.frame_bgr); tr = truth_and_pixel(f.frame_bgr)
        if tr: rest.append((tr["fwd"], belief(fixed, tr), belief(live, tr), tr["perp"], tr["left"], tr["bearing"]))
done.set(); th.join()
os.makedirs("../run_servo", exist_ok=True)
for i, (tt, g_, jb) in enumerate(rec): open("../run_servo/f%04d.jpg" % i, "wb").write(jb)
csv.writer(open("../run_servo/meta.csv", "w", newline="")).writerows([("i", "t", "go")] + [(i, "%.3f" % tt, int(g_)) for i, (tt, g_, _) in enumerate(rec)])
csv.writer(open("../servo_rows.csv", "w", newline="")).writerows([("t", "bearing", "w", "true_fwd", "fixed", "live", "pitch", "left", "perp", "omega_int")] + rows)
print("STOPPED:", why)
if rows:
    a = np.array(rows); steady = a[a[:, 0] > a[0, 0] + 2.0] if (a[:, 0] > a[0, 0] + 2.0).sum() > 10 else a
    dist = a[0, 3] - a[-1, 3]
    print("BEARING after the first 2 s: RMS %.2f deg, max %.2f deg (%d frames); start %+.1f deg" % (math.sqrt(np.mean(steady[:, 1] ** 2)), np.max(abs(steady[:, 1])), len(steady), a[0, 1]))
    print("TURN COMMANDED: %+.3f rad total over %.2f m driven = %+.3f rad/m (motion.json drift %.3f rad/m at v=1.0 means about %+.3f needed); mean |w| %.3f" % (a[-1, 9], dist, a[-1, 9] / dist if dist > 0.2 else float("nan"), DRIFT, -DRIFT, np.mean(abs(a[:, 2]))))
    e_f = a[:, 4] - a[:, 3]; e_l = a[:, 5] - a[:, 3]
    print("GROUND DISTANCE (%d frames): median |err| fixed %.3f m, live %.3f m" % (len(a), np.nanmedian(abs(e_f)), np.nanmedian(abs(e_l))))
if rest:
    r = np.median(np.array(rest), axis=0)
    print("AT REST: true forward %.3f m, PERPENDICULAR to the wall %.3f m | fixed belief %.3f (%+.3f) | live belief %.3f (%+.3f) | lateral %+.3f m | marker bearing %+.1f deg" % (r[0], r[3], r[1], r[1] - r[0], r[2], r[2] - r[0], r[4], r[5]))
