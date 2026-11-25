"""YOLOv8 pose inference and timestamped lunge cues. No motor/network I/O.

The default cue is the spec's strict dA/A > 0.40 within 100 ms. It describes
image geometry, not intent. D4 determines recall/false alarms. Optional ankle
rise is relative to the hips and bbox height; it is disabled until calibrated.
One detector consumes one selected target stream, not a list of people.
"""
from collections import deque
from dataclasses import dataclass
import math
from pathlib import Path

import numpy as np

from sentry.config import DEFAULT_PATH, load


@dataclass(frozen=True)
class LungeSettings:
    area_growth: float = .40
    window_s: float = .10
    min_bbox_area_px2: float = 400.0
    keypoint_confidence: float = .5
    ankle_rise_fraction: float = 0.0

    def __post_init__(self):
        for name in ('area_growth', 'window_s', 'min_bbox_area_px2'):
            if not math.isfinite(getattr(self, name)) or getattr(self, name) <= 0:
                raise ValueError(name + ' must be positive and finite')
        if not math.isfinite(self.keypoint_confidence) or not 0 <= self.keypoint_confidence <= 1:
            raise ValueError('keypoint confidence must be in [0, 1]')
        if not math.isfinite(self.ankle_rise_fraction) or self.ankle_rise_fraction < 0:
            raise ValueError('ankle rise must be finite and nonnegative (0 disables it)')

    @classmethod
    def from_config(cls, cfg=None):
        cfg = load() if cfg is None else cfg
        return cls(area_growth=cfg['thresholds']['strike_area_growth'],
                   window_s=cfg['thresholds']['strike_window_s'], **cfg.get('strike', {}))


@dataclass(frozen=True)
class LungeResult:
    t: float
    strike: bool
    reason: str
    area_growth: float = 0.0
    interval_s: float | None = None
    ankle_rise_fraction: float = 0.0


class LungeDetector:
    def __init__(self, settings=None):
        self.settings = LungeSettings.from_config() if settings is None else settings
        self.reset()

    def reset(self):
        self._history = deque(maxlen=256)
        self._last_t = self._key = self._size = None
        self.last_result = None

    def _ankles(self, points, confidence, height):
        if not self.settings.ankle_rise_fraction or points is None or confidence is None:
            return {}
        try:
            p, c = np.asarray(points, dtype=float), np.asarray(confidence, dtype=float)
        except (ValueError, TypeError):
            return {}
        if p.shape != (17, 2) or c.shape != (17,):
            return {}
        valid = np.isfinite(p).all(axis=1) & np.isfinite(c) & (c >= self.settings.keypoint_confidence)
        hips = [i for i in (11, 12) if valid[i]]
        if not hips:
            return {}
        hip_y = float(p[hips, 1].mean())
        return {i: (p[i, 1] - hip_y) / height for i in (15, 16) if valid[i]}

    def update(self, t, bbox, *, track_id=0, epoch=0, frame_size=None,
               keypoints_xy=None, keypoints_conf=None):
        if isinstance(t, bool) or not isinstance(t, (float, int)) or not math.isfinite(t):
            self.reset()
            raise ValueError('finite numeric timestamp required')
        t = float(t)
        key = (epoch, track_id)
        size = tuple(frame_size) if frame_size is not None else None
        reason = 'warmup'
        if self._last_t is not None and t <= self._last_t:
            self._history.clear()
            reason = 'clock_reset' if t < self._last_t else 'duplicate_timestamp'
        if key != self._key or size != self._size:
            self._history.clear()
        self._last_t, self._key, self._size = t, key, size

        def result(hit=False, why=reason, growth=0.0, interval=None, rise=0.0):
            self.last_result = LungeResult(t, hit, why, float(growth), interval, float(rise))
            return self.last_result

        if reason == 'duplicate_timestamp':
            return result()
        try:
            b = np.asarray(bbox, dtype=float)
        except (ValueError, TypeError):
            b = np.array([])
        if b.shape != (4,) or not np.isfinite(b).all() or b[2] <= b[0] or b[3] <= b[1]:
            self._history.clear()
            return result(why='missing_or_invalid_bbox')
        area = float((b[2] - b[0]) * (b[3] - b[1]))
        if not math.isfinite(area) or area < self.settings.min_bbox_area_px2:
            self._history.clear()
            return result(why='small_bbox')
        if size is not None:
            if len(size) != 2 or not all(math.isfinite(v) and v > 0 for v in size):
                self._history.clear()
                raise ValueError('frame_size must be (width, height) with finite positive values')
            if b[0] <= 0 or b[1] <= 0 or b[2] >= size[0] or b[3] >= size[1]:
                self._history.clear()
                return result(why='edge_cut')
        # One microsecond allows rounding of recorded seconds at the boundary.
        while self._history and t - self._history[0][0] > self.settings.window_s + 1e-6:
            self._history.popleft()
        ankles = self._ankles(keypoints_xy, keypoints_conf, b[3] - b[1])
        growth, interval, rise = 0.0, None, 0.0
        for previous_t, previous_area, previous_ankles in self._history:
            g = (area - previous_area) / previous_area
            if g > growth:
                growth, interval = g, t - previous_t
            rise = max([rise] + [previous_ankles[i] - ankles[i] for i in ankles.keys() & previous_ankles.keys()])
        had_baseline = bool(self._history)
        self._history.append((t, area, ankles))
        if growth > self.settings.area_growth:
            return result(True, 'bbox_area_growth', growth, interval, rise)
        if self.settings.ankle_rise_fraction and rise > self.settings.ankle_rise_fraction:
            return result(True, 'ankle_rise', growth, interval, rise)
        return result(why='below_threshold' if had_baseline else reason,
                      growth=growth, interval=interval, rise=rise)

    def __call__(self, t, sample):
        """KR harness callable(t, sample) -> bool; capture time governs the cue.

        sample['t'] may remain laptop wall time to align label_events onsets.
        Epoch/target/resize changes, missing boxes and time rollback reset history.
        Repeated frames never accumulate confirmation.
        """
        return self.update(sample.get('t_cap', t), sample.get('bbox'),
            track_id=sample.get('track_id', 0), epoch=sample.get('epoch', 0),
            frame_size=sample.get('frame_size'), keypoints_xy=sample.get('keypoints_xy'),
            keypoints_conf=sample.get('keypoints_conf')).strike


