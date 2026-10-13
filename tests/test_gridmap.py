import math

import numpy as np
import pytest

from sentry.nav.gridmap import FREE, OCCUPIED, UNKNOWN, OccupancyGrid, Pose2D
from sentry.perception.camera import GroundPoint


def grid():
    return OccupancyGrid(1, 6, 6, (0, 0))


def test_world_pose_offset_and_unknown_semantics():
    g = OccupancyGrid(0.1, 6, 6, (-3, -3), camera_offset=(0.1, 0.2))
    pose = Pose2D(0, 0, math.pi / 2)
    p = GroundPoint(1, 0.5)
    assert g.ground_to_world(pose, p) == pytest.approx((-0.7, 1.1))
    g.update(pose, [p])
    assert g.cells[g.world_to_cell(-0.7, 1.1)] == OCCUPIED
    assert g.cells[g.world_to_cell(0, 0)] == FREE
    assert g.cells[g.world_to_cell(-0.35, 0.55)] == UNKNOWN


def test_floor_occlusion_and_occupied_persistence():
    g, pose = grid(), Pose2D(0.5, 2.5, 0)
    g.update(pose, [GroundPoint(2, 0)], [GroundPoint(4, 0)])
    assert list(g.cells[2]) == [FREE, FREE, OCCUPIED, UNKNOWN, UNKNOWN, UNKNOWN]
    g.update(Pose2D(2.5, 2.5, 0))
    assert g.cells[2, 2] == OCCUPIED


def test_no_outside_obstacle_clipped_to_edge():
    g = grid()
    g.update(Pose2D(5.5, 2.5, 0), [GroundPoint(3, 0)])
    assert not np.any(g.cells == OCCUPIED)
    assert g.world_to_cell(6, 0) is None
    assert g.world_to_cell(-0.01, 0) is None
    with pytest.raises(ValueError):
        g.update(Pose2D(9, 0, 0))


@pytest.mark.parametrize("start,end", [((0.5, 1.5), (1, 1)), ((1, 1), (0.5, 1.5)),
                                      ((0.5, 0.5), (4.5, 4.5)), ((4.5, 4.5), (0.5, 0.5)),
                                      ((0.5, 2.5), (4.5, 2.5)), ((3.5, 3.5), (3.5, 3.5))])
def test_segment_terminates_and_is_symmetric(start, end):
    g = grid()
    cells = list(g.segment_cells(start, end))
    assert len(cells) <= 25
    assert cells[0] == g.world_to_cell(*start)
    assert cells[-1] == g.world_to_cell(*end)
    assert set(cells) == set(g.segment_cells(end, start))


def test_los_blocks_unknown_corner_and_nonterminal_obstacles():
    g = grid()
    g.cells[:] = FREE
    g.cells[1, 0] = OCCUPIED  # corner of diagonal
    assert not g.line_of_sight((0.5, 0.5), (2.5, 2.5))
    g.cells[:] = FREE
    g.cells[2, 2] = OCCUPIED
    assert g.line_of_sight((0.5, 2.5), (2.5, 2.5), True)
    assert not g.line_of_sight((0.5, 2.5), (3.5, 2.5), True)
    g.cells[2, 2] = UNKNOWN
    assert not g.line_of_sight((0.5, 2.5), (2.5, 2.5), True)


def test_grid_boundary_ray_checks_both_sides():
    g = grid()
    g.cells[:] = FREE
    g.cells[1, 2] = OCCUPIED
    assert not g.line_of_sight((0.5, 2), (4.5, 2))
    g.cells[:] = FREE
    g.cells[2, 1] = UNKNOWN
    assert not g.line_of_sight((2, 0.5), (2, 4.5))


def test_random_ray_reversal_and_work_bound():
    g = grid()
    rng = np.random.default_rng(532)
    for _ in range(100):
        a, b = rng.uniform(0, 6, (2, 2))
        cells = list(g.segment_cells(a, b))
        assert len(cells) < 40
        assert set(cells) == set(g.segment_cells(b, a))


def test_clearance_disconnects_narrow_corridor():
    g = OccupancyGrid(0.1, 2, 2, (0, 0))
    g.cells[:] = OCCUPIED
    g.cells[2:18, 2:8] = FREE
    g.cells[2:18, 12:18] = FREE
    g.cells[9, 8:12] = FREE  # one-cell doorway
    pose = Pose2D(0.55, 1.05, 0)
    assert g.reachable(pose, 0)[10, 15]
    assert not g.reachable(pose, 0.15)[10, 15]


def test_roundtrip_guarding_pose_and_corrupt_map(tmp_path):
    g = OccupancyGrid(0.1, 6, 4, (-3, -2), 0.12, (0.1, 0.2))
    g.update(Pose2D(0, 0, 0), [GroundPoint(1, 0.2)])
    guard = Pose2D(1, 2, 0.5)
    path = tmp_path / "map.npz"
    g.save(path, guard)
    other = OccupancyGrid.load(path)
    assert np.array_equal(other.cells, g.cells)
    assert other.guarding_pose == guard and other.camera_offset == g.camera_offset
    assert other.origin == g.origin and other.resolution_m == g.resolution_m
    np.savez(path, cells=np.array([[7]]), metadata='{"version":1}')
    with pytest.raises(ValueError):
        OccupancyGrid.load(path)


def test_actual_start_pose_near_unknown_has_no_clearance():
    g = grid()
    g.cells[2:4, 2:4] = FREE
    assert g.reachable(Pose2D(2.5, 2.5, 0), 0.1).any()
    assert not g.reachable(Pose2D(2.01, 2.01, 0), 0.1).any()
