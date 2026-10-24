"""Geometric fallback for thin floor-level wires and cables (Week 3, HNHL).

Detects thin dark or bright linear structures on the floor plane as a fallback
when learned object detectors fail on 1-2 px thin wires (Implementation Plan line 238,
Risk 30).
"""
from dataclasses import dataclass
import math
from typing import List, Optional, Tuple

import cv2
import numpy as np

from sentry.config import load
from sentry.perception.camera import CameraGeometry


@dataclass(frozen=True)
class WireCandidate:
    pt1: Tuple[float, float]          # (x, y) start pixel
    pt2: Tuple[float, float]          # (x, y) end pixel
    length_px: float                  # segment length in pixels
    contrast: float                   # intensity difference vs local background
    polarity: str                     # 'dark' or 'bright'
    ground_range_m: Optional[float]   # distance to nearest point on the floor
    bearing_rad: Optional[float]      # bearing to nearest point (positive = left)
    keep_clear: bool                  # True if within keep-clear repulsive distance


class WireGeometricFallback:
    """Heuristic detector for floor wires using line analysis and ground-plane validation."""

    def __init__(
        self,
        camera: Optional[CameraGeometry] = None,
        min_length_px: float = 35.0,
        contrast_threshold: float = 18.0,
        floor_crop_fraction: float = 0.50,
        keep_clear_m: float = 0.80,
    ):
        self.camera = camera
        self.min_length_px = float(min_length_px)
        self.contrast_threshold = float(contrast_threshold)
        self.floor_crop_fraction = float(floor_crop_fraction)
        self.keep_clear_m = float(keep_clear_m)
        self.lsd = cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD)

    @classmethod
    def from_config(cls, camera: Optional[CameraGeometry] = None):
        cfg = load().get("thresholds", {})
        keep_clear = float(cfg.get("obstacle_explore_m", 0.6)) + 0.2
        return cls(camera=camera, keep_clear_m=keep_clear)

    def detect(self, frame_bgr: np.ndarray) -> List[WireCandidate]:
        """Detect wire candidates on the floor in the input BGR image."""
        if not isinstance(frame_bgr, np.ndarray) or frame_bgr.ndim != 3:
            raise ValueError("Expected uint8 BGR image with shape (H, W, 3)")

        h, w = frame_bgr.shape[:2]
        crop_y = int(h * (1.0 - self.floor_crop_fraction))
        floor_roi = frame_bgr[crop_y:h, 0:w]

        gray = cv2.cvtColor(floor_roi, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 1.0)

        lines, _, _, _ = self.lsd.detect(blurred)
        if lines is None:
            return []

        candidates: List[WireCandidate] = []

        for line in lines:
            x1, y1, x2, y2 = line.reshape(-1)[:4]
            full_y1 = y1 + crop_y
            full_y2 = y2 + crop_y

            dx = x2 - x1
            dy = y2 - y1
            length = math.hypot(dx, dy)
            if length < self.min_length_px:
                continue

            mx = int(round((x1 + x2) / 2.0))
            my = int(round((y1 + y2) / 2.0))

            if not (6 <= mx < w - 6 and 6 <= my < floor_roi.shape[0] - 6):
                continue

            # Normal vector to line
            nx = -dy / (length + 1e-6)
            ny = dx / (length + 1e-6)

            # Sample profile across the line from -5 to +5 pixels
            profile = []
            for k in range(-5, 6):
                px = int(round(mx + k * nx))
                py = int(round(my + k * ny))
                if 0 <= px < w and 0 <= py < floor_roi.shape[0]:
                    profile.append(float(gray[py, px]))

            if len(profile) < 9:
                continue

            flank_val = (profile[0] + profile[-1]) / 2.0
            min_val = min(profile)
            max_val = max(profile)

            dark_contrast = flank_val - min_val
            bright_contrast = max_val - flank_val

            if dark_contrast >= self.contrast_threshold and dark_contrast >= bright_contrast:
                polarity = "dark"
                contrast = dark_contrast
            elif bright_contrast >= self.contrast_threshold:
                polarity = "bright"
                contrast = bright_contrast
            else:
                continue

            # Nearest point (maximum y, closest to robot base)
            closest_x = x1 if full_y1 > full_y2 else x2
            closest_y = max(full_y1, full_y2)

            ground_range = None
            bearing = None
            keep_clear = False

            if self.camera is not None:
                pt = self.camera.ground_point(closest_x, closest_y)
                if pt is not None:
                    ground_range = pt.distance_m
                    bearing = pt.bearing_rad
                    keep_clear = ground_range <= self.keep_clear_m

            candidates.append(WireCandidate(
                pt1=(float(x1), float(full_y1)),
                pt2=(float(x2), float(full_y2)),
                length_px=float(length),
                contrast=float(contrast),
                polarity=polarity,
                ground_range_m=ground_range,
                bearing_rad=bearing,
                keep_clear=keep_clear,
            ))

        return candidates
