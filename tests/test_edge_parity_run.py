import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "jetson"))
import face_post  # noqa: E402
import parity_run as pr  # noqa: E402
import yolo_post  # noqa: E402

from tools import edge_parity  # noqa: E402


def frame():
    rng = np.random.RandomState(3)
    return (rng.rand(480, 640, 3) * 255).astype(np.uint8)


def test_yolo_inputs_equal_the_benchs_letterbox():
    f = frame()
    blob, scale, px, py = yolo_post.letterbox(f, 320)
    canvas, s2, px2, py2 = pr.yolo_canvas(f, 320)
    assert (scale, px, py) == (s2, px2, py2) and np.array_equal(blob, pr.yolo_blob(canvas))


def test_scrfd_inputs_equal_the_benchs_scrfd_input():
    f = frame()
    blob, scale = face_post.scrfd_input(f, 320)
    canvas, s2 = pr.scrfd_canvas(f, 320)
    assert scale == s2 and np.array_equal(blob, pr.scrfd_blob(canvas))


def test_cosines_and_box_matching():
    a = np.array([[1.0, 0, 0], [0, 1.0, 0]])
    b = np.array([[2.0, 0, 0], [1.0, 1.0, 0]])
    c = edge_parity.cosines(a, b)
    assert abs(c[0] - 1.0) < 1e-9 and abs(c[1] - np.sqrt(0.5)) < 1e-9
    ba = np.array([[0, 0, 10, 10], [50, 50, 60, 60]], np.float32)
    bb = np.array([[0, 0, 10, 10], [80, 80, 90, 90]], np.float32)
    assert edge_parity.match_boxes(ba, bb) == (1, 2) and edge_parity.match_boxes(ba, np.zeros((0, 4))) == (0, 2) and edge_parity.match_boxes(np.zeros((0, 4)), bb) == (0, 0)


def test_stack_outputs_names_scrfd_outputs_by_shape_and_drops_the_batch_of_the_others():
    det = [[np.ones((1, 84, 5), np.float32)], [np.zeros((1, 84, 5), np.float32)]]
    assert pr.stack_outputs("det", det)["det_0"].shape == (2, 84, 5)
    sc = [[np.ones((3200, 1), np.float32), np.ones((3200, 4), np.float32)]] * 2
    s = pr.stack_outputs("scrfd", sc, sort_by_shape=True)
    assert sorted(s) == ["scrfd_3200_1", "scrfd_3200_4"] and s["scrfd_3200_4"].shape == (2, 3200, 4)
