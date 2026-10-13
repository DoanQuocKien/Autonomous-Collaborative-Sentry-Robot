"""Live camera tilt, roll and height from an ArUco marker on a vertical wall (Week 2 extra, DQK).

World frame = marker frame: x right, y UP (the wall is vertical, so the marker's y axis is the world vertical), z out of the wall toward the room.
Convention (same as tools/measure_camera_pose.py): pitch is positive when the camera looks DOWN.
Feed it UNDISTORTED frames (the fisheye model is removed first) and the pinhole K of `calib/camera.json`.

  tilt = TiltFilter()
  for frame in frames:
      est = tilt.update_frame(und, K, MARKER_M, MARKER_BOTTOM_H_M)    # None without a marker; tilt.pitch_deg keeps the last value
"""
import math
from collections import deque

import cv2
import numpy as np

DICT = cv2.aruco.DICT_4X4_50
ROLL_SIGN = -1


def pitch_from_position(t_cam, marker_center_h_m, camera_h_m):
    """Tilt from WHERE the marker is, not how it is oriented (the orientation of a small planar marker is poorly conditioned beyond ~1.5 m).
    t_cam: marker centre in camera coordinates (x right, y down, z forward). The range r is accurate (size + centre), and the marker's elevation above the
    horizontal follows from the known heights: sin(e) = (h_marker - H) / r. With the horizontal bearing beta of the marker off the optical axis,
    its camera-frame y component is dy = -sin(e) cos(p) - cos(e) cos(beta) sin(p); solve for the pitch p (positive = looking down)."""
    x, y, z = (float(v) for v in t_cam)
    r = math.sqrt(x * x + y * y + z * z)
    e = math.asin(max(-1.0, min(1.0, (marker_center_h_m - camera_h_m) / r)))
    beta = math.atan2(x, z)
    a, b = math.cos(e) * math.cos(beta), math.sin(e)
    return math.degrees(math.asin(max(-1.0, min(1.0, -(y / r) / math.hypot(a, b)))) - math.atan2(b, a))


def pose_from_corners(corners_px, K, marker_m, marker_bottom_h_m, camera_h_m=None, roll_deg=None):
    """corners_px: 4x2 pixel corners in ArUco order (top-left, top-right, bottom-right, bottom-left) of an undistorted image.
    -> dict(pitch_deg, roll_deg, height_m, distance_m, reproj_px, pitch_ori_deg) or None. `pitch_deg` comes from the marker's POSITION when the camera height
    `camera_h_m` is given (accurate to a fraction of a degree up to ~2.5 m), else from its orientation (`pitch_ori_deg`, noisy: 3-10 deg at 1.5-2 m).
    `roll_deg` overrides the roll that is undone before the position is used: the marker's own roll is poor off-axis (0.5 deg of tilt per deg of roll at 28 deg bearing)."""
    s = marker_m / 2.0
    obj = np.array([[-s, s, 0], [s, s, 0], [s, -s, 0], [-s, -s, 0]], np.float64)
    img = np.asarray(corners_px, np.float64).reshape(4, 2)
    n, rvecs, tvecs, errs = cv2.solvePnPGeneric(obj, img, np.asarray(K, np.float64), None, flags=cv2.SOLVEPNP_IPPE)
    cands = [(float(np.asarray(e).ravel()[0]), rv, tv) for rv, tv, e in zip(rvecs, tvecs, errs)] if n else []
    cands = [c for c in cands if np.isfinite(c[0]) and np.all(np.isfinite(c[2]))]
    if not cands:                  # OpenCV 5.0's IPPE returns NaN for some exact (noise-free) views: fall back to the iterative solver
        ok, rv, tv = cv2.solvePnP(obj, img, np.asarray(K, np.float64), None, flags=cv2.SOLVEPNP_ITERATIVE)
        cands = [(0.0, rv, tv)] if ok else []
    best = None
    for e, rv, tv in cands:
        R, _ = cv2.Rodrigues(rv)
        if (-R.T @ tv.reshape(3))[2] <= 0:   # the camera must be in front of the wall (+z of the marker): the other IPPE solution is behind it
            continue
        if best is None or e < best[0]:
            best = (e, R, tv.reshape(3))
    if best is None:
        return None
    err, R, t = best
    C = -R.T @ t                                           # camera position in marker coordinates
    pitch_ori = math.degrees(math.asin(max(-1.0, min(1.0, -R[2][1]))))               # axis y = -sin(pitch down)
    roll = math.degrees(math.asin(max(-1.0, min(1.0, R[0][1]))))                     # camera right vector's vertical part
    if camera_h_m is None:
        pitch = pitch_ori
    else:                                                                            # undo the camera roll (measured from the orientation) before using the position
        r_use = roll if roll_deg is None else roll_deg
        c, sn = math.cos(math.radians(ROLL_SIGN * r_use)), math.sin(math.radians(ROLL_SIGN * r_use))
        pitch = pitch_from_position((t[0] * c - t[1] * sn, t[0] * sn + t[1] * c, t[2]), marker_bottom_h_m + s, camera_h_m)
    return {"pitch_deg": pitch, "pitch_ori_deg": pitch_ori,
            "roll_deg": roll, "bearing_rad": math.atan2(float(t[0]), float(t[2])),
            "height_m": marker_bottom_h_m + s + float(C[1]),
            "distance_m": float(C[2]),
            "reproj_px": err}


