import math, threading, time, winsound
import cv2, numpy as np
from sentry.config import load
from sentry.net.udp_tx import UDPSender
from sentry.net.zmq_rx import ZMQReceiver
from sentry.perception.camera import CameraGeometry
from sentry.perception.camera_pose import LiveTilt, detect_corners
V, TARGET_M, HARD_M, TOTAL_S, LOST_S = 0.4, 0.50, 0.55, 45, 0.3     # v 0.4 = the slowest usable command (motor 0.12); stop commands after 0.3 s without a detection
cfg = load()["calibration"]; M = cfg["aruco_marker_m"]; S = M / 2
BASE_Y = -(cfg["aruco_square_above_page_m"] + cfg["aruco_page_bottom_h_m"] + S - cfg["aruco_page_bottom_h_m"]) # wall/floor line, marker frame (y up, origin = marker centre)
BASE_Y = -(cfg["aruco_page_bottom_h_m"] * 0 + cfg["aruco_square_above_page_m"] + S) + cfg["aruco_page_bottom_h_m"]
live = CameraGeometry.from_files("calib/camera.json", "calib/camera_pose_tilt_ref.json")
fixed = CameraGeometry.from_files("calib/camera.json", "calib/camera_pose_tilt_ref.json")        # never updated: the strips tilt, 5.03 deg
lt = LiveTilt.from_config(live, cfg, every=1)
K = live.K
obj = np.array([[-S, S, 0], [S, S, 0], [S, -S, 0], [-S, -S, 0]], np.float64)

def truth_and_pixel(img):
    f = [c for i, c in detect_corners(img)]
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
    u, v = K[0, 0] * pc[0] / pc[2] + K[0, 2], K[1, 1] * pc[1] / pc[2] + K[1, 2]
    return dict(fwd=float(d @ fh), left=float(d @ left), perp=float(C[2]), u=float(u), v=float(v))

go = threading.Event(); done = threading.Event()
def sender():
    s = UDPSender("10.35.172.160", load()["net"]["control_port"], 30)
    try:
        while not done.is_set():
            s.send(V if go.is_set() else 0.0, 0.0); time.sleep(s.period_s)
    finally:
        s.close(stop=True)
th = threading.Thread(target=sender); th.start()
rec = []
rows, why, t0, last, seen = [], "time", time.time(), 0, time.time()
def belief(g, tr):
    p = g.ground_point(tr["u"], tr["v"]); return p.forward_m if p else float("nan")
with ZMQReceiver() as rx:
    for _ in range(3): rx.read(timeout=5)
    for _ in range(6):                                           # start check: the robot must be about 2 m from the wall, else do not move
        f = rx.read(timeout=5); tr0 = truth_and_pixel(live.undistort(f.frame_bgr))
        if tr0: break
    if tr0 is None or tr0["fwd"] < 1.5:
        done.set(); th.join(); print("ABORT: start check failed (marker %s)" % ("not seen" if tr0 is None else "at %.2f m, not about 2 m" % tr0["fwd"])); raise SystemExit
    go.set(); [winsound.Beep(1500, 300) for _ in range(3)]
    print("window open: hold R1 now. cols: t | true fwd (PnP) | fixed 5.03 deg belief | live belief | live pitch | lateral", flush=True)
    while time.time() - t0 < TOTAL_S:
        f = rx.read(timeout=5)
        if f is None: why = "no frames"; break
        rec.append((time.time() - t0, bool(go.is_set()), f.jpeg if isinstance(f.jpeg, (bytes, bytearray)) else cv2.imencode('.jpg', f.frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 95])[1].tobytes()))
        img = live.undistort(f.frame_bgr); lt(img)
        tr = truth_and_pixel(img)
        if tr is None:
            if time.time() - seen > LOST_S: go.clear(); why = "marker lost %.1f s" % LOST_S; break
            continue
        if rows and abs(tr["fwd"] - rows[-1][1]) > 0.3: continue                 # one-frame glitch (PnP flip / blur): ignore it
        seen = time.time()
        row = (time.time() - t0, tr["fwd"], belief(fixed, tr), belief(live, tr), math.degrees(live.pitch), tr["left"], tr["perp"]); rows.append(row)
        if time.time() - last >= 0.5:
            last = time.time(); print("t=%4.1f  true %.3f  fixed %.3f  live %.3f  pitch %.2f  left %+.3f" % row[:6], flush=True)
        if len(rows) >= 3 and np.nanmedian([r[3] for r in rows[-3:]]) <= TARGET_M: why = "live belief reached %.2f m" % TARGET_M; break
        if row[1] < HARD_M: go.clear(); why = "hard floor %.2f m" % HARD_M; break
    go.clear(); time.sleep(2.0)                                  # let it stop and settle, then 2 s of rest readings
    rest = []
    t1 = time.time()
    while time.time() - t1 < 2.5:
        f = rx.read(timeout=5)
        if f is None: break
        rec.append((time.time() - t0, False, f.jpeg if isinstance(f.jpeg, (bytes, bytearray)) else cv2.imencode('.jpg', f.frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 95])[1].tobytes()))
        img = live.undistort(f.frame_bgr); lt(img); tr = truth_and_pixel(img)
        if tr: rest.append((tr["fwd"], belief(fixed, tr), belief(live, tr), math.degrees(live.pitch), tr["left"], tr["perp"]))
done.set(); th.join()
import csv, os; os.makedirs("../run_rec", exist_ok=True)
for i, (tt, g_, jb) in enumerate(rec): open("../run_rec/f%04d.jpg" % i, "wb").write(jb)
csv.writer(open("../run_rec/meta.csv", "w", newline="")).writerows([("i", "t", "go")] + [(i, "%.3f" % tt, int(g_)) for i, (tt, g_, _) in enumerate(rec)])
csv.writer(open("../rt_test_rows.csv", "w", newline="")).writerows([("t", "true_fwd", "fixed_belief", "live_belief", "live_pitch", "left", "perp")] + rows)
print("STOPPED:", why)
if rest:
    a = np.median(np.array(rest), axis=0)
    print("AT REST (median of %d frames): true %.3f m | fixed-tilt belief %.3f m (error %+.3f) | live belief %.3f m (error %+.3f) | live pitch %.2f deg | lateral %+.3f m | PERPENDICULAR to the wall %.3f m" % (len(rest), a[0], a[1], a[1]-a[0], a[2], a[2]-a[0], a[3], a[4], a[5]))
if rows:
    arr = np.array(rows); e_f = arr[:, 2] - arr[:, 1]; e_l = arr[:, 3] - arr[:, 1]
    print("DURING THE RUN (%d frames): mean |error| fixed %.3f m, live %.3f m; worst fixed %.3f, live %.3f" % (len(arr), np.nanmean(abs(e_f)), np.nanmean(abs(e_l)), np.nanmax(abs(e_f)), np.nanmax(abs(e_l))))
