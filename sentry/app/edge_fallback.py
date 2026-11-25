"""Laptop-side Stage A fallback coordinator bridging `jetson.obstacle_layer.FallbackSwitch`
with `sentry.nav.explore.Explorer`.

When the on-robot obstacle layer is healthy and enabled, its `(v, w)` command is
forwarded; when switched off, errored, or silent past `timeout_s` (<= 1.0 s),
control falls back to the laptop `Explorer` + `ObstacleDetector` path.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional, Tuple

from jetson.obstacle_layer import FallbackSwitch
from sentry.nav.explore import Command as ExploreCommand, ExploreSettings, Explorer, legal


class EdgeFallbackController:
    """Coordinate on-robot obstacle commands with the laptop `Explorer` backup."""

    def __init__(
        self,
        explorer: Optional[Explorer] = None,
        switch: Optional[FallbackSwitch] = None,
        *,
        timeout_s: float = 0.5,
        recovery_frames: int = 3,
        edge_enabled: bool = True,
    ):
        self.explorer = Explorer() if explorer is None else explorer
        self.switch = (
            FallbackSwitch(timeout_s=timeout_s, recovery_frames=recovery_frames, enabled=edge_enabled)
            if switch is None
            else switch
        )

    def set_edge_enabled(self, enabled: bool, now: float) -> None:
        self.switch.set_edge_enabled(enabled, now)

    def on_edge_result(self, edge_result: Optional[Dict[str, Any]], now: float) -> None:
        self.switch.on_edge_result(edge_result, now)

    def on_edge_error(self, now: float, reason: str = "edge_error") -> None:
        self.switch.on_edge_error(now, reason=reason)

    def step(
        self,
        now: float,
        dt: float,
        pose: Tuple[float, float, float],
        *,
        laptop_obs: Any = None,
        edge_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Advance both edge tracking and laptop backup, returning a legal `(v, w)` decision."""
        if not math.isfinite(dt) or dt < 0.0:
            raise ValueError(f"dt must be finite and >= 0, got {dt!r}")

        if edge_result is not None:
            self.switch.on_edge_result(edge_result, now)

        # Always keep the laptop Explorer synchronized on available observations so a
        # mid-run fallback takes over seamlessly with up-to-date turn/clear hysteresis.
        laptop_cmd = self.explorer.step(laptop_obs, pose, dt)
        laptop_dict = {
            "v": laptop_cmd.v,
            "w": laptop_cmd.w,
            "state": laptop_cmd.state,
            "reason": laptop_cmd.reason,
        }
        chosen = self.switch.select(now, laptop_result=laptop_dict)
        if not legal(ExploreCommand(chosen["v"], chosen["w"], chosen["state"], chosen["reason"]), self.explorer.s):
            chosen["v"] = 0.0
            chosen["w"] = 0.0
            chosen["state"] = "STOP"
            chosen["reason"] = "illegal_command"
        return chosen
