"""Fisheye -> same-K rectified pixels -> ground (forward, left), in metres.

Same K as tools.measure_camera_pose: using a newly optimized K would invalidate
the measured pitch. Ground origin is directly under the lens, not axle centre.
"""
from dataclasses import dataclass
import json
import math
from pathlib import Path

import cv2
import numpy as np


@dataclass(frozen=True)
class GroundPoint:
    forward_m: float
    left_m: float

    def __post_init__(self):
        if not all(math.isfinite(v) for v in (self.forward_m, self.left_m)) or self.forward_m <= 0:
            raise ValueError("ground point must be finite and ahead of the camera")

    @property
    def distance_m(self):
        return math.hypot(self.forward_m, self.left_m)

    @property
    def bearing_rad(self):
        return math.atan2(self.left_m, self.forward_m)  # positive = left


class CameraGeometry:
    def __init__(self, camera, pose, max_range_m=5.0, max_pose_rms_m=0.03):
        self.K = np.asarray(camera["K"], dtype=float)
        self.D = np.asarray(camera["D"], dtype=float)
        self.size = tuple(camera["image_size"])
        self.height_m = float(pose["H_cam_m"])
        self.pitch = math.radians(float(pose["pitch_down_deg"]))
        self.roll = math.radians(float(pose.get("camera_roll_deg", 0)))
        self.max_range_m = float(max_range_m)
        if not math.isfinite(max_pose_rms_m) or max_pose_rms_m <= 0:
            raise ValueError("positive finite pose RMS limit required")
        self.session = pose.get("session", pose.get("tag", "unspecified"))
        self.pose_status = "explicit_pass"
        if "passed" in pose:
            if pose["passed"] is not True:
                raise ValueError("camera pose calibration must pass")
        else:
            # DQK classroom format records measured height/fit evidence, no passed flag.
            marks, rows = pose.get("marks_m", []), pose.get("rows_px", [])
            rms = pose.get("rms_m", math.inf)
            if (not pose.get("session") or pose.get("H_fixed_by_tape") is not True
                    or len(marks) < 3 or len(marks) != len(rows)
                    or not all(math.isfinite(v) for v in (*marks, *rows, rms, max_pose_rms_m))
                    or not 0 <= rms <= max_pose_rms_m or max_pose_rms_m <= 0
                    or any(v <= 0 for v in marks)):
                raise ValueError("session camera pose needs tape height and finite fit evidence")
            self.pose_status = "measured_session_without_pass_flag"
        if (self.K.shape != (3, 3) or self.D.size != 4 or not np.isfinite(self.K).all()
                or not np.isfinite(self.D).all() or self.K[0, 0] <= 0 or self.K[1, 1] <= 0
                or not np.allclose(self.K[2], [0, 0, 1])
                or self.K[0, 1] != 0 or self.K[1, 0] != 0):
            raise ValueError("invalid fisheye intrinsics (zero skew required)")
        if len(self.size) != 2 or any(type(n) is not int or n <= 0 for n in self.size):
            raise ValueError("invalid calibrated image size")
        if (not all(math.isfinite(v) for v in (self.height_m, self.pitch, self.roll, self.max_range_m))
                or self.height_m <= 0 or self.max_range_m <= 0 or abs(self.pitch) >= math.pi / 2):
            raise ValueError("invalid camera geometry")
        self.map_x, self.map_y = cv2.fisheye.initUndistortRectifyMap(
            self.K, self.D, np.eye(3), self.K, self.size, cv2.CV_32FC1)
        w, h = self.size
        self.valid = ((self.map_x >= 0) & (self.map_x < w - 1)
                      & (self.map_y >= 0) & (self.map_y < h - 1))

    @classmethod
    def from_files(cls, camera_path, pose_path, max_range_m=5.0, max_pose_rms_m=0.03):
        return cls(json.loads(Path(camera_path).read_text(encoding="utf-8-sig")),
                   json.loads(Path(pose_path).read_text(encoding="utf-8-sig")), max_range_m, max_pose_rms_m)

    def set_pitch_deg(self, deg):
        """Live tilt update (sentry.perception.camera_pose.TiltFilter.pitch_deg); the floor moves it by up to ~1.7 deg between spots."""
        if not math.isfinite(deg) or abs(deg) >= 90:
            raise ValueError("invalid pitch")
        self.pitch = math.radians(deg)

    def undistort_points(self, pts):
        """Raw fisheye pixels -> the same-K rectified pixels (what undistort() would give), without remapping the image."""
        p = np.asarray(pts, dtype=np.float64).reshape(-1, 1, 2)
        return cv2.fisheye.undistortPoints(p, self.K, self.D, P=self.K).reshape(-1, 2)

    def undistort(self, frame_bgr):
        w, h = self.size
        if (not isinstance(frame_bgr, np.ndarray) or frame_bgr.shape != (h, w, 3)
                or frame_bgr.dtype != np.uint8):
            raise ValueError("expected uint8 BGR at the calibrated resolution")
        return cv2.remap(frame_bgr, self.map_x, self.map_y, cv2.INTER_LINEAR,
                         borderMode=cv2.BORDER_CONSTANT)

    def ground_point(self, u, v):
        """Intersect a rectified pixel ray with the floor; None above horizon/out of range.

        With zero pitch/roll and u=cx, forward = fy*H/(v-cy). Tilt rotates the
        full 3D ray, so off-centre bearings and distances remain consistent.
        """
        if not all(math.isfinite(q) for q in (u, v)):
            return None
        w, h = self.size
        if not (0 <= u < w and 0 <= v < h):
            return None
        # Undo the image roll about the principal point before normalizing.
        du, dv = u - self.K[0, 2], v - self.K[1, 2]
        cr, sr = math.cos(self.roll), math.sin(self.roll)
        right = (cr * du + sr * dv) / self.K[0, 0]
        down = (-sr * du + cr * dv) / self.K[1, 1]
        cp, sp = math.cos(self.pitch), math.sin(self.pitch)
        forward, vertical = cp - sp * down, sp + cp * down
        if vertical <= 0 or forward <= 0:
            return None
        scale = self.height_m / vertical
        point = GroundPoint(scale * forward, -scale * right)
        return point if point.distance_m <= self.max_range_m else None
