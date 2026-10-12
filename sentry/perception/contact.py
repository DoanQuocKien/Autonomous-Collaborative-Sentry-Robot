"""Candidate object/reflection contact from vertical symmetry, with abstention.

No midpoint-only correction: textured foreground and a distinct symmetry peak
are required. A segmentation/contact adapter can replace this estimator later.
"""
from dataclasses import dataclass
import math

import cv2
import numpy as np


@dataclass(frozen=True)
class ContactEstimate:
    u: float
    v: float
    method: str
    confidence: float


class ReflectionContactEstimator:
    def __init__(self, settings):
        self.settings = dict(settings)
        for key in ("reflection_window_px", "reflection_max_shift_px", "reflection_min_trim_px",
                    "reflection_flank_px"):
            if type(settings[key]) is not int or settings[key] < 1:
                raise ValueError("positive integer reflection windows required")
        for key in ("reflection_min_std", "reflection_peak_separation_px"):
            if not math.isfinite(settings[key]) or settings[key] <= 0:
                raise ValueError("positive reflection evidence thresholds required")
        for key in ("reflection_min_score", "reflection_min_peak_margin"):
            if not math.isfinite(settings[key]) or not 0 < settings[key] <= 1:
                raise ValueError("reflection correlation thresholds must be in (0,1]")

    def __call__(self, image, box, valid=None):
        s = self.settings
        x1, y1, x2, bottom = box
        left, right = int(math.floor(x1)), int(math.ceil(x2))
        h, w = image.shape[:2]
        flank, window = s["reflection_flank_px"], s["reflection_window_px"]
        if left - flank < 0 or right + flank > w or right - left < 3:
            return None
        # Bound how far a correction can move up; do not search a chair's whole body.
        shift = min(s["reflection_max_shift_px"], (bottom - y1) / 2)
        axes = np.arange(bottom - shift, bottom - s["reflection_min_trim_px"] + 0.01, 0.5)
        grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32)
        candidates = []
        for axis in axes:
            offsets = np.arange(window) + 0.5
            above, below = np.rint(axis - offsets).astype(int), np.rint(axis + offsets).astype(int)
            all_rows = np.r_[above, below]
            if all_rows.min() < 0 or all_rows.max() >= h:
                continue
            if valid is not None and not valid[all_rows, left - flank:right + flank].all():
                continue
            def profile(rows):
                # Local floor flanks remove lighting gradients, keeping rowwise object structure.
                flanks = np.concatenate((grey[rows, left - flank:left], grey[rows, right:right + flank]), axis=1)
                return np.median(grey[rows, left:right], axis=1) - np.median(flanks, axis=1)
            a, b = profile(above), profile(below)
            if min(float(a.std()), float(b.std())) < s["reflection_min_std"]:
                continue
            a, b = a - a.mean(), b - b.mean()
            score = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
            if math.isfinite(score):
                candidates.append((score, float(axis)))
        if not candidates:
            return None
        score, axis = max(candidates)
        others = [v for v, y in candidates if abs(y - axis) >= s["reflection_peak_separation_px"]]
        if (score < s["reflection_min_score"]
                or (others and score - max(others) < s["reflection_min_peak_margin"])):
            return None
        return ContactEstimate((x1 + x2) / 2, axis, "reflection_symmetry", score)
