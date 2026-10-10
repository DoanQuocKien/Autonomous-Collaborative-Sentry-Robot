import cv2
import numpy as np

from tools.make_markers import checkerboard, checkerboard_page, marker, marker_pages, px


def _padded(img, mm=15):
    return cv2.copyMakeBorder(img, px(mm), px(mm), px(mm), px(mm), cv2.BORDER_CONSTANT, value=255)


def test_markers_are_100mm_and_detectable():
    assert marker("DICT_4X4_50", 3).shape == (px(100), px(100)) == (1000, 1000)
    d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    det = cv2.aruco.ArucoDetector(d, cv2.aruco.DetectorParameters())
    small = cv2.resize(_padded(marker("DICT_4X4_50", 3)), None, fx=0.2, fy=0.2, interpolation=cv2.INTER_AREA)
    _, ids, _ = det.detectMarkers(small)
    assert ids is not None and ids.ravel().tolist() == [3]


def test_checkerboard_has_9x6_inner_corners():
    small = cv2.resize(_padded(checkerboard()), None, fx=0.15, fy=0.15, interpolation=cv2.INTER_AREA)
    found, corners = cv2.findChessboardCorners(small, (9, 6))
    assert found and len(corners) == 54


def test_150mm_markers_fit_one_per_page():
    pages = marker_pages([0, 1, 2], size_mm=150)
    assert len(pages) == 3 and pages[0].shape == (px(297), px(210))
    assert marker("DICT_4X4_50", 0, 150).shape == (1500, 1500)


def test_pages_are_a4():
    assert marker_pages([0, 1, 2])[0].shape == (px(297), px(210)) and len(marker_pages([0, 1, 2])) == 2
    assert checkerboard_page().shape == (px(210), px(297))
