"""Target ground-speed hold detector with robot motion compensation (Week 5, kouun-rokku).

Tracks target ground position in the world coordinate frame by compensating for robot pose
(x, y, theta) and angular velocity (yaw). This guarantees that robot rotation alone (e.g.
while turning, centering a bounding box, or yawing in place) is never mistaken for target motion.

Specification (§4.5) & Implementation Plan (§4.3):
- Target ground speed v_target < 0.1 m/s for > 2.0 s -> HOLD (emits TARGET_STATIONARY).
- Target ground speed v_target > 0.2 m/s -> exit HOLD (emits TARGET_MOVING, hysteresis).
- Pure logic (no hardware or GPU dependency), runs in all test tiers.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math
from typing import Any, Deque, Optional, Tuple, Union

from sentry.config import DEFAULT_PATH, load


@dataclass(frozen=True)
class HoldConfig:
    """Tunable thresholds for hold detection and hysteresis."""
    speed_threshold_mps: float = 0.1          # Entry threshold: target stationary below this
    dwell_time_s: float = 2.0                 # Target must remain stationary for > this duration
    exit_speed_mps: float = 0.2               # Exit threshold: hysteresis prevents flickering
    window_s: float = 0.5                     # Sliding window for robust linear-regression velocity
    min_samples: int = 5                      # Minimum observations required in window
    min_window_span_s: float = 0.2            # Minimum time span required in window to avoid jitter
    max_observation_gap_s: float = 1.0        # Reset velocity history and hold state if gap exceeds this

    def __post_init__(self):
        if not (0.0 < self.speed_threshold_mps < self.exit_speed_mps):
            raise ValueError("speed_threshold_mps must be positive and strictly less than exit_speed_mps")
        if not (self.dwell_time_s > 0.0 and math.isfinite(self.dwell_time_s)):
            raise ValueError("dwell_time_s must be positive and finite")
        if not (self.window_s > 0.0 and math.isfinite(self.window_s)):
            raise ValueError("window_s must be positive and finite")
        if self.min_samples < 2:
            raise ValueError("min_samples must be at least 2")
        if not (self.min_window_span_s > 0.0 and math.isfinite(self.min_window_span_s)):
            raise ValueError("min_window_span_s must be positive and finite")

    @classmethod
    def from_toml(cls, config_path=DEFAULT_PATH) -> HoldConfig:
        raw = load(config_path)
        h = raw.get("hold", {})
        t = raw.get("thresholds", {})
        return cls(
            speed_threshold_mps=float(t.get("stationary_speed_mps", 0.1)),
            dwell_time_s=float(t.get("stationary_time_s", 2.0)),
            exit_speed_mps=float(t.get("stationary_exit_speed_mps", 0.2)),
            window_s=float(h.get("window_s", 0.5)),
            min_samples=int(h.get("min_samples", 5)),
            min_window_span_s=float(h.get("min_window_span_s", 0.2)),
            max_observation_gap_s=float(h.get("max_observation_gap_s", 1.0)),
        )


@dataclass(frozen=True)
class HoldState:
    """Snapshot of target state and hold status at timestamp t."""
    t: float
    target_world_x: float
    target_world_y: float
    speed_mps: Optional[float]
    vx_mps: Optional[float]
    vy_mps: Optional[float]
    in_hold: bool
    event: Optional[str]                      # 'TARGET_STATIONARY', 'TARGET_MOVING', 'TARGET_LOST', or None
    dwell_progress_s: float                   # How long current stationary period has lasted


def local_to_world_coords(
    robot_pose: Union[Tuple[float, float, float], Any],
    forward_m: float,
    left_m: float,
) -> Tuple[float, float]:
    """Transform target coordinates from robot frame (forward, left) to world (x, y).

    `robot_pose` can be a 3-tuple (x, y, theta) or any object with attributes
    (x, y, theta) or (x_m, y_m, yaw_rad) like sentry.nav.localization.RobotPose.
    """
    if hasattr(robot_pose, "x_m") and robot_pose.x_m is not None:
        rx, ry, rtheta = float(robot_pose.x_m), float(robot_pose.y_m), float(robot_pose.yaw_rad)
    elif hasattr(robot_pose, "x"):
        rx, ry, rtheta = float(robot_pose.x), float(robot_pose.y), float(robot_pose.theta)
    else:
        rx, ry, rtheta = float(robot_pose[0]), float(robot_pose[1]), float(robot_pose[2])

    if not all(math.isfinite(v) for v in (rx, ry, rtheta, forward_m, left_m)):
        raise ValueError("robot pose and target local coordinates must be finite")

    cos_th = math.cos(rtheta)
    sin_th = math.sin(rtheta)
    wx = rx + forward_m * cos_th - left_m * sin_th
    wy = ry + forward_m * sin_th + left_m * cos_th
    return wx, wy


class HoldDetector:
    """Detects when an intruder becomes stationary in the world frame and triggers HOLD.

    Employs world coordinate projection to decouple robot motion/rotation from intruder motion.
    Tracks speed using linear regression over a short sliding window, then enforces a 2.0 s dwell
    time before transitioning to HOLD, and requires 0.2 m/s to resume pursuit.
    """

    def __init__(self, config: Optional[HoldConfig] = None):
        self.cfg = config or HoldConfig()
        self._history: Deque[Tuple[float, float, float]] = deque()
        self._in_hold: bool = False
        self._stationary_start_t: Optional[float] = None
        self._last_t: Optional[float] = None

    @property
    def in_hold(self) -> bool:
        """True if the target is currently considered in HOLD state."""
        return self._in_hold

    def reset(self) -> None:
        """Reset internal filter history and hold state (e.g. when changing targets or new stream)."""
        self._history.clear()
        self._in_hold = False
        self._stationary_start_t = None
        self._last_t = None

    def update_world(self, t: float, wx: float, wy: float) -> HoldState:
        """Update detector directly with target world coordinates (meters) at time t (seconds)."""
        if not all(math.isfinite(v) for v in (t, wx, wy)):
            raise ValueError("timestamp and world coordinates must be finite")
        if self._last_t is not None and t <= self._last_t:
            raise ValueError(f"timestamp t={t} must be strictly greater than last_t={self._last_t}")

        # If a large frame gap occurred, reset velocity history and release hold if target left view
        had_hold = self._in_hold
        gap_reset = False
        if self._last_t is not None and (t - self._last_t) > self.cfg.max_observation_gap_s:
            self._history.clear()
            self._stationary_start_t = None
            self._in_hold = False
            gap_reset = True

        self._last_t = t
        self._history.append((t, wx, wy))

        # Evict samples outside sliding window
        cutoff = t - self.cfg.window_s
        while len(self._history) > 1 and self._history[0][0] < cutoff:
            self._history.popleft()

        # Compute ground velocity via linear regression
        vx, vy, speed = self._estimate_velocity()

        # Evaluate dwell time & hysteresis
        event = None
        dwell_progress = 0.0

        if gap_reset and had_hold:
            event = "TARGET_LOST"

        if not self._in_hold:
            if speed is not None and speed < self.cfg.speed_threshold_mps:
                if self._stationary_start_t is None:
                    self._stationary_start_t = t
                dwell_progress = t - self._stationary_start_t
                if dwell_progress >= self.cfg.dwell_time_s:
                    self._in_hold = True
                    event = "TARGET_STATIONARY"
            else:
                self._stationary_start_t = None
                dwell_progress = 0.0
        else:
            # Currently in HOLD: exit only if speed is valid and exceeds exit threshold (hysteresis)
            if speed is not None and speed > self.cfg.exit_speed_mps:
                self._in_hold = False
                self._stationary_start_t = None
                dwell_progress = 0.0
                event = "TARGET_MOVING"
            else:
                # Retain hold during hysteresis band [speed_threshold_mps, exit_speed_mps] or while pending
                dwell_progress = self.cfg.dwell_time_s

        return HoldState(
            t=t,
            target_world_x=wx,
            target_world_y=wy,
            speed_mps=speed,
            vx_mps=vx,
            vy_mps=vy,
            in_hold=self._in_hold,
            event=event,
            dwell_progress_s=dwell_progress,
        )

    def update(
        self,
        t: float,
        robot_pose: Union[Tuple[float, float, float], Any],
        target_local_pos: Union[Tuple[float, float], Any],
    ) -> HoldState:
        """Update detector using robot pose and target local position in robot frame.

        `target_local_pos` can be:
        - (forward_m, left_m) tuple
        - Any object with forward_m and left_m attributes (e.g. GroundPoint)
        """
        if hasattr(target_local_pos, "forward_m") and hasattr(target_local_pos, "left_m"):
            fwd, left = float(target_local_pos.forward_m), float(target_local_pos.left_m)
        else:
            fwd, left = float(target_local_pos[0]), float(target_local_pos[1])

        wx, wy = local_to_world_coords(robot_pose, fwd, left)
        return self.update_world(t, wx, wy)

    def _estimate_velocity(self) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """Estimate (vx, vy, speed) in m/s using linear regression over the window.

        Returns (None, None, None) if sample count or window time span is insufficient.
        """
        n = len(self._history)
        if n < self.cfg.min_samples:
            return None, None, None

        span = self._history[-1][0] - self._history[0][0]
        if span < self.cfg.min_window_span_s:
            return None, None, None

        sum_t = sum_x = sum_y = 0.0
        for ti, xi, yi in self._history:
            sum_t += ti
            sum_x += xi
            sum_y += yi
        mean_t = sum_t / n
        mean_x = sum_x / n
        mean_y = sum_y / n

        denom = 0.0
        cov_tx = 0.0
        cov_ty = 0.0
        for ti, xi, yi in self._history:
            dt = ti - mean_t
            denom += dt * dt
            cov_tx += dt * (xi - mean_x)
            cov_ty += dt * (yi - mean_y)

        if denom < 1e-9:
            # Fallback to simple finite difference across endpoints
            t0, x0, y0 = self._history[0]
            t1, x1, y1 = self._history[-1]
            dt = t1 - t0
            if dt > 1e-6:
                vx = (x1 - x0) / dt
                vy = (y1 - y0) / dt
            else:
                vx = vy = 0.0
        else:
            vx = cov_tx / denom
            vy = cov_ty / denom

        speed = math.hypot(vx, vy)
        return vx, vy, speed
