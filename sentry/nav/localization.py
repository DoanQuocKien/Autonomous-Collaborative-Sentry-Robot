"""Robot localization: dead reckoning and ArUco marker pose correction.

Tracks 2D planar robot pose (x, y, theta) by integrating commanded (v, w)
normalized velocity commands via the per-wheel motion model (WheelModel,
calib/motion.json), and correcting drift when known ArUco fiducial markers
(DICT_4X4_50) are detected in camera frames.
"""
from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from sentry.nav.wheel_model import K_WHEEL, M0, TRACK, WheelModel


def wrap_angle(rad: float) -> float:
    """Wraps an angle in radians to [-pi, pi)."""
    return (rad + math.pi) % (2.0 * math.pi) - math.pi


def angle_diff(target: float, source: float) -> float:
    """Computes shortest signed angular difference (target - source) in [-pi, pi)."""
    return wrap_angle(target - source)


@dataclass
class RobotPose:
    """2D planar robot pose in the world frame.

    Compatible with both standard robotics naming (x, y, theta) and HNHL's
    Pose2D naming (x_m, y_m, yaw_rad) for seamless gridmap/prescan integration.
    """
    x: float = 0.0      # meters (forward / East)
    y: float = 0.0      # meters (lateral / North, left positive)
    theta: float = 0.0  # radians (counter-clockwise / yaw, left positive)
    t: float = 0.0      # timestamp in seconds

    def __init__(
        self,
        x: float = 0.0,
        y: float = 0.0,
        theta: float = 0.0,
        t: float = 0.0,
        *,
        x_m: float | None = None,
        y_m: float | None = None,
        yaw_rad: float | None = None,
    ) -> None:
        self.x = float(x_m if x_m is not None else x)
        self.y = float(y_m if y_m is not None else y)
        self.theta = float(yaw_rad if yaw_rad is not None else theta)
        self.t = float(t)

    @property
    def theta_deg(self) -> float:
        return math.degrees(self.theta)

    # Aliases for compatibility with sentry.nav.gridmap.Pose2D / PreScanner
    @property
    def x_m(self) -> float:
        return self.x

    @property
    def y_m(self) -> float:
        return self.y

    @property
    def yaw_rad(self) -> float:
        return self.theta

    def as_tuple(self) -> Tuple[float, float, float]:
        return (self.x, self.y, self.theta)

    def calculate_door_world_xy(self, bearing_rad: float, distance_m: float) -> Tuple[float, float]:
        """Calculates world-frame (x, y) coordinates of the entrance given relative bearing and distance.

        Parameters:
            bearing_rad: horizontal angle in radians relative to robot heading (positive left).
            distance_m: measured ground range from this pose origin to the door.
        """
        if (not all(math.isfinite(v) for v in (self.x, self.y, self.theta, bearing_rad, distance_m))
                or distance_m <= 0):
            raise ValueError("finite pose/bearing and positive measured door range required")
        target_yaw = self.theta + bearing_rad
        door_x = self.x + distance_m * math.cos(target_yaw)
        door_y = self.y + distance_m * math.sin(target_yaw)
        return (door_x, door_y)


@dataclass(frozen=True)
class MarkerAnchor:
    """Known 3D/2D location of an ArUco marker anchor in the room coordinate frame."""
    marker_id: int
    x: float                 # meters in world frame
    y: float                 # meters in world frame
    z: float = 0.15          # height above floor in meters
    yaw_rad: float = 0.0     # marker normal heading in world frame (facing into room)


@dataclass(frozen=True)
class MarkerDetection:
    """Detection information for a visible ArUco marker."""
    marker_id: int
    corners: np.ndarray      # (4, 2) pixel coordinates
    tvec: np.ndarray         # (3, 1) translation vector in camera optical frame
    rvec: np.ndarray         # (3, 1) rotation vector in camera optical frame
    distance_m: float        # Euclidean distance to marker
    bearing_rad: float       # horizontal bearing angle in camera frame (left positive)


