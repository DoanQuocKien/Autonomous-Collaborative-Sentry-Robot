"""YOLO furniture observations and normalized angular repulsion; no motor I/O."""
from dataclasses import dataclass
import math
from pathlib import Path
from typing import Callable

import numpy as np

from sentry.config import DEFAULT_PATH, load
from .camera import CameraGeometry, GroundPoint
from .contact import ContactEstimate, ReflectionContactEstimator


@dataclass(frozen=True)
class Detection:
    class_id: int
    confidence: float
    xyxy: tuple[float, float, float, float]
    flat_on_floor: bool = False  # explicit annotation/adapter fact, never inferred from class ID


@dataclass(frozen=True)
class Obstacle:
    detection: Detection
    ground: GroundPoint | None
    rejection: str | None = None
    contact: ContactEstimate | None = None


@dataclass(frozen=True)
class ObstacleResult:
    t: float
    obstacles: tuple[Obstacle, ...]
    repulsive_w: float
    nearest_m: float | None
    floor_type: str = "unknown"
    camera_session: str = "unspecified"

    @property
    def ground_points(self):
        return tuple(o.ground for o in self.obstacles if o.ground is not None)

    @property
    def unresolved(self):
        return any(o.ground is None for o in self.obstacles)


def repulsive_w(points, threshold_m, gain=1.0, max_w=1.0, centre_turn=1):
    """Left obstacle -> negative w (right turn); right obstacle -> positive w.

    This is only an angular contribution. Zero can also mean balanced obstacles;
    callers must inspect nearest_m/unresolved before deciding to drive.
    """
    if (not all(math.isfinite(v) for v in (threshold_m, gain, max_w))
            or threshold_m <= 0 or gain < 0 or not 0 < max_w <= 1 or centre_turn not in (-1, 1)):
        raise ValueError("invalid repulsion parameters")
    total = 0.0
    for point in points:
        if point.distance_m < threshold_m:
            sign = -1 if point.left_m > 0 else 1 if point.left_m < 0 else centre_turn
            total += sign * gain * (1 - point.distance_m / threshold_m)
    return float(np.clip(total, -max_w, max_w))


class YOLOPredictor:
    """Local weights only; imports ultralytics when inference is constructed."""
    def __init__(self, weights, settings):
        weights = Path(weights)
        if not weights.is_file():
            raise FileNotFoundError("fetch local YOLO weights first: " + str(weights))
        from ultralytics import YOLO
        from ultralytics.cfg import DEFAULT_CFG_DICT
        self.model = YOLO(str(weights))
        self.settings = settings
        # Current releases renamed half to quantize; older team environments keep half.
        self.precision = {"quantize": 32} if "quantize" in DEFAULT_CFG_DICT else {"half": False}

    def __call__(self, image):
        s = self.settings
        results = self.model.predict(image, imgsz=s["imgsz"], conf=s["confidence"],
                                     classes=s["class_ids"], device=s["device"],
                                     batch=1, verbose=False, **self.precision)
        boxes = results[0].boxes
        if boxes is None:
            return ()
        return tuple(Detection(int(c), float(p), tuple(map(float, b)))
                     for b, c, p in zip(boxes.xyxy.cpu().numpy(), boxes.cls.cpu().numpy(),
                                        boxes.conf.cpu().numpy()))


class ObstacleDetector:
    def __init__(self, geometry: CameraGeometry, predictor: Callable, settings, thresholds, tilt=None):
        self.geometry, self.predictor, self.tilt = geometry, predictor, tilt     # tilt: camera_pose.LiveTilt, updates geometry.pitch from ArUco pages
        self.settings, self.thresholds = dict(settings), dict(thresholds)
        if (not math.isfinite(settings["confidence"]) or not 0 <= settings["confidence"] <= 1
                or not math.isfinite(settings["border_margin_px"]) or settings["border_margin_px"] < 1):
            raise ValueError("invalid detection thresholds")
        self.class_ids = frozenset(settings["class_ids"])
        self.contact_estimator = ReflectionContactEstimator(settings)
        for mode in ("explore", "pursuit"):
            repulsive_w((), thresholds["obstacle_" + mode + "_m"], settings["repulsion_gain"],
                        settings["repulsion_max_w"], settings["centre_turn"])

    @classmethod
    def from_config(cls, config_path=DEFAULT_PATH, predictor=None, camera_pose_path=None,
                    camera_path=None, floor_type=None):
        config = load(config_path)
        root = Path(config_path).resolve().parent
        s = dict(config["obstacle"])
        if camera_pose_path is not None:
            s["camera_pose"] = str(Path(camera_pose_path).resolve())
        if camera_path is not None:
            s["camera_calibration"] = str(Path(camera_path).resolve())
        if floor_type is not None:
            s["floor_type"] = floor_type
        geometry = CameraGeometry.from_files(root / s["camera_calibration"], root / s["camera_pose"],
                                             s["max_ground_range_m"], s["pose_max_rms_m"])
        return cls(geometry, predictor if predictor is not None else YOLOPredictor(root / s["weights"], s),
                   s, config["thresholds"])

    def __call__(self, frame_bgr, t, mode="explore", floor_type=None):
        floor_type = self.settings["floor_type"] if floor_type is None else floor_type
        if (not math.isfinite(t) or mode not in ("explore", "pursuit")
                or floor_type not in ("glossy", "matte", "unknown")):
            raise ValueError("finite timestamp and explore/pursuit mode required")
        image = self.geometry.undistort(frame_bgr)
        if self.tilt is not None:
            self.tilt.raw(frame_bgr)                                     # raw frame: finds markers far off-axis
        w, h = self.geometry.size
        observations = []
        for detection in self.predictor(image):
            if detection.class_id not in self.class_ids:
                continue
            if (not math.isfinite(detection.confidence) or not 0 <= detection.confidence <= 1
                    or detection.confidence < self.settings["confidence"]):
                continue
            box = detection.xyxy
            point, reason, contact = None, None, None
            margin = self.settings["border_margin_px"]
            if (len(box) != 4 or not all(math.isfinite(x) for x in box)
                    or not (0 <= box[0] < box[2] <= w and 0 <= box[1] < box[3] <= h)):
                reason = "invalid_box"
            elif box[3] >= h - margin:
                reason = "bottom_truncated"
            elif box[0] <= margin or box[1] <= margin or box[2] >= w - margin:
                reason = "border_truncated"
            else:
                if floor_type == "matte" or detection.flat_on_floor:
                    contact = ContactEstimate((box[0] + box[2]) / 2, box[3],
                                              "bbox_known_flat" if detection.flat_on_floor else "bbox_matte", 1.0)
                elif floor_type == "glossy":
                    contact = self.contact_estimator(image, box, self.geometry.valid)
                if contact is None:
                    reason = "reflection_unresolved" if floor_type == "glossy" else "floor_type_unknown"
                elif not self.geometry.valid[min(int(contact.v), h - 1), min(int(contact.u), w - 1)]:
                    reason = "invalid_rectified_pixel"
                else:
                    point = self.geometry.ground_point(contact.u, contact.v)
                    if point is None:
                        reason = "no_ground_intersection_or_out_of_range"
            observations.append(Obstacle(detection, point, reason, contact))
        points = tuple(o.ground for o in observations if o.ground is not None)
        s = self.settings
        repulsion = repulsive_w(points, self.thresholds["obstacle_" + mode + "_m"],
                                s["repulsion_gain"], s["repulsion_max_w"], s["centre_turn"])
        return ObstacleResult(float(t), tuple(observations), repulsion,
                              min((p.distance_m for p in points), default=None), floor_type, self.geometry.session)
