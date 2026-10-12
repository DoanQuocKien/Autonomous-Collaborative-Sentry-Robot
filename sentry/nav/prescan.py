"""Wire HNHL modules together; caller supplies KR pose and confirmed seen floor."""
from dataclasses import dataclass

from sentry.perception.obstacle import ObstacleResult
from .vantage import VantagePoint


@dataclass(frozen=True)
class PrescanResult:
    observations: ObstacleResult
    vantage: VantagePoint | None


class PreScanner:
    def __init__(self, detector, grid, selector, door_xy=None):
        self.detector, self.grid, self.selector = detector, grid, selector
        self.door_xy = door_xy

    def __call__(self, frame_bgr, t, pose, seen_floor=()):
        observed = self.detector(frame_bgr, t)
        self.grid.update(pose, observed.ground_points, seen_floor)
        vantage = (self.selector.select(self.grid, self.door_xy, pose)
                   if self.door_xy is not None else None)
        self.grid.guarding_pose = vantage.pose if vantage is not None else None
        return PrescanResult(observed, vantage)
