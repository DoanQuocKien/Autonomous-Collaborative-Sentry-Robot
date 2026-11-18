import cv2
import numpy as np

from sentry.perception.camera import CameraGeometry
from sentry.perception.camera_pose import DICT
from tools.tower_marker_trial import drive_seconds, look


def _frame(marker_id, side=40):
    img = np.full((480, 640), 255, np.uint8)
    m = cv2.aruco.generateImageMarker(cv2.aruco.getPredefinedDictionary(DICT), marker_id, side)
    img[200:200 + side, 300:300 + side] = m
    return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)


def test_look_only_tower_ids():
    g = CameraGeometry.from_files("calib/camera.json", "calib/camera_pose_nowedge.json")
    obj = np.array([[-.025, .025, 0], [.025, .025, 0], [.025, -.025, 0], [-.025, -.025, 0]], np.float64)
    assert look(g, obj, _frame(0)) is None                   # a room board is not the tower
    r = look(g, obj, _frame(11))
    assert r is not None and r[0] == 11 and 30 < r[3] < 50


def test_drive_seconds_keeps_the_floor():
    gain, v = 0.4135, 0.5
    t = drive_seconds(1.4, v, gain)
    assert t * gain * v * 1.15 <= 1.4 + 1e-9 and drive_seconds(-1, v, gain) == 0.0