@dataclass(frozen=True)
class PosePerson:
    xyxy: tuple
    confidence: float
    keypoints_xy: np.ndarray
    keypoints_conf: np.ndarray


class YOLOPoseEstimator:
    def __init__(self, weights=None, device=None, imgsz=640, confidence=.3):
        cfg = load()['reid']
        self.weights = Path(weights or (DEFAULT_PATH.parent / cfg.get('pose_weights', 'data/models/yolov8n-pose.pt'))).resolve()
        if not self.weights.is_file():
            raise FileNotFoundError(self.weights)
        if type(imgsz) is not int or imgsz < 32 or imgsz % 32:
            raise ValueError('imgsz must be a positive multiple of 32')
        if not math.isfinite(confidence) or not 0 < confidence <= 1:
            raise ValueError('confidence must be in (0, 1]')
        from ultralytics import YOLO
        self.model = YOLO(str(self.weights))
        if self.model.task != 'pose':
            raise ValueError('YOLO pose weights required')
        self.device = cfg['person_device'] if device is None else device
        self.imgsz, self.confidence = imgsz, confidence

    @property
    def actual_device(self):
        predictor = getattr(self.model, 'predictor', None)
        return str(predictor.device if predictor is not None else next(self.model.model.parameters()).device)

    def predict(self, image):
        if not isinstance(image, np.ndarray) or image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3 or not image.size:
            raise ValueError('nonempty uint8 BGR image required')
        r = self.model.predict(image, imgsz=self.imgsz, device=self.device,
                               conf=self.confidence, verbose=False)[0]
        if r.keypoints is None or r.keypoints.conf is None:
            return []
        return [PosePerson(tuple(map(float, b)), float(c), p.copy(), k.copy())
                for b, c, p, k in zip(r.boxes.xyxy.cpu().numpy(), r.boxes.conf.cpu().numpy(),
                                     r.keypoints.xy.cpu().numpy(), r.keypoints.conf.cpu().numpy())]
