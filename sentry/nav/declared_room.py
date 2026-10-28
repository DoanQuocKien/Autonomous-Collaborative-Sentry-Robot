"""Operator-declared room map for the Phase 1 deployment (decision 2026-10-29, option A).

WHY: `VantageSelector` accepts a sweet spot only when every cell on the line to the door is KNOWN free, and the live map marks floor as free only in a 0.12 m disk around the cells
the robot drove over (plus rays of "seen floor" points that the caller must supply: nothing supplies them live). After a normal exploration run there is no candidate. So the room
is DECLARED instead, from tape measurements in the start frame (robot at (0, 0), facing +x, y to its left): the cleared box is FREE, the wall segments and the door are OCCUPIED,
everything else stays UNKNOWN. The obstacle detector still adds furniture during the run (OccupancyGrid.update). The report must say the map is declared, not explored.

declared_grid()        box, walls, door -> OccupancyGrid
straight_path_clear()  the go-to controller drives a straight line: every sampled cell must be FREE with clearance >= the robot radius
door_cell_centre()     the door snapped to its cell centre (used by select_reachable)
select_reachable()     the best ranked sweet spot that the robot can reach in a straight line from its pose (None when there is none)
"""
import math

import numpy as np

from .gridmap import FREE, OCCUPIED, OccupancyGrid


def _wall_cells(g, a, b):
    """The cells a wall segment passes through, ONE cell thick: sampled every quarter cell (a supercover ray marks two cells when the wall lies exactly on a grid line, and a
    second wall cell in front of the door would block every line of sight to it)."""
    n = max(1, int(math.ceil(math.hypot(b[0] - a[0], b[1] - a[1]) / (g.resolution_m / 4.0))))
    cells = set()
    for i in range(n + 1):
        t = i / float(n)
        cell = g.world_to_cell(a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
        if cell is not None:
            cells.add(cell)
    return cells


def declared_grid(box, walls=(), door_xy=None, grid=None):
    """box (x0, y0, x1, y1): cleared floor; every cell that overlaps the box is FREE (so a box that reaches a wall leaves no unknown gap in front of it, which would block the line
    of sight). walls: segments (x0, y0, x1, y1) (OCCUPIED, one cell thick, they override FREE). door_xy: on a wall (OCCUPIED, must lie inside the map)."""
    g = grid if grid is not None else OccupancyGrid.from_config()
    x0, y0, x1, y1 = (float(v) for v in box)
    if not all(math.isfinite(v) for v in (x0, y0, x1, y1)) or not (x0 < x1 and y0 < y1):
        raise ValueError("box must be finite with x0 < x1 and y0 < y1")
    rows, cols = np.indices(g.cells.shape)
    xs = g.origin[0] + (cols + 0.5) * g.resolution_m
    ys = g.origin[1] + (rows + 0.5) * g.resolution_m
    h = g.resolution_m / 2.0 + 1e-9
    g.cells[(xs >= x0 - h) & (xs <= x1 + h) & (ys >= y0 - h) & (ys <= y1 + h)] = FREE
    for w in walls:
        if len(w) != 4 or not all(math.isfinite(v) for v in w):
            raise ValueError("a wall is (x0, y0, x1, y1), finite")
        for cell in _wall_cells(g, (w[0], w[1]), (w[2], w[3])):
            g.cells[cell] = OCCUPIED
    if door_xy is not None:
        cell = g.world_to_cell(*door_xy)
        if cell is None:
            raise ValueError("the door is outside the map")
        g.cells[cell] = OCCUPIED
    return g


def door_cell_centre(grid, door_xy):
    """The centre of the door's cell. A door exactly on a grid corner (easy to type: 5.1, 0.0) makes the line of sight end on a corner that also touches the next wall cell,
    and every candidate fails; the cell centre has no such ambiguity."""
    cell = grid.world_to_cell(*door_xy)
    if cell is None:
        raise ValueError("the door is outside the map")
    return grid.cell_to_world(cell)


def straight_path_clear(grid, a_xy, b_xy, radius_m, clearance=None):
    """True when the straight line a -> b crosses only FREE cells that keep radius_m from anything that is not free."""
    clearance = grid.clearance_m() if clearance is None else clearance
    for cell in grid.segment_cells(a_xy, b_xy):
        if not grid.in_bounds(cell) or grid.cells[cell] != FREE or clearance[cell] < radius_m:
            return False
    return True


def select_reachable(selector, grid, door_xy, pose):
    """First sweet spot of selector.rank (best score first) that the robot reaches along a straight clear line from `pose` (a Pose2D); None when no candidate qualifies."""
    clearance = grid.clearance_m()
    door_xy = door_cell_centre(grid, door_xy)
    for p in selector.rank(grid, door_xy, pose):
        if straight_path_clear(grid, (pose.x_m, pose.y_m), (p.x_m, p.y_m), selector.robot_radius_m, clearance):
            return p
    return None
