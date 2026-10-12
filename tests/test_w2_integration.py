"""Contracts across the merged DQK/KR and HNHL Week 2 modules."""
import math
from types import SimpleNamespace

import numpy as np
import pytest

from sentry.nav.gridmap import OCCUPIED, OccupancyGrid
from sentry.nav.localization import RobotPose
from sentry.nav.prescan import PreScanner
from sentry.nav.vantage import VantageSelector
from sentry.perception.camera import CameraGeometry, GroundPoint
from sentry.perception.entrance import EntranceResult
from sentry.perception.obstacle import Detection, Obstacle, ObstacleResult


def test_locked_session_pose_loads_and_projects_tape_rows():
    geometry = CameraGeometry.from_files('calib/camera.json', 'calib/camera_pose_classroom_locked.json')
    assert geometry.pitch < 0
    assert geometry.pose_status == 'measured_session_without_pass_flag'
    for row, tape in zip((313.5, 282.0, 267.0), (0.5, 1.0, 2.0)):
        point = geometry.ground_point(geometry.K[0, 2], row)
        assert point is not None and abs(point.forward_m - tape) < 0.04


def test_kr_robot_pose_flows_through_prescan_with_camera_offset():
    pose = RobotPose(x=1, y=2, theta=math.pi / 2, t=5)
    point = GroundPoint(0.8, 0.3)
    observed = ObstacleResult(5, (Obstacle(Detection(56, 0.9, (1, 1, 3, 3)), point),), 0, point.distance_m)
    grid = OccupancyGrid(0.1, 6, 6, origin=(0, 0), camera_offset=(0.2, -0.1))
    scanner = PreScanner(lambda image, t: observed, grid, VantageSelector.from_config())
    result = scanner(np.zeros((480, 640, 3), np.uint8), 5, pose)
    # Local (forward,left)=(1.0,0.2), rotated +90 degrees -> (-0.2,+1.0).
    assert grid.ground_to_world(pose, point) == pytest.approx((0.8, 3.0))
    assert grid.cells[grid.world_to_cell(0.8, 3.0)] == OCCUPIED
    assert result.vantage is None


def test_entrance_bearing_needs_measured_range():
    pose = RobotPose(x=1, y=2, theta=math.pi / 2)
    entrance = EntranceResult(True, bearing_rad=-math.pi / 2)
    assert entrance.estimate_door_world_xy(pose) is None
    assert entrance.estimate_door_world_xy(pose, 1.7) == pytest.approx((2.7, 2))
    assert pose.calculate_door_world_xy(-math.pi / 2, 1.7) == pytest.approx((2.7, 2))
    with pytest.raises(TypeError):
        pose.calculate_door_world_xy(0)
    assert EntranceResult(False, bearing_rad=0).estimate_door_world_xy(pose, 1.7) is None


@pytest.mark.parametrize('distance', [0, -1, math.nan, math.inf])
def test_door_helpers_reject_invalid_range(distance):
    pose = RobotPose()
    with pytest.raises(ValueError):
        pose.calculate_door_world_xy(0, distance)
    with pytest.raises(ValueError):
        EntranceResult(True, bearing_rad=0).estimate_door_world_xy(pose, distance)


def test_door_helper_rejects_missing_pose_instead_of_inventing_origin():
    with pytest.raises(ValueError):
        EntranceResult(True, bearing_rad=0).estimate_door_world_xy(SimpleNamespace(), 1)
