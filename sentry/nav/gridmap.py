"""Conservative three-state room map. Unknown is never treated as navigable.

YOLO empty pixels do not prove free floor: callers supply explicit observed floor
points. Occupied evidence persists (no decay until a later validated clearing model).
"""
from collections import deque
from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import tempfile

import cv2
import numpy as np

from sentry.config import load

UNKNOWN, FREE, OCCUPIED = -1, 0, 1


@dataclass(frozen=True)
class Pose2D:
    x_m: float
    y_m: float
    yaw_rad: float

    def __post_init__(self):
        if not all(math.isfinite(v) for v in (self.x_m, self.y_m, self.yaw_rad)):
            raise ValueError("pose must be finite")


class OccupancyGrid:
    def __init__(self, resolution_m, width_m, height_m, origin=(-10.0, -10.0),
                 driven_radius_m=0.0, camera_offset=(0.0, 0.0)):
        values = (resolution_m, width_m, height_m, *origin, driven_radius_m, *camera_offset)
        if (len(origin) != 2 or len(camera_offset) != 2 or not all(math.isfinite(v) for v in values)
                or min(resolution_m, width_m, height_m) <= 0 or driven_radius_m < 0):
            raise ValueError("invalid grid geometry")
        self.resolution_m = float(resolution_m)
        self.origin = tuple(map(float, origin))
        self.driven_radius_m = float(driven_radius_m)
        self.camera_offset = tuple(map(float, camera_offset))  # lens forward/left of pose origin
        nx, ny = math.ceil(width_m / resolution_m), math.ceil(height_m / resolution_m)
        if nx * ny > 4_000_000:
            raise ValueError("map exceeds 4 million cells")
        self.cells = np.full((ny, nx), UNKNOWN, dtype=np.int8)  # cells[row y, col x]
        self.guarding_pose = None

    @classmethod
    def from_config(cls, config_path=None):
        s = (load() if config_path is None else load(config_path))["gridmap"]
        return cls(s["resolution_m"], s["width_m"], s["height_m"],
                   (s["origin_x_m"], s["origin_y_m"]), s["driven_radius_m"],
                   (s["camera_forward_m"], s["camera_left_m"]))

    def world_to_cell(self, x, y):
        if not all(math.isfinite(v) for v in (x, y)):
            raise ValueError("world coordinates must be finite")
        col, row = (math.floor(v) for v in self._grid_coordinates((x, y)))
        return (row, col) if self.in_bounds((row, col)) else None

    def _grid_coordinates(self, point):
        coords = [(point[i] - self.origin[i]) / self.resolution_m for i in (0, 1)]
        # Rotation/decimal arithmetic can put an exact boundary just below an integer.
        return tuple(float(round(v)) if abs(v - round(v)) < 1e-10 else v for v in coords)

    def in_bounds(self, cell):
        return 0 <= cell[0] < self.cells.shape[0] and 0 <= cell[1] < self.cells.shape[1]

    def cell_to_world(self, cell):
        if not self.in_bounds(cell):
            raise ValueError("cell outside map")
        row, col = cell
        return (self.origin[0] + (col + 0.5) * self.resolution_m,
                self.origin[1] + (row + 0.5) * self.resolution_m)

    def ground_to_world(self, pose, point):
        forward = point.forward_m + self.camera_offset[0]
        left = point.left_m + self.camera_offset[1]
        c, s = math.cos(pose.yaw_rad), math.sin(pose.yaw_rad)
        return pose.x_m + c * forward - s * left, pose.y_m + s * forward + c * left

    def segment_cells(self, start, end):
        """Supercover ray in cell coordinates, including both sides of corner crossings.

        Endpoints may be outside the map. Callers stop on the first outside cell.
        The work is bounded for malicious or accidentally distant coordinates.
        """
        if not all(math.isfinite(v) for v in (*start, *end)):
            raise ValueError("segment endpoints must be finite")
        x0, y0 = self._grid_coordinates(start)
        x1, y1 = self._grid_coordinates(end)
        col, row, ec, er = math.floor(x0), math.floor(y0), math.floor(x1), math.floor(y1)
        if abs(ec - col) + abs(er - row) > 4 * sum(self.cells.shape):
            raise ValueError("segment too long for this map")
        dx, dy = x1 - x0, y1 - y0
        sx, sy = (1 if dx > 0 else -1), (1 if dy > 0 else -1)
        tx = ((col + 1 - x0) / dx if dx > 0 else (col - x0) / dx) if dx else math.inf
        ty = ((row + 1 - y0) / dy if dy > 0 else (row - y0) / dy) if dy else math.inf
        dtx, dty = (1 / abs(dx) if dx else math.inf), (1 / abs(dy) if dy else math.inf)
        def touching(x, y):
            cols = [math.floor(x)] + ([math.floor(x) - 1] if x.is_integer() else [])
            rows = [math.floor(y)] + ([math.floor(y) - 1] if y.is_integer() else [])
            return [(rr, cc) for rr in rows for cc in cols]

        def boundary_neighbours(rr, cc):
            if dx == 0 and x0.is_integer():
                yield rr, cc - 1
            if dy == 0 and y0.is_integer():
                yield rr - 1, cc

        yield row, col
        yield from touching(x0, y0)[1:]
        yield from boundary_neighbours(row, col)
        while min(tx, ty) < 1 - 1e-12:
            if math.isclose(tx, ty, rel_tol=0, abs_tol=1e-12):
                yield row, col + sx
                yield row + sy, col
                col, row, tx, ty = col + sx, row + sy, tx + dtx, ty + dty
            elif tx < ty:
                col, tx = col + sx, tx + dtx
            else:
                row, ty = row + sy, ty + dty
            yield row, col
            yield from boundary_neighbours(row, col)
        yield from touching(x1, y1)[1:]
        yield er, ec

    def update(self, pose, obstacles=(), seen_floor=()):
        """Both sequences contain GroundPoint in the rectified camera ground frame.

        Insert all occupied endpoints BEFORE floor rays. An obstacle ray itself
        never clears floor. Only independently confirmed seen_floor rays do.
        """
        robot_cell = self.world_to_cell(pose.x_m, pose.y_m)
        if robot_cell is None:
            raise ValueError("robot outside map; choose a larger/configured extent")
        obstacle_world = [self.ground_to_world(pose, p) for p in obstacles]
        floor_world = [self.ground_to_world(pose, p) for p in seen_floor]
        for xy in obstacle_world:
            cell = self.world_to_cell(*xy)
            if cell is not None:
                self.cells[cell] = OCCUPIED
        r = math.ceil(self.driven_radius_m / self.resolution_m)
        row, col = robot_cell
        for rr in range(max(0, row - r), min(self.cells.shape[0], row + r + 1)):
            for cc in range(max(0, col - r), min(self.cells.shape[1], col + r + 1)):
                x, y = self.cell_to_world((rr, cc))
                if ((rr, cc) == robot_cell or math.hypot(x - pose.x_m, y - pose.y_m) <= self.driven_radius_m):
                    if self.cells[rr, cc] != OCCUPIED:
                        self.cells[rr, cc] = FREE
        c, s = math.cos(pose.yaw_rad), math.sin(pose.yaw_rad)
        lens = (pose.x_m + c * self.camera_offset[0] - s * self.camera_offset[1],
                pose.y_m + s * self.camera_offset[0] + c * self.camera_offset[1])
        for xy in floor_world:
            for cell in self.segment_cells(lens, xy):
                if not self.in_bounds(cell) or self.cells[cell] == OCCUPIED:
                    break
                self.cells[cell] = FREE

    def line_of_sight(self, start, end, allow_occupied_end=False):
        a, b = self.world_to_cell(*start), self.world_to_cell(*end)
        if a is None or b is None:
            return False
        for cell in self.segment_cells(start, end):
            if not self.in_bounds(cell):
                return False
            state = self.cells[cell]
            if state != FREE and not (cell == b and state == OCCUPIED and allow_occupied_end):
                return False
        return True

    def clearance_m(self):
        """Conservative clearance to unknown, occupied or outside map, at cell centres."""
        mask = np.pad((self.cells == FREE).astype(np.uint8), 1)
        distances = cv2.distanceTransform(mask, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)[1:-1, 1:-1]
        return np.maximum(0, distances * self.resolution_m - self.resolution_m / math.sqrt(2))

    def reachable(self, pose, radius_m):
        if not math.isfinite(radius_m) or radius_m < 0:
            raise ValueError("invalid robot radius")
        clearance = self.clearance_m()
        allowed = (self.cells == FREE) & (clearance >= radius_m)
        start = self.world_to_cell(pose.x_m, pose.y_m)
        reached = np.zeros(self.cells.shape, dtype=bool)
        if start is None or not allowed[start]:
            return reached
        centre = self.cell_to_world(start)
        offset = math.hypot(centre[0] - pose.x_m, centre[1] - pose.y_m)
        if clearance[start] < radius_m + offset:
            return reached
        reached[start] = True
        todo = deque([start])
        while todo:
            row, col = todo.popleft()
            for q in ((row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)):
                if self.in_bounds(q) and allowed[q] and not reached[q]:
                    reached[q] = True
                    todo.append(q)
        return reached

    def save(self, path, guarding_pose=None):
        """Atomic NPZ, JSON metadata, no pickle. Can be loaded by the later search planner."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        guard = guarding_pose if guarding_pose is not None else self.guarding_pose
        meta = dict(version=1, resolution_m=self.resolution_m, origin=self.origin,
                    driven_radius_m=self.driven_radius_m, camera_offset=self.camera_offset,
                    guarding_pose=asdict(guard) if guard is not None else None,
                    coordinates="x forward at yaw=0; y left; yaw CCW; metres/radians")
        fd, temp_path = tempfile.mkstemp(dir=path.parent, suffix=".npz")
        try:
            with os.fdopen(fd, "wb") as f:
                np.savez_compressed(f, cells=self.cells, metadata=json.dumps(meta, allow_nan=False))
            os.replace(temp_path, path)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    @classmethod
    def load(cls, path):
        with np.load(path, allow_pickle=False) as saved:
            cells = saved["cells"]
            meta = json.loads(str(saved["metadata"]))
        if (meta["version"] != 1 or cells.ndim != 2 or not cells.size or cells.size > 4_000_000
                or not np.isin(cells, [UNKNOWN, FREE, OCCUPIED]).all()):
            raise ValueError("invalid saved map")
        res = meta["resolution_m"]
        grid = cls(res, cells.shape[1] * res, cells.shape[0] * res,
                   meta["origin"], meta["driven_radius_m"], meta["camera_offset"])
        grid.cells = cells.astype(np.int8, copy=True)
        if meta["guarding_pose"] is not None:
            grid.guarding_pose = Pose2D(**meta["guarding_pose"])
        return grid
