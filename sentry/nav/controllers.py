"""Pursuit and Standoff Hold Controllers (Week 5, DoanQuocKien & kouun-rokku).

Specification (§4.5) & Implementation Plan (§4.3):
- PursuitController:
  * Proportional-Derivative (PD) control maintaining 1.2 m standoff distance from target
    and centering target bounding box / bearing in camera FOV.
  * Obstacle Override: when d_obs < 0.5 m, applies repulsive yaw deflection offset to bypass
    obstacle without losing target line-of-sight.
- HoldController:
  * Zero translation (v = 0.0 strictly) and yaw-only PD maintaining target bbox centering.
  * No orbiting (which would place target 90 deg off-axis, dropping outside camera FOV).
  * Centers bbox within +/- 10% of frame width within 1.5 s.
- InterceptionController:
  * Combines PursuitController, HoldController, and HoldDetector for closed-loop Phase 3 execution.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Optional, Tuple, Union

from sentry.config import DEFAULT_PATH, load
from sentry.nav.hold_detector import HoldConfig, HoldDetector, HoldState


@dataclass(frozen=True)
class PursuitConfig:
    """Tunable parameters for pursuit and obstacle avoidance."""
    target_distance_m: float = 1.2             # Nominal standoff distance in meters
    distance_tolerance_m: float = 0.2          # Acceptable band: 1.2 +/- 0.2 m
    kp_distance: float = 0.8                   # Proportional gain on distance error
    kd_distance: float = 0.1                   # Derivative gain on distance error
    kp_yaw: float = 1.5                        # Proportional gain on centering error (rad or norm)
    kd_yaw: float = 0.2                        # Derivative gain on centering error
    v_max: float = 0.55                        # Maximum forward linear command
    v_min_reverse: float = -0.3                # Maximum reverse linear command
    w_max: float = 1.0                         # Maximum angular velocity command
    min_pwm: float = 0.12                      # Motor dead-zone threshold
    max_speed_cap: float = 0.3                 # Hardware cap on robot
    obstacle_threshold_m: float = 0.5          # Override active when obstacle closer than this
    obstacle_critical_m: float = 0.35          # Forward speed cut when obstacle closer than this
    obstacle_avoid_w: float = 0.45             # Yaw deflection offset when obstacle detected
    center_tolerance_norm: float = 0.10        # Centering threshold (+/- 10% of frame width)

    @property
    def dead_zone(self) -> float:
        """Normalized command dead-zone: below this motors only whine."""
        return self.min_pwm / self.max_speed_cap if self.max_speed_cap > 0 else 0.4

    @classmethod
    def from_toml(cls, config_path=DEFAULT_PATH) -> PursuitConfig:
        raw = load(config_path)
        p = raw.get("pursuit", {})
        t = raw.get("thresholds", {})
        return cls(
            target_distance_m=float(p.get("target_distance_m", t.get("standoff_m", 1.2))),
            distance_tolerance_m=float(p.get("distance_tolerance_m", 0.2)),
            kp_distance=float(p.get("kp_distance", 0.8)),
            kd_distance=float(p.get("kd_distance", 0.1)),
            kp_yaw=float(p.get("kp_yaw", 1.5)),
            kd_yaw=float(p.get("kd_yaw", 0.2)),
            v_max=float(p.get("v_max", 0.55)),
            v_min_reverse=float(p.get("v_min_reverse", -0.3)),
            w_max=float(p.get("w_max", 1.0)),
            obstacle_threshold_m=float(p.get("obstacle_threshold_m", t.get("obstacle_pursuit_m", 0.5))),
            obstacle_critical_m=float(p.get("obstacle_critical_m", 0.35)),
            obstacle_avoid_w=float(p.get("obstacle_avoid_w", 0.45)),
            center_tolerance_norm=float(p.get("center_tolerance_norm", 0.10)),
        )


@dataclass(frozen=True)
class HoldBehaviorConfig:
    """Tunable parameters for standoff hold behavior."""
    kp_yaw: float = 1.5                        # Yaw centering proportional gain
    kd_yaw: float = 0.2                        # Yaw centering derivative gain
    w_max: float = 0.8                         # Max angular speed during hold
    center_tolerance_norm: float = 0.10        # Centering requirement: within +/- 10% width
    max_recenter_time_s: float = 1.5           # Required to re-center within 1.5 s

    @classmethod
    def from_toml(cls, config_path=DEFAULT_PATH) -> HoldBehaviorConfig:
        raw = load(config_path)
        h = raw.get("hold", {})
        return cls(
            kp_yaw=float(h.get("kp_yaw", 1.5)),
            kd_yaw=float(h.get("kd_yaw", 0.2)),
            w_max=float(h.get("w_max", 0.8)),
            center_tolerance_norm=float(h.get("center_tolerance_norm", 0.10)),
            max_recenter_time_s=float(h.get("max_recenter_time_s", 1.5)),
        )


@dataclass(frozen=True)
class ControllerOutput:
    """Motor commands and telemetry emitted by controllers."""
    t: float
    v: float                                   # Linear command in [-1, 1]
    w: float                                   # Angular command in [-1, 1] (positive = left)
    mode: str                                  # 'PURSUIT' or 'HOLD'
    distance_error_m: float
    yaw_error: float
    is_centered: bool
    obstacle_override: bool
    event: Optional[str] = None                # 'TARGET_STATIONARY', 'TARGET_MOVING', or None


class PursuitController:
    """PD controller for target pursuit maintaining 1.2 m standoff and centering."""

    def __init__(self, config: Optional[PursuitConfig] = None):
        self.cfg = config or PursuitConfig()
        self._prev_t: Optional[float] = None
        self._prev_dist_err: Optional[float] = None
        self._prev_yaw_err: Optional[float] = None

    def reset(self) -> None:
        self._prev_t = None
        self._prev_dist_err = None
        self._prev_yaw_err = None

    def compute(
        self,
        t: float,
        target_dist_m: float,
        yaw_err: float,
        obstacle_dist_m: Optional[float] = None,
        obstacle_bearing_rad: float = 0.0,
    ) -> Tuple[float, float, bool, bool]:
        """Compute (v, w, is_centered, obstacle_active).

        `target_dist_m`: measured ground distance to intruder (meters).
        `yaw_err`: centering error (positive if intruder is to the LEFT, requiring left turn w > 0).
                   Can be bearing in radians or normalized image offset (u_center - u_target)/(W/2).
        `obstacle_dist_m`: distance to closest obstacle in forward sector, or None.
        `obstacle_bearing_rad`: bearing of the obstacle (left positive).
        """
        if not math.isfinite(t):
            raise ValueError("timestamp must be finite")
        if self._prev_t is not None and t <= self._prev_t:
            raise ValueError(f"timestamp t={t} must be strictly greater than prev_t={self._prev_t}")

        dt = (t - self._prev_t) if self._prev_t is not None else 0.0
        self._prev_t = t

        # Distance error: positive means target is farther than target_distance_m -> move forward
        dist_err = target_dist_m - self.cfg.target_distance_m
        d_dist = (dist_err - self._prev_dist_err) / dt if (dt > 1e-6 and self._prev_dist_err is not None) else 0.0
        self._prev_dist_err = dist_err

        # Centering error derivative
        d_yaw = (yaw_err - self._prev_yaw_err) / dt if (dt > 1e-6 and self._prev_yaw_err is not None) else 0.0
        self._prev_yaw_err = yaw_err

        # PD control
        v = self.cfg.kp_distance * dist_err + self.cfg.kd_distance * d_dist
        w = self.cfg.kp_yaw * yaw_err + self.cfg.kd_yaw * d_yaw

        # Obstacle override
        obstacle_active = False
        if obstacle_dist_m is not None and obstacle_dist_m < self.cfg.obstacle_threshold_m:
            obstacle_active = True
            # Add deflection offset away from obstacle
            # If obstacle is to the left (bearing > 0), turn right (w -= avoid_w); else turn left
            avoid_dir = -1.0 if obstacle_bearing_rad >= 0 else +1.0
            w += avoid_dir * self.cfg.obstacle_avoid_w

            # If critically close, suppress forward velocity to prevent collision
            if obstacle_dist_m < self.cfg.obstacle_critical_m:
                v = min(0.0, v)

        # Saturate outputs within configured caps
        v = max(self.cfg.v_min_reverse, min(self.cfg.v_max, v))
        w = max(-self.cfg.w_max, min(self.cfg.w_max, w))

        is_centered = abs(yaw_err) <= self.cfg.center_tolerance_norm
        return v, w, is_centered, obstacle_active


class HoldController:
    """Standoff hold controller: strictly zero translation, yaw-only PD recentering."""

    def __init__(self, config: Optional[HoldBehaviorConfig] = None):
        self.cfg = config or HoldBehaviorConfig()
        self._prev_t: Optional[float] = None
        self._prev_yaw_err: Optional[float] = None
        self._entered_t: Optional[float] = None
        self._first_centered_t: Optional[float] = None

    def reset(self) -> None:
        self._prev_t = None
        self._prev_yaw_err = None
        self._entered_t = None
        self._first_centered_t = None

    def compute(self, t: float, yaw_err: float) -> Tuple[float, float, bool]:
        """Compute (v, w, is_centered).

        v is ALWAYS 0.0 (no translation / orbiting).
        w centers the target bbox using yaw-only PD.
        """
        if not math.isfinite(t):
            raise ValueError("timestamp must be finite")
        if self._prev_t is not None and t <= self._prev_t:
            raise ValueError(f"timestamp t={t} must be strictly greater than prev_t={self._prev_t}")

        if self._entered_t is None:
            self._entered_t = t

        dt = (t - self._prev_t) if self._prev_t is not None else 0.0
        self._prev_t = t

        d_yaw = (yaw_err - self._prev_yaw_err) / dt if (dt > 1e-6 and self._prev_yaw_err is not None) else 0.0
        self._prev_yaw_err = yaw_err

        # Translation strictly zero
        v = 0.0

        # Yaw PD control
        w = self.cfg.kp_yaw * yaw_err + self.cfg.kd_yaw * d_yaw
        w = max(-self.cfg.w_max, min(self.cfg.w_max, w))

        is_centered = abs(yaw_err) <= self.cfg.center_tolerance_norm
        if is_centered and self._first_centered_t is None:
            self._first_centered_t = t

        return v, w, is_centered


class InterceptionController:
    """Complete Phase 3 closed-loop pursuit, hold detector, and standoff hold controller."""

    def __init__(
        self,
        pursuit_cfg: Optional[PursuitConfig] = None,
        hold_behavior_cfg: Optional[HoldBehaviorConfig] = None,
        hold_detector_cfg: Optional[HoldConfig] = None,
    ):
        self.pursuit = PursuitController(pursuit_cfg)
        self.hold = HoldController(hold_behavior_cfg)
        self.detector = HoldDetector(hold_detector_cfg)
        self._mode = "PURSUIT"

    @property
    def mode(self) -> str:
        return self._mode

    def reset(self) -> None:
        self.pursuit.reset()
        self.hold.reset()
        self.detector.reset()
        self._mode = "PURSUIT"

    def step(
        self,
        t: float,
        robot_pose: Union[Tuple[float, float, float], Any],
        target_local_pos: Union[Tuple[float, float], Any],
        yaw_err: float,
        obstacle_dist_m: Optional[float] = None,
        obstacle_bearing_rad: float = 0.0,
    ) -> ControllerOutput:
        """Execute one control step at timestamp t."""
        # Update ground-speed hold detector with world compensation
        hstate = self.detector.update(t, robot_pose, target_local_pos)

        # Handle mode switching based on hold detector state
        event = hstate.event
        if event == "TARGET_STATIONARY":
            self._mode = "HOLD"
            self.hold.reset()
        elif event == "TARGET_MOVING":
            self._mode = "PURSUE"
            self.pursuit.reset()

        if hasattr(target_local_pos, "distance_m"):
            dist_m = float(target_local_pos.distance_m)
        elif hasattr(target_local_pos, "forward_m"):
            dist_m = math.hypot(float(target_local_pos.forward_m), float(target_local_pos.left_m))
        else:
            dist_m = math.hypot(float(target_local_pos[0]), float(target_local_pos[1]))

        dist_err = dist_m - self.pursuit.cfg.target_distance_m

        if self._mode == "HOLD":
            v, w, is_centered = self.hold.compute(t, yaw_err)
            obs_active = False
        else:
            v, w, is_centered, obs_active = self.pursuit.compute(
                t, dist_m, yaw_err, obstacle_dist_m, obstacle_bearing_rad
            )

        return ControllerOutput(
            t=t,
            v=v,
            w=w,
            mode=self._mode,
            distance_error_m=dist_err,
            yaw_error=yaw_err,
            is_centered=is_centered,
            obstacle_override=obs_active,
            event=event,
        )
