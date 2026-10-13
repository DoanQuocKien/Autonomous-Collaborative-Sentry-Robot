"""YOLO furniture observations and normalized angular repulsion; no motor I/O."""
from dataclasses import dataclass
import math
from pathlib import Path
from typing import Callable

import numpy as np

from sentry.config import DEFAULT_PATH, load
from .camera import CameraGeometry, GroundPoint


@dataclass(frozen=True)
class Detection:
    class_id: int
    confidence: float
    xyxy: tuple[float, float, float, float]


@dataclass(frozen=True)
class Obstacle:
    detection: Detection
    ground: GroundPoint | None
    rejection: str | None = None


@dataclass(frozen=True)
class ObstacleResult:
    t: float
    obstacles: tuple[Obstacle, ...]
    repulsive_w: float
    nearest_m: float | None

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
    def __init__(self, geometry: CameraGeometry, predictor: Callable, settings, thresholds):
        self.geometry, self.predictor = geometry, predictor
        self.settings, self.thresholds = dict(settings), dict(thresholds)
        if (not math.isfinite(settings["confidence"]) or not 0 <= settings["confidence"] <= 1
                or not math.isfinite(settings["bottom_margin_px"]) or settings["bottom_margin_px"] < 1):
            raise ValueError("invalid detection thresholds")
        self.class_ids = frozenset(settings["class_ids"])
        for mode in ("explore", "pursuit"):
            repulsive_w((), thresholds["obstacle_" + mode + "_m"], settings["repulsion_gain"],
                        settings["repulsion_max_w"], settings["centre_turn"])

    @classmethod
    def from_config(cls, config_path=DEFAULT_PATH, predictor=None):
        config = load(config_path)
        root = Path(config_path).resolve().parent
        s = config["obstacle"]
        geometry = CameraGeometry.from_files(root / s["camera_calibration"], root / s["camera_pose"],
                                             s["max_ground_range_m"])
        return cls(geometry, predictor if predictor is not None else YOLOPredictor(root / s["weights"], s),
                   s, config["thresholds"])

    def __call__(self, frame_bgr, t, mode="explore"):
        if not math.isfinite(t) or mode not in ("explore", "pursuit"):
            raise ValueError("finite timestamp and explore/pursuit mode required")
        image = self.geometry.undistort(frame_bgr)
        w, h = self.geometry.size
        observations = []
        for detection in self.predictor(image):
            if detection.class_id not in self.class_ids:
                continue
            if (not math.isfinite(detection.confidence) or not 0 <= detection.confidence <= 1
                    or detection.confidence < self.settings["confidence"]):
                continue
            box = detection.xyxy
            point, reason = None, None
            if (len(box) != 4 or not all(math.isfinite(x) for x in box)
                    or not (0 <= box[0] < box[2] <= w and 0 <= box[1] < box[3] <= h)):
                reason = "invalid_box"
            elif box[3] >= h - self.settings["bottom_margin_px"]:
                reason = "bottom_truncated"
            else:
                u, v = (box[0] + box[2]) / 2, box[3]
                if not self.geometry.valid[min(int(v), h - 1), min(int(u), w - 1)]:
                    reason = "invalid_rectified_pixel"
                else:
                    point = self.geometry.ground_point(u, v)
                    if point is None:
                        reason = "no_ground_intersection_or_out_of_range"
            observations.append(Obstacle(detection, point, reason))
        points = tuple(o.ground for o in observations if o.ground is not None)
        s = self.settings
        repulsion = repulsive_w(points, self.thresholds["obstacle_" + mode + "_m"],
                                s["repulsion_gain"], s["repulsion_max_w"], s["centre_turn"])
        return ObstacleResult(float(t), tuple(observations), repulsion,
                              min((p.distance_m for p in points), default=None))