def detect_corners(gray_or_bgr):
    """-> list of (marker_id, 4x2 corners) found in the image."""
    prm = cv2.aruco.DetectorParameters()
    prm.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX          # default is whole pixels: 1 px = 0.19 deg of tilt
    det = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(DICT), prm)
    corners, ids, _ = det.detectMarkers(gray_or_bgr)
    return [] if ids is None else [(int(i), c.reshape(4, 2)) for i, c in zip(ids.ravel(), corners)]


class TiltFilter:
    """Median of the last `n` marker estimates; a jump of more than `max_jump_deg` from the current median is rejected as an outlier
    (after `min_samples` accepted ones). Without a marker the last value is kept: `pitch_deg` starts at `default_pitch_deg` (the session's calib value)."""

    def __init__(self, default_pitch_deg=0.0, n=15, max_jump_deg=5.0, min_samples=5, max_reproj_px=2.0, max_distance_m=2.5, centred_rad=0.10):
        self.pitch_deg, self.roll_deg, self.height_m = default_pitch_deg, 0.0, None
        self.hist, self.max_jump, self.min_samples = deque(maxlen=n), max_jump_deg, min_samples
        self.max_reproj, self.max_distance, self.centred = max_reproj_px, max_distance_m, centred_rad
        self.roll_hist = deque(maxlen=n)          # roll only from markers near the optical axis
        self.rejected = 0

    def update(self, est):
        """est: dict from pose_from_corners or None. -> True when the estimate was accepted."""
        if est is None or est["reproj_px"] > self.max_reproj or est["distance_m"] > self.max_distance:
            return False
        if len(self.hist) >= self.min_samples and abs(est["pitch_deg"] - float(np.median([h["pitch_deg"] for h in self.hist]))) > self.max_jump:
            self.rejected += 1
            return False
        self.hist.append(est)
        self.pitch_deg = float(np.median([h["pitch_deg"] for h in self.hist]))
        if abs(est["bearing_rad"]) < self.centred:
            self.roll_hist.append(est["roll_deg"])
            self.roll_deg = float(np.median(self.roll_hist))
        self.height_m = float(np.median([h["height_m"] for h in self.hist]))
        return True

    def update_frame(self, undistorted_bgr, K, marker_m, marker_bottom_h_m, marker_id=None, camera_h_m=None):
        found = [c for i, c in detect_corners(undistorted_bgr) if marker_id is None or i == marker_id]
        return self.update_corners(found[0], K, marker_m, marker_bottom_h_m, camera_h_m) if found else None

    def update_corners(self, corners_px, K, marker_m, marker_bottom_h_m, camera_h_m=None):
        est = pose_from_corners(corners_px, K, marker_m, marker_bottom_h_m, camera_h_m)
        if est and camera_h_m is not None and self.roll_hist and abs(est["bearing_rad"]) >= self.centred:
            est = pose_from_corners(corners_px, K, marker_m, marker_bottom_h_m, camera_h_m, roll_deg=self.roll_deg)   # off-axis: trust the camera's roll, not the marker's
        self.update(est)
        return est


class LiveTilt:
    """Keeps a CameraGeometry's pitch current from the ArUco pages in view (the floor tilts the chassis by up to ~1.7 deg between spots, measured 2026-10-14).
    Call it with each UNDISTORTED frame (ObstacleDetector does, after geometry.undistort); every `every`-th frame is searched for a marker, an accepted estimate
    sets geometry.pitch. Without a marker the last pitch stays. All pages share one layout, so one lower-edge height serves every id (config.toml [calibration])."""

    def __init__(self, geometry, marker_m, square_bottom_h_m, every=3, n=3, **filter_kw):          # n=3 (median of 3 frames): 15 lagged ~1 s behind a robot at 0.3 m/s. Replays of two recorded runs, 2026-10-14: moving error window15 / 5 / 3 = 0.061 / 0.036 / 0.037 m (v=0.7), 0.310 / 0.194 / 0.126 m (v=0.4)
        self.geometry, self.marker_m, self.bottom_h, self.every, self.n = geometry, marker_m, square_bottom_h_m, max(1, every), 0
        self.filter = TiltFilter(default_pitch_deg=math.degrees(geometry.pitch), n=n, min_samples=min(5, n), **filter_kw)

    @classmethod
    def from_config(cls, geometry, calibration, **kw):
        return cls(geometry, calibration["aruco_marker_m"], calibration["aruco_page_bottom_h_m"] + calibration["aruco_square_above_page_m"], **kw)

    def __call__(self, undistorted_bgr):
        """-> the accepted estimate dict, or None."""
        return self._step(lambda: self.filter.update_frame(undistorted_bgr, self.geometry.K, self.marker_m, self.bottom_h, None, self.geometry.height_m))

    def raw(self, frame_bgr):
        """Same, from the RAW fisheye frame: the marker is detected there and only its 4 corners are undistorted. Finds markers far off-axis that the remapped image loses."""
        def go():
            found = detect_corners(frame_bgr)
            return self.filter.update_corners(self.geometry.undistort_points(found[0][1]), self.geometry.K, self.marker_m, self.bottom_h, self.geometry.height_m) if found else None
        return self._step(go)

    def _step(self, estimate):
        self.n += 1
        if (self.n - 1) % self.every:
            return None
        est = estimate()
        if est is None or not self.filter.hist or self.filter.hist[-1] is not est:
            return None
        self.geometry.set_pitch_deg(self.filter.pitch_deg)
        return est
