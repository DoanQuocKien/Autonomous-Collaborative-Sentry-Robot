import math

import numpy as np
import pytest

from sentry.nav.gridmap import FREE, OCCUPIED, UNKNOWN, OccupancyGrid, Pose2D
from sentry.nav.vantage import VantageSelector


def room():
    g = OccupancyGrid(0.2, 6, 6, (0, 0))
    g.cells[:] = FREE
    g.cells[[0, -1], :] = OCCUPIED
    g.cells[:, [0, -1]] = OCCUPIED
    return g, (5.9, 3.1), Pose2D(2.5, 3.1, 0)


def test_spot_satisfies_conditions_and_prefers_observed_boundary():
    g, door, pose = room()
    s = VantageSelector()
    ranked = s.rank(g, door, pose)
    best = s.select(g, door, pose)
    assert best == ranked[0] and best == s.select(g, door, pose)
    assert 1.5 <= best.door_distance_m <= 3
    assert best.boundary_distance_m < 0.8
    assert g.line_of_sight((best.x_m, best.y_m), door, True)
    assert g.reachable(pose, s.robot_radius_m)[g.world_to_cell(best.x_m, best.y_m)]
    assert best.yaw_rad == pytest.approx(math.atan2(door[1] - best.y_m, door[0] - best.x_m))
    assert best.score >= ranked[-1].score
    boundary_only = VantageSelector(distance_weight=0).rank(g, door, pose)
    assert boundary_only[0].boundary_distance_m == min(p.boundary_distance_m for p in boundary_only)


@pytest.mark.parametrize("state", [UNKNOWN, OCCUPIED])
def test_no_spot_through_unknown_or_obstructed_wall(state):
    g, door, pose = room()
    g.cells[:, 20] = state
    assert VantageSelector().select(g, door, pose) is None


def test_unknown_door_and_outside_door_do_not_qualify():
    g, door, pose = room()
    g.cells[g.world_to_cell(*door)] = UNKNOWN
    assert VantageSelector().select(g, door, pose) is None
    assert VantageSelector().select(g, (10, 10), pose) is None
    with pytest.raises(ValueError):
        VantageSelector().select(g, (math.nan, 1), pose)
