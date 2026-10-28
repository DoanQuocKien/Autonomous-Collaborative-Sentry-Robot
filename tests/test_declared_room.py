import pytest

from sentry.nav.declared_room import declared_grid, door_cell_centre, select_reachable, straight_path_clear
from sentry.nav.gridmap import FREE, OCCUPIED, UNKNOWN, OccupancyGrid, Pose2D
from sentry.nav.vantage import VantageSelector

BOX = (-1.0, -2.0, 5.0, 2.0)                       # a 6 x 4 m room: the door is in the middle of the far wall, 2 m from each side wall
WALLS = [(5.1, -2.1, 5.1, 2.1), (-1.1, -2.1, -1.1, 2.1), (-1.1, 2.1, 5.1, 2.1), (-1.1, -2.1, 5.1, -2.1)]
DOOR = (5.1, 0.0)


def room(**kw):
    g = OccupancyGrid(0.1, 12.0, 8.0, (-3.0, -4.0))
    return declared_grid(BOX, WALLS, DOOR, grid=g, **kw)


def state(g, x, y):
    return g.cells[g.world_to_cell(x, y)]


def test_the_declared_cells_are_free_occupied_and_unknown():
    g = room()
    assert state(g, 2.0, 0.0) == FREE and state(g, 0.0, 0.0) == FREE            # the cleared box
    assert state(g, 5.1, 1.5) == OCCUPIED and state(g, 2.0, 2.1) == OCCUPIED     # walls
    assert state(g, 5.1, 0.0) == OCCUPIED                                        # the door is part of the wall
    assert state(g, 7.5, 0.0) == UNKNOWN                                         # outside everything declared
    with pytest.raises(ValueError):
        declared_grid((1.0, 0.0, 0.0, 1.0))                                      # an empty box
    with pytest.raises(ValueError):
        declared_grid(BOX, door_xy=(500.0, 0.0), grid=OccupancyGrid(0.1, 12.0, 8.0, (-3.0, -4.0)))


def test_the_selected_sweet_spot_meets_the_three_spec_conditions():
    g = room()
    s = VantageSelector(min_distance_m=1.8, max_distance_m=2.7, robot_radius_m=0.15)
    p = select_reachable(s, g, DOOR, Pose2D(0.0, 0.0, 0.0))
    assert p is not None
    assert 1.8 <= p.door_distance_m <= 2.7                                       # distance to the entrance (spec: 1.5-3.0 m, with a margin for dead reckoning)
    assert g.line_of_sight((p.x_m, p.y_m), door_cell_centre(g, DOOR), allow_occupied_end=True)       # clear line of sight
    assert p.boundary_distance_m < 0.6                                           # close to a wall (the side walls are inside the distance ring)
    assert straight_path_clear(g, (0.0, 0.0), (p.x_m, p.y_m), 0.15)             # the robot can drive there in a straight line


def test_a_blocker_across_every_straight_path_leaves_no_sweet_spot():
    g = room()
    for yy in [i * 0.1 for i in range(-20, 21)]:
        g.cells[g.world_to_cell(1.0, yy)] = OCCUPIED                              # furniture row across the whole box
    s = VantageSelector(min_distance_m=1.8, max_distance_m=2.7, robot_radius_m=0.15)
    assert select_reachable(s, g, DOOR, Pose2D(0.0, 0.0, 0.0)) is None


def test_a_room_too_small_for_the_distance_window_has_no_sweet_spot():
    g = declared_grid((-1.0, -1.0, 1.0, 1.0), [(1.1, -1.1, 1.1, 1.1)], DOOR, grid=OccupancyGrid(0.1, 12.0, 8.0, (-3.0, -4.0)))
    s = VantageSelector(min_distance_m=1.8, max_distance_m=2.7, robot_radius_m=0.15)
    assert select_reachable(s, g, DOOR, Pose2D(0.0, 0.0, 0.0)) is None


def test_straight_path_clear_needs_clearance_from_walls_and_free_cells():
    g = room()
    assert straight_path_clear(g, (0.0, 0.0), (2.0, 0.0), 0.15)
    assert not straight_path_clear(g, (0.0, 0.0), (2.0, 2.05), 0.15)            # runs into the wall clearance
    assert not straight_path_clear(g, (0.0, 0.0), (7.0, 0.0), 0.15)             # leaves the declared floor
