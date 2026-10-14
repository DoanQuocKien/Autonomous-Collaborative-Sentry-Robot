"""Which camera roll (sign and value) makes the ground distance of the wall base match the marker-pose truth, across bearings 0-30 deg?"""
import glob, math, os
import cv2, numpy as np
from sentry.perception.camera import CameraGeometry
from sentry.perception.camera_pose import detect_corners, pose_from_corners

SP = os.path.dirname(os.path.abspath(__file__))
g = CameraGeometry.from_files("calib/camera.json", "calib/camera_pose_tilt_ref.json")
K = g.K; S = 0.15; BOT = 0.132; BASE_Y = -(BOT + S / 2)
obj = np.array([[-S / 2, S / 2, 0], [S / 2, S / 2, 0], [S / 2, -S / 2, 0], [-S / 2, -S / 2, 0]], np.float64)
frames = []
for d, step in (("run_servo_2", 20), ("run_servo", 3), ("run_servo_1", 6), ("run_servo_3", 1)):
    files = sorted(glob.glob(os.path.join(SP, d, "f*.jpg")))[::step]
    for f in files:
        found = detect_corners(cv2.imread(f))
        if not found:
            continue
        c = g.undistort_points(found[0][1])
        n, rv, tv, er = cv2.solvePnPGeneric(obj, c, K, None, flags=cv2.SOLVEPNP_IPPE)
        best = None
        for r, t, e in zip(rv, tv, er):
            R, _ = cv2.Rodrigues(r); t = t.reshape(3); C = -R.T @ t
            if C[2] > 0 and np.isfinite(e).all() and (best is None or float(e.ravel()[0]) < best[0]): best = (float(e.ravel()[0]), R, t, C)
        if best is None: continue
        _, R, t, C = best
        fw = R.T @ np.array([0, 0, 1.0]); fh = np.array([fw[0], 0, fw[2]]); fh /= np.linalg.norm(fh)
        fwd_true = float(np.array([-C[0], 0, -C[2]]) @ fh)
        pc = R @ np.array([0, BASE_Y, 0.0]) + t
        u, v = K[0, 0] * pc[0] / pc[2] + K[0, 2], K[1, 1] * pc[1] / pc[2] + K[1, 2]
        ctr = c.mean(0); b = -math.degrees(math.atan((ctr[0] - K[0, 2]) / K[0, 0]))
        frames.append((c, fwd_true, u, v, b))
print("frames", len(frames), "bearings %.0f..%.0f deg, true forward %.2f..%.2f m" % (min(f[4] for f in frames), max(f[4] for f in frames), min(f[1] for f in frames), max(f[1] for f in frames)))
bins = ((-3, 8), (8, 20), (20, 40))
print("rows: roll used for the marker pitch (r_m) / roll used by ground_point (r_g); columns: median |relative error| in bearing bins", bins)
for rm in (-1.1, 0.0, 1.1):
    for rg in (-1.1, 0.0, 1.1):
        cells = []
        for lo, hi in bins:
            errs = []
            for c, fwd, u, v, b in frames:
                if not lo <= abs(b) < hi and not (lo == -3 and abs(b) < hi):
                    continue
                e = pose_from_corners(c, K, S, BOT, g.height_m, roll_deg=rm)
                if e is None: continue
                g.set_pitch_deg(e["pitch_deg"]); g.roll = math.radians(rg)
                p = g.ground_point(u, v)
                errs.append(abs(p.forward_m - fwd) / fwd if p else 1.0)
            cells.append("%5.1f%% (n=%d)" % (100 * np.median(errs), len(errs)) if errs else "  n/a")
        print("r_m %+.1f  r_g %+.1f : %s" % (rm, rg, "   ".join(cells)))
