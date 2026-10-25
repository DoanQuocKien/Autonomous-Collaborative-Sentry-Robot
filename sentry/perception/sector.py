"""Departure sector classification from horizontal bounding-box drift (Spec §4.6, Implementation Plan §4.3).

Owner: kouun-rokku (KR).
Pure CPU logic for logging the horizontal drift of an entrant's bounding box
over up to 2.0 s on the ESP32-CAM stream -> Left ('L') / Center ('C') / Right ('R').
This provides an optional search prior for the room coverage planner (Week 9).
"""
from dataclasses import dataclass
from enum import Enum
import math
from typing import Iterable, List, Optional, Sequence, Tuple, Union

from sentry.config import load


class DepartureSector(str, Enum):
    """Canonical departure sectors in camera frame coordinates."""
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"
    UNKNOWN = "unknown"


# Accepted aliases and shorthands
SECTOR_ALIASES = {
    "l": DepartureSector.LEFT.value,
    "left": DepartureSector.LEFT.value,
    "c": DepartureSector.CENTER.value,
    "center": DepartureSector.CENTER.value,
    "centre": DepartureSector.CENTER.value,
    "r": DepartureSector.RIGHT.value,
    "right": DepartureSector.RIGHT.value,
    "u": DepartureSector.UNKNOWN.value,
    "unknown": DepartureSector.UNKNOWN.value,
}

SECTOR_CODES = {
    DepartureSector.LEFT.value: "L",
    DepartureSector.CENTER.value: "C",
    DepartureSector.RIGHT.value: "R",
    DepartureSector.UNKNOWN.value: "U",
}


def normalize_sector(val: Union[str, DepartureSector, None]) -> str:
    """Normalize any sector name or code into 'left', 'center', 'right', or 'unknown'."""
    if val is None:
        return DepartureSector.UNKNOWN.value
    s = str(val).strip().lower()
    return SECTOR_ALIASES.get(s, DepartureSector.UNKNOWN.value)


def sector_code(val: Union[str, DepartureSector, None]) -> str:
    """Return single-letter code ('L', 'C', 'R', or 'U')."""
    norm = normalize_sector(val)
    return SECTOR_CODES.get(norm, "U")


@dataclass(frozen=True)
class SectorConfig:
    """Tunables for bounding-box horizontal drift classification."""
    window_s: float = 2.0
    drift_threshold: float = 0.08  # Fraction of frame width separating L/R from C
    min_points: int = 3           # Minimum points needed to evaluate drift

    @classmethod
    def from_toml(cls, cfg: Optional[dict] = None) -> "SectorConfig":
        """Load from config.toml [sector] section with fallbacks."""
        raw = load() if cfg is None else cfg
        sec = raw.get("sector", {})
        return cls(
            window_s=float(sec.get("window_s", 2.0)),
            drift_threshold=float(sec.get("drift_threshold", 0.08)),
            min_points=int(sec.get("min_points", 3)),
        )


@dataclass(frozen=True)
class TrajectoryPoint:
    """Single observation of an intruder bounding box."""
    t: float
    x: float  # Normalized horizontal center in [0.0, 1.0]
    y: float = 0.5
    bbox: Optional[Tuple[float, float, float, float]] = None


def _extract_x_center(obs, frame_width: Optional[float] = None) -> Tuple[float, float]:
    """Extract (timestamp, normalized_x_center) from various observation shapes.

    Accepts:
      - TrajectoryPoint
      - (t, bbox) where bbox is (x1, y1, x2, y2)
      - (t, x_center)
      - (t, x, y)
      - dict with keys ('t' or 'timestamp') and ('bbox' or 'x' or 'x_center')
    """
    if isinstance(obs, TrajectoryPoint):
        return obs.t, obs.x

    if isinstance(obs, dict):
        t = float(obs.get("t", obs.get("timestamp", 0.0)))
        if "bbox" in obs:
            x1, _, x2, _ = obs["bbox"]
            xc = (x1 + x2) / 2.0
        elif "x_center" in obs:
            xc = float(obs["x_center"])
        elif "x" in obs:
            xc = float(obs["x"])
        else:
            raise ValueError(f"Dictionary observation missing x or bbox: {obs}")
    elif isinstance(obs, (tuple, list)):
        if len(obs) == 2:
            t, val = obs
            if isinstance(val, (tuple, list)) and len(val) == 4:
                x1, _, x2, _ = val
                xc = (x1 + x2) / 2.0
            else:
                xc = float(val)
        elif len(obs) >= 3:
            t, x_val, _ = obs[0], obs[1], obs[2]
            xc = float(x_val)
        else:
            raise ValueError(f"Unrecognized observation tuple shape: {obs}")
    else:
        raise TypeError(f"Unsupported observation type: {type(obs)}")

    if frame_width is not None and frame_width > 1.0:
        if xc > 1.0:
            xc = xc / float(frame_width)

    return float(t), float(xc)


