import math

import cv2
import numpy as np
import pytest

from sentry.config import load
from sentry.perception.camera import CameraGeometry, GroundPoint
from sentry.perception.obstacle import Detection, ObstacleDetector, YOLOPredictor, repulsive_w
from tools.measure_camera_pose import undistorted


def geometry(pitch=0, roll=0):
    return CameraGeometry(dict(K=[[300, 0, 320], [0, 300, 240], [0, 0, 1]],
                               D=[0, 0, 0, 0], image_size=[640, 480]),
                          dict(H_cam_m=0.1, pitch_down_deg=pitch, camera_roll_deg=roll, passed=True))


def project(forward, left, height, pitch_deg, roll_deg):
    # Independent ground -> camera rotation, then image roll, for round trips.
    pitch, roll = math.radians(pitch_deg), math.radians(roll_deg)
    z = math.cos(pitch) * forward + math.sin(pitch) * height
    y = -math.sin(pitch) * forward + math.cos(pitch) * height
    du, dv = -300 * left / z, 300 * y / z
    return (320 + math.cos(roll) * du - math.sin(roll) * dv,
            240 + math.sin(roll) * du + math.cos(roll) * dv)


@pytest.mark.parametrize("pitch,roll", [(0, 0), (2.63, 0), (15, 0), (8, 6)])
@pytest.mark.parametrize("forward,left", [(0.3, 0), (1, 0.2), (2, -0.4)])
def test_ground_projection_roundtrip(pitch, roll, forward, left):
    p = geometry(pitch, roll).ground_point(*project(forward, left, 0.1, pitch, roll))
    assert p is not None
    assert (p.forward_m, p.left_m) == pytest.approx((forward, left))
    assert p.distance_m == pytest.approx(math.hypot(forward, left))


def test_level_formula_and_left_bearing():
    p = geometry().ground_point(290, 300)
    assert p.forward_m == pytest.approx(300 * 0.1 / (300 - 240))
    assert p.left_m > 0 and p.bearing_rad > 0


@pytest.mark.parametrize("pixel", [(320, 240), (320, 100), (-1, 300), (640, 300), (math.nan, 300), (320, 241)])
def test_invalid_horizon_or_too_far(pixel):
    assert geometry().ground_point(*pixel) is None


def test_same_k_as_measured_camera_and_bad_frame_shape():
    import json
    from pathlib import Path
    camera = json.loads(Path("calib/camera.json").read_text())
    g = CameraGeometry.from_files("calib/camera.json", "calib/camera_pose_nowedge.json")
    frame = np.random.default_rng(532).integers(0, 256, (480, 640, 3), dtype=np.uint8)
    assert np.max(np.abs(g.undistort(frame).astype(int) - undistorted(frame, camera).astype(int))) <= 8
    fixed, frac = cv2.fisheye.initUndistortRectifyMap(g.K, g.D, np.eye(3), g.K, g.size, cv2.CV_16SC2)
    mx, my = cv2.convertMaps(fixed, frac, cv2.CV_32FC1)
    assert np.max(np.abs(g.map_x - mx)) <= 1 / 32
    assert np.max(np.abs(g.map_y - my)) <= 1 / 32
    with pytest.raises(ValueError):
        g.undistort(frame[:240])
    with pytest.raises(ValueError):
        g.undistort(frame.astype(float))


@pytest.mark.parametrize("change", [{"passed": False}, {"H_cam_m": math.nan}, {"H_cam_m": 0}, {"pitch_down_deg": 90}])
def test_reject_invalid_pose(change):
    g = geometry()
    pose = dict(H_cam_m=0.1, pitch_down_deg=0, passed=True)
    pose.update(change)
    with pytest.raises(ValueError):
        CameraGeometry(dict(K=g.K, D=g.D, image_size=list(g.size)), pose)


def detector(detections):
    config = load()
    return ObstacleDetector(geometry(), lambda image: detections, config["obstacle"], config["thresholds"])


def test_filter_rejections_and_real_contact_point():
    detections = [Detection(0, 0.9, (280, 100, 300, 320)), # person ignored
                  Detection(56, 0.1, (280, 100, 300, 320)),
                  Detection(56, 0.9, (280, 100, 300, 320)),
                  Detection(57, 0.8, (300, 200, 340, 480)),
                  Detection(56, 0.8, (300, 50, 340, 150)),
                  Detection(56, 0.8, (-1, 50, 340, 300))]
    r = detector(detections)(np.zeros((480, 640, 3), np.uint8), 123.4)
    assert r.t == 123.4 and len(r.obstacles) == 4
    assert r.ground_points[0].forward_m == pytest.approx(0.375)
    assert r.repulsive_w < 0 and r.unresolved
    assert [o.rejection for o in r.obstacles] == [None, "bottom_truncated",
                                                "no_ground_intersection_or_out_of_range", "invalid_box"]


def test_modes_and_instance_isolation():
    a = detector([Detection(56, 0.9, (310, 150, 330, 295))])  # ~0.545 m
    b = detector([])
    frame = np.zeros((480, 640, 3), np.uint8)
    assert a(frame, 1).repulsive_w > 0
    assert a(frame, 1, "pursuit").repulsive_w == 0
    assert b(frame, 1).ground_points == ()
    for t, mode in [(math.inf, "explore"), (1, "other")]:
        with pytest.raises(ValueError):
            a(frame, t, mode)


def test_repulsion_sign_bounds_balanced_and_threshold():
    assert repulsive_w([GroundPoint(0.3, 0.1)], 0.6) < 0
    assert repulsive_w([GroundPoint(0.3, -0.1)], 0.6) > 0
    assert repulsive_w([GroundPoint(0.6, 0)], 0.6) == 0
    assert repulsive_w([GroundPoint(0.1, 0)] * 10, 0.6) == 1
    assert repulsive_w([GroundPoint(0.3, 0.1), GroundPoint(0.3, -0.1)], 0.6) == 0
    with pytest.raises(ValueError):
        repulsive_w([], math.nan)


def test_no_implicit_weight_download(tmp_path):
    with pytest.raises(FileNotFoundError):
        YOLOPredictor(tmp_path / "missing.pt", load()["obstacle"])


@pytest.mark.parametrize("K,D", [([[0, 0, 320], [0, 300, 240], [0, 0, 1]], [0]*4),
                                 ([[300, 0, 320], [0, math.inf, 240], [0, 0, 1]], [0]*4),
                                 ([[300, 0, 320], [0, 300, 240], [0, 0, 1]], [math.nan]*4)])
def test_reject_invalid_intrinsics(K, D):
    with pytest.raises(ValueError):
        CameraGeometry(dict(K=K, D=D, image_size=[640, 480]),
                       dict(H_cam_m=0.1, pitch_down_deg=0, passed=True))
