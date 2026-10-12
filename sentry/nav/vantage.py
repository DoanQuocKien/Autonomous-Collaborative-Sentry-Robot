"""Known-free, reachable camera stops with 1.5-3 m LOS to a world-frame door."""
from dataclasses import dataclass
import math

import cv2
import numpy as np

from sentry.config import load
from .gridmap import OCCUPIED, Pose2D


@dataclass(frozen=True)
class VantagePoint:
    x_m: float
    y_m: float
    yaw_rad: float           # points at door (camera placement); deployment can face room centre separately
    door_distance_m: float
    boundary_distance_m: float
    score: float            # larger is better

    @property
    def pose(self):
        return Pose2D(self.x_m, self.y_m, self.yaw_rad)


class VantageSelector:
    def __init__(self, min_distance_m=1.5, max_distance_m=3.0, robot_radius_m=0.15,
                 boundary_weight=1.0, distance_weight=0.2):
        vals = (min_distance_m, max_distance_m, robot_radius_m, boundary_weight, distance_weight)
        if (not all(math.isfinite(v) for v in vals) or not 0 < min_distance_m <= max_distance_m
                or min(robot_radius_m, boundary_weight, distance_weight) < 0):
            raise ValueError("invalid vantage parameters")
        self.min_distance_m, self.max_distance_m = min_distance_m, max_distance_m
        self.robot_radius_m = robot_radius_m
        self.boundary_weight, self.distance_weight = boundary_weight, distance_weight

    @classmethod
    def from_config(cls, config_path=None):
        config = load() if config_path is None else load(config_path)
        t, s = config["thresholds"], config["vantage"]
        return cls(t["entrance_min_m"], t["entrance_max_m"], s["robot_radius_m"],
                   s["boundary_weight"], s["distance_weight"])

    def rank(self, grid, door_xy, robot_pose):
        """Unknown blocks LOS and travel. Only an occupied door endpoint is exempt.

        World door location must come from KR/measurements, not a bearing alone.
        Boundary preference uses observed occupied cells, never unknown/map edges.
        """
        if len(door_xy) != 2 or not all(math.isfinite(v) for v in door_xy):
            raise ValueError("finite door world coordinates required")
        if grid.world_to_cell(*door_xy) is None:
            return ()
        reachable = grid.reachable(robot_pose, self.robot_radius_m)
        if np.any(grid.cells == OCCUPIED):
            boundary = cv2.distanceTransform((grid.cells != OCCUPIED).astype(np.uint8),
                                            cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
            boundary = np.maximum(0, boundary * grid.resolution_m - grid.resolution_m / math.sqrt(2))
        else:
            boundary = np.full(grid.cells.shape, math.hypot(*grid.cells.shape) * grid.resolution_m)
        target = (self.min_distance_m + self.max_distance_m) / 2
        choices = []
        for row, col in np.argwhere(reachable):
            x, y = grid.cell_to_world((row, col))
            distance = math.hypot(door_xy[0] - x, door_xy[1] - y)
            if not self.min_distance_m <= distance <= self.max_distance_m:
                continue
            if not grid.line_of_sight((x, y), door_xy, allow_occupied_end=True):
                continue
            near = float(boundary[row, col])
            score = -self.boundary_weight * near - self.distance_weight * abs(distance - target)
            choices.append(VantagePoint(x, y, math.atan2(door_xy[1] - y, door_xy[0] - x),
                                        distance, near, score))
        return tuple(sorted(choices, key=lambda p: (-p.score, p.x_m, p.y_m)))

    def select(self, grid, door_xy, robot_pose):
        ranked = self.rank(grid, door_xy, robot_pose)
        return ranked[0] if ranked else None