class LocalizationTracker:
    """Tracks robot pose using dead reckoning on WheelModel with ArUco marker pose fusion.

    Dead-reckoning model from sentry/nav/wheel_model.py (fitted 2026-10-15):
        wheel speed [m/s] = scale * k * (|motor| - m0)   for |motor| >= min_pwm, else 0
        motor = (command mixed into left / right) * max_speed after per-wheel dead zone
        forward speed [m/s] = (vL + vR) / 2
        turn rate [rad/s] = (vR - vL) / track            (left positive, like w)
    """

    def __init__(
        self,
        motion_calib: dict[str, Any] | str | Path | None = "calib/motion.json",
        camera_calib: dict[str, Any] | str | Path | None = "calib/camera.json",
        aruco_dict_name: str | None = None,
        marker_size_m: float | None = None,
        initial_pose: RobotPose | None = None,
        config_path: str | Path | None = "config.toml",
        max_marker_distance_m: float = 1.5,
        wheel_model: WheelModel | None = None,
    ) -> None:
        self.wheel_model: WheelModel = wheel_model if wheel_model is not None else WheelModel()
        self.drift_rad_per_m: float = 0.0
        self.apply_drift_compensation: bool = False

        if motion_calib is not None and wheel_model is None:
            self._load_motion_calib(motion_calib)

        # Camera calibration
        self.K = np.array([
            [309.604, 0.0, 285.773],
            [0.0, 306.170, 239.149],
            [0.0, 0.0, 1.0],
        ], dtype=np.float64)
        self.D = np.array([-0.03288, 0.000466, -0.00643, 0.001745], dtype=np.float64)
        self.is_fisheye: bool = True

        if camera_calib is not None:
            self._load_camera_calib(camera_calib)

        # Load config tunables if available
        config_marker_m = 0.15
        config_dict = "DICT_4X4_50"
        if config_path is not None:
            cp = Path(config_path)
            if cp.is_file():
                try:
                    import tomllib
                    with open(cp, "rb") as f:
                        cfg = tomllib.load(f)
                    calib_cfg = cfg.get("calibration", {})
                    config_marker_m = float(calib_cfg.get("aruco_marker_m", config_marker_m))
                    config_dict = str(calib_cfg.get("aruco_dict", config_dict))
                except Exception:
                    pass

        # ArUco detector setup
        self.marker_size_m = float(marker_size_m if marker_size_m is not None else config_marker_m)
        self.max_marker_distance_m = float(max_marker_distance_m)
        dict_name = aruco_dict_name if aruco_dict_name is not None else config_dict
        dict_id = getattr(cv2.aruco, dict_name, cv2.aruco.DICT_4X4_50)
        self.dictionary = cv2.aruco.getPredefinedDictionary(dict_id)
        if hasattr(cv2.aruco, "ArucoDetector"):
            params = cv2.aruco.DetectorParameters()
            self.detector = cv2.aruco.ArucoDetector(self.dictionary, params)
        else:
            self.detector = None

        # State
        self.pose = initial_pose if initial_pose is not None else RobotPose()
        self.anchors: Dict[int, MarkerAnchor] = {}
        self.corrections_count: int = 0

    @property
    def min_pwm(self) -> float:
        return self.wheel_model.min_pwm

    @min_pwm.setter
    def min_pwm(self, value: float) -> None:
        self.wheel_model.min_pwm = float(value)

    @property
    def max_speed(self) -> float:
        return self.wheel_model.max_speed

    @max_speed.setter
    def max_speed(self, value: float) -> None:
        self.wheel_model.max_speed = float(value)

    @property
    def scale(self) -> float:
        return self.wheel_model.scale

    @scale.setter
    def scale(self, value: float) -> None:
        self.wheel_model.scale = float(value)

    def _load_motion_calib(self, calib_source: dict[str, Any] | str | Path) -> None:
        data: dict[str, Any] | None = None
        if isinstance(calib_source, (str, Path)):
            p = Path(calib_source)
            if p.is_file():
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
        elif isinstance(calib_source, dict):
            data = calib_source

        if not data:
            return

        wm = data.get("wheel_model") if isinstance(data.get("wheel_model"), dict) else None
        src = wm if wm is not None else data  # keys in the wheel_model block win, top-level keys are the fallback
        d = self.wheel_model

        def get(name, default, *aliases):
            for key in (name,) + aliases:
                if key in src:
                    return float(src[key])
            return float(data.get(name, default)) if src is not data else float(default)

        self.wheel_model = WheelModel(
            k=get("k_m_per_s_per_motor", d.k, *(("k",) if wm is not None else ())),
            m0=get("motor_offset", d.m0, "m0"),
            track=get("track_m", d.track, "track"),
            max_speed=get("max_speed", d.max_speed),
            min_pwm=get("min_pwm", d.min_pwm),
            scale=get("scale", d.scale),
            k_mix=get("k_mix", data.get("k", d.k_mix)),
        )
        if "drift_rad_per_m" in src:
            self.drift_rad_per_m = float(src["drift_rad_per_m"])
            self.apply_drift_compensation = self.drift_rad_per_m != 0.0

    def _load_camera_calib(self, calib_source: dict[str, Any] | str | Path) -> None:
        data: dict[str, Any] | None = None
        if isinstance(calib_source, (str, Path)):
            p = Path(calib_source)
            if p.is_file():
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
        elif isinstance(calib_source, dict):
            data = calib_source

        if data:
            if "K" in data:
                self.K = np.array(data["K"], dtype=np.float64)
            if "D" in data:
                self.D = np.array(data["D"], dtype=np.float64)
            model = data.get("model", "")
            self.is_fisheye = "fisheye" in model

    def set_pose(self, x: float, y: float, theta: float, t: float = 0.0) -> None:
        """Explicitly sets current robot pose."""
        self.pose = RobotPose(x=x, y=y, theta=wrap_angle(theta), t=t)

    def add_anchor(self, anchor: MarkerAnchor) -> None:
        """Registers a known ArUco marker location."""
        self.anchors[anchor.marker_id] = anchor

    def load_anchors_csv(self, csv_path: str | Path) -> None:
        """Loads marker anchors from a CSV file (e.g. marker_positions_template.csv)."""
        p = Path(csv_path)
        if not p.is_file():
            return
        with open(p, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                mid = int(row["marker_id"])
                x = float(row["x_m"])
                y = float(row["y_m"])
                z = float(row.get("z_m", 0.15))
                yaw = math.radians(float(row.get("yaw_deg", 0.0)))
                self.add_anchor(MarkerAnchor(marker_id=mid, x=x, y=y, z=z, yaw_rad=yaw))

    def update_odometry(self, v: float, w: float, dt: float, t: float | None = None) -> RobotPose:
        """Updates robot pose via dead reckoning from commanded normalized (v, w) over duration dt."""
        if dt <= 0.0:
            if t is not None:
                self.pose.t = t
            return self.pose

        # Normalize command values
        v = float(np.clip(v, -1.0, 1.0))
        w = float(np.clip(w, -1.0, 1.0))

        # Per-wheel speed and turn rate from WheelModel (mix -> speed cap -> per-wheel deadzone -> wheel law)
        v_mps, w_radps = self.wheel_model.body_speeds(v, w)
        delta_s = v_mps * dt

        delta_theta = w_radps * dt
        if self.apply_drift_compensation and self.drift_rad_per_m != 0.0:
            delta_theta += self.drift_rad_per_m * delta_s

        theta = self.pose.theta

        # Exact circular arc integration
        if abs(delta_theta) < 1e-6:
            dx = delta_s * math.cos(theta + delta_theta * 0.5)
            dy = delta_s * math.sin(theta + delta_theta * 0.5)
        else:
            radius = delta_s / delta_theta
            dx = radius * (math.sin(theta + delta_theta) - math.sin(theta))
            dy = -radius * (math.cos(theta + delta_theta) - math.cos(theta))

        new_x = self.pose.x + dx
        new_y = self.pose.y + dy
        new_theta = wrap_angle(theta + delta_theta)
        new_t = self.pose.t + dt if t is None else t

        self.pose = RobotPose(x=new_x, y=new_y, theta=new_theta, t=new_t)
        return self.pose

    def detect_markers(self, frame_bgr: np.ndarray) -> List[MarkerDetection]:
        """Detects ArUco markers in the frame and computes pose relative to camera."""
        if frame_bgr is None or frame_bgr.size == 0:
            return []

        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY) if frame_bgr.ndim == 3 else frame_bgr

        if self.detector is not None:
            corners, ids, _ = self.detector.detectMarkers(gray)
        else:
            corners, ids, _ = cv2.aruco.detectMarkers(gray, self.dictionary)

        if ids is None or len(ids) == 0:
            return []

        # 3D coordinates of marker corners in marker coordinate system
        s = self.marker_size_m / 2.0
        # Order: top-left, top-right, bottom-right, bottom-left
        obj_pts = np.array([
            [-s, s, 0.0],
            [s, s, 0.0],
            [s, -s, 0.0],
            [-s, -s, 0.0],
        ], dtype=np.float64)

        detections: List[MarkerDetection] = []
        for i, mid in enumerate(ids.ravel()):
            corner_pts = corners[i].reshape(4, 2).astype(np.float64)

            if self.is_fisheye:
                pts_undist = cv2.fisheye.undistortPoints(
                    corner_pts.reshape(-1, 1, 2),
                    self.K,
                    self.D,
                    R=np.eye(3),
                    P=self.K,
                ).reshape(-1, 2)
                img_pts = pts_undist
                dist_coeffs = None
            else:
                img_pts = corner_pts
                dist_coeffs = self.D

            res = cv2.solvePnPGeneric(
                obj_pts,
                img_pts,
                self.K,
                dist_coeffs,
                flags=cv2.SOLVEPNP_IPPE_SQUARE,
            )
            n_sol = res[0]
            rvecs = res[1] if n_sol else ()
            tvecs = res[2] if n_sol else ()
            errs = res[3] if len(res) > 3 and n_sol else ()

            cands = []
            for j in range(len(rvecs)):
                rv = rvecs[j]
                tv = tvecs[j]
                err = float(np.asarray(errs[j]).ravel()[0]) if len(errs) > j else 0.0
                if np.isfinite(err) and np.all(np.isfinite(rv)) and np.all(np.isfinite(tv)):
                    cands.append((err, rv, tv))

            # OpenCV 5.0's IPPE can return NaN on exact noise-free views: fall back to iterative solver
            if not cands:
                ok, rv_iter, tv_iter = cv2.solvePnP(
                    obj_pts,
                    img_pts,
                    self.K,
                    dist_coeffs,
                    flags=cv2.SOLVEPNP_ITERATIVE,
                )
                if ok and np.all(np.isfinite(rv_iter)) and np.all(np.isfinite(tv_iter)):
                    cands = [(0.0, rv_iter, tv_iter)]

            best = None
            for err, rv, tv in cands:
                R, _ = cv2.Rodrigues(rv)
                tv_flat = tv.reshape(3)
                P_cam = -R.T @ tv_flat
                # Camera must be in front of marker wall (Z > 0 in marker frame)
                if P_cam[2] <= 0:
                    continue
                if best is None or err < best[0]:
                    best = (err, rv.reshape(3, 1), tv.reshape(3, 1))

            if best is None:
                continue

            _, best_rvec, best_tvec = best
            dist = float(np.linalg.norm(best_tvec))
            # Camera optical frame: X is right, Z is forward
            # Bearing is angle to the optical axis (positive left -> -X)
            bearing = math.atan2(-float(best_tvec[0][0]), float(best_tvec[2][0]))

            detections.append(
                MarkerDetection(
                    marker_id=int(mid),
                    corners=corner_pts,
                    tvec=best_tvec,
                    rvec=best_rvec,
                    distance_m=dist,
                    bearing_rad=bearing,
                )
            )

        return detections

    def update_with_markers(
        self,
        frame_bgr: np.ndarray,
        alpha: float = 0.4,
        t: float | None = None,
    ) -> Tuple[RobotPose, List[MarkerDetection]]:
        """Detects visible markers, estimates robot pose against known anchors, and fuses with current pose.

        Parameters:
            frame_bgr: current camera frame
            alpha: filter gain for correction (0.0 = no update, 1.0 = instant snap)
            t: optional frame timestamp
        """
        detections = self.detect_markers(frame_bgr)
        if t is not None:
            self.pose.t = t

        if not detections or not self.anchors:
            return self.pose, detections

        # Process first known anchor detected
        for det in detections:
            if det.marker_id in self.anchors:
                # Reject markers beyond maximum reliable range (noisy beyond 1.5 m)
                if det.distance_m > self.max_marker_distance_m:
                    continue

                anchor = self.anchors[det.marker_id]

                # R_cm: rotation from marker to camera
                R_cm, _ = cv2.Rodrigues(det.rvec)
                # t_cm: translation of marker in camera frame
                t_cm = det.tvec

                # Camera position in marker coordinates: P_marker = -R_cm^T * t_cm
                P_cam_in_marker = -R_cm.T @ t_cm

                # In 2D floor projection:
                # Marker coordinate frame has Z normal pointing outwards.
                # Transform camera position in marker frame to room coordinates:
                theta_m = anchor.yaw_rad
                x_rel = float(P_cam_in_marker[0][0])
                z_rel = float(P_cam_in_marker[2][0])

                # Position of camera in world
                x_cam_world = anchor.x + z_rel * math.cos(theta_m) - x_rel * math.sin(theta_m)
                y_cam_world = anchor.y + z_rel * math.sin(theta_m) + x_rel * math.cos(theta_m)

                # Camera heading:
                # Normal of marker seen in camera frame is R_cm[:, 2].
                yaw_cam = wrap_angle(anchor.yaw_rad + math.pi - math.atan2(R_cm[0, 2], R_cm[2, 2]))

                # Filter update (alpha blend with range falloff beyond 0.8 m)
                base_alpha = float(np.clip(alpha, 0.0, 1.0))
                near_range_m = 0.8
                if det.distance_m > near_range_m:
                    range_decay = max(
                        0.0,
                        (self.max_marker_distance_m - det.distance_m) / (self.max_marker_distance_m - near_range_m),
                    )
                else:
                    range_decay = 1.0
                effective_alpha = base_alpha * range_decay

                if effective_alpha <= 0.0:
                    continue

                d_theta = angle_diff(yaw_cam, self.pose.theta)
                # Outlier jump rejection: once tracking is established, reject erratic heading jumps > 25 deg
                if self.corrections_count >= 3 and abs(d_theta) > math.radians(25.0):
                    continue

                new_x = (1.0 - effective_alpha) * self.pose.x + effective_alpha * x_cam_world
                new_y = (1.0 - effective_alpha) * self.pose.y + effective_alpha * y_cam_world
                new_theta = wrap_angle(self.pose.theta + effective_alpha * d_theta)

                self.pose = RobotPose(x=new_x, y=new_y, theta=new_theta, t=self.pose.t)
                self.corrections_count += 1
                break

        return self.pose, detections