def classify_sector(
    observations: Sequence,
    config: Optional[SectorConfig] = None,
    frame_width: Optional[float] = 640.0,
) -> Tuple[str, float]:
    """Classify departure sector from horizontal drift over the configured time window.

    Returns:
        (sector_name, drift_value): where sector_name is 'left', 'center', 'right',
        or 'unknown', and drift_value is the normalized horizontal delta (x_end - x_start).
    """
    cfg = SectorConfig.from_toml() if config is None else config

    if not observations:
        return DepartureSector.UNKNOWN.value, 0.0

    effective_fw = frame_width if frame_width is not None else 640.0
    parsed: List[Tuple[float, float]] = []
    for obs in observations:
        t, x = _extract_x_center(obs, frame_width=effective_fw)
        if math.isfinite(t) and math.isfinite(x):
            parsed.append((t, x))

    if not parsed:
        return DepartureSector.UNKNOWN.value, 0.0

    # Auto-normalize if any coordinates are still in pixel space (> 1.0)
    max_x = max(p[1] for p in parsed)
    if max_x > 1.0:
        scale = max(640.0, max_x)
        parsed = [(p[0], p[1] / scale) for p in parsed]

    parsed.sort(key=lambda item: item[0])

    t0 = parsed[0][0]
    t_limit = t0 + cfg.window_s

    # Filter observations to the observation window [t0, t0 + window_s]
    windowed = [p for p in parsed if p[0] <= t_limit + 1e-6]
    if len(windowed) < cfg.min_points:
        # If not enough windowed points, take up to min_points from all available if possible
        if len(parsed) >= cfg.min_points:
            windowed = parsed[: cfg.min_points]
        elif len(parsed) >= 2:
            windowed = parsed
        else:
            # Single observation: cannot evaluate drift
            return DepartureSector.UNKNOWN.value, 0.0

    # Robust drift calculation:
    # If we have at least 4 points, compare medians of the first quarter/half vs last quarter/half
    # or use robust linear fit to suppress detection jitter
    k = max(1, len(windowed) // 3)
    start_xs = [p[1] for p in windowed[:k]]
    end_xs = [p[1] for p in windowed[-k:]]

    x_start = sum(start_xs) / len(start_xs)
    x_end = sum(end_xs) / len(end_xs)
    drift = x_end - x_start

    # Also compute linear slope over time as verification
    if len(windowed) >= 3 and (windowed[-1][0] - windowed[0][0]) > 1e-4:
        dt = windowed[-1][0] - windowed[0][0]
        # Sum of least squares slope
        t_mean = sum(p[0] for p in windowed) / len(windowed)
        x_mean = sum(p[1] for p in windowed) / len(windowed)
        denom = sum((p[0] - t_mean) ** 2 for p in windowed)
        if denom > 1e-9:
            slope = sum((p[0] - t_mean) * (p[1] - x_mean) for p in windowed) / denom
            slope_drift = slope * dt
            # Average robust start/end delta and linear projection for smooth drift estimate
            drift = 0.5 * (drift + slope_drift)

    if drift < -cfg.drift_threshold:
        return DepartureSector.LEFT.value, float(drift)
    elif drift > cfg.drift_threshold:
        return DepartureSector.RIGHT.value, float(drift)
    else:
        return DepartureSector.CENTER.value, float(drift)


class SectorTracker:
    """Streaming stateful tracker for logging entrant horizontal drift over time."""

    def __init__(
        self,
        config: Optional[SectorConfig] = None,
        frame_width: Optional[float] = 640.0,
    ):
        self.cfg = SectorConfig.from_toml() if config is None else config
        self.frame_width = frame_width
        self.points: List[TrajectoryPoint] = []
        self._finalized: bool = False
        self._cached_sector: str = DepartureSector.UNKNOWN.value
        self._cached_drift: float = 0.0

    def update(
        self,
        bbox: Tuple[float, float, float, float],
        t: float,
    ) -> str:
        """Add bounding box observation (x1, y1, x2, y2) at timestamp t."""
        if not math.isfinite(t):
            raise ValueError(f"Timestamp must be finite, got {t}")

        x1, y1, x2, y2 = bbox
        if x2 < x1 or y2 < y1:
            raise ValueError(f"Invalid bbox dimensions: {bbox}")

        fw = float(self.frame_width) if self.frame_width else 1.0
        xc = ((x1 + x2) / 2.0) / fw if fw > 1.0 else (x1 + x2) / 2.0
        yc = ((y1 + y2) / 2.0) / fw if fw > 1.0 else (y1 + y2) / 2.0

        pt = TrajectoryPoint(t=float(t), x=float(xc), y=float(yc), bbox=tuple(bbox))
        self.points.append(pt)

        # Re-evaluate sector
        sec, drift = classify_sector(self.points, config=self.cfg, frame_width=self.frame_width)
        self._cached_sector = sec
        self._cached_drift = drift

        if self.elapsed_s >= self.cfg.window_s:
            self._finalized = True

        return self._cached_sector

    @property
    def elapsed_s(self) -> float:
        if not self.points:
            return 0.0
        return max(0.0, self.points[-1].t - self.points[0].t)

    @property
    def is_finalized(self) -> bool:
        return self._finalized or (self.elapsed_s >= self.cfg.window_s and len(self.points) >= self.cfg.min_points)

    def finalize(self) -> str:
        """Manually finalize tracking and lock sector estimate."""
        sec, drift = classify_sector(self.points, config=self.cfg, frame_width=self.frame_width)
        self._cached_sector = sec
        self._cached_drift = drift
        self._finalized = True
        return self._cached_sector

    @property
    def sector(self) -> str:
        return self._cached_sector

    @property
    def drift(self) -> float:
        return self._cached_drift

    @property
    def code(self) -> str:
        return sector_code(self._cached_sector)

    def reset(self) -> None:
        self.points.clear()
        self._finalized = False
        self._cached_sector = DepartureSector.UNKNOWN.value
        self._cached_drift = 0.0
