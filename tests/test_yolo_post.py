import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "jetson"))
pytest.importorskip("cv2")
import yolo_post  # noqa: E402


def test_letterbox_maps_a_box_back_to_the_original_pixels():
    frame = np.zeros((480, 640, 3), np.uint8)
    blob, scale, px, py = yolo_post.letterbox(frame, 320)
    assert blob.shape == (1, 3, 320, 320) and scale == 0.5 and (px, py) == (0, 40)
    # a person box at x 200..300, y 100..400 in the original image sits at x 100..150, y 90..240 in the letterboxed one
    out = np.zeros((1, 4 + 80, 2), np.float32)
    out[0, :4, 0] = [125, 165, 50, 150]                 # cx, cy, w, h (letterboxed)
    out[0, 4, 0] = 0.9                                   # class 0 (person) score
    boxes, scores, cls, _ = yolo_post.decode(out, scale, px, py)
    assert np.allclose(boxes[0], [200, 100, 300, 400]) and cls[0] == 0 and scores[0] > 0.8


def test_nms_keeps_the_best_of_two_overlapping_boxes_and_the_far_one():
    boxes = np.array([[0, 0, 10, 10], [1, 1, 11, 11], [50, 50, 60, 60]], np.float32)
    assert yolo_post.nms(boxes, np.array([0.6, 0.9, 0.7], np.float32)) == [1, 2]


def test_pose_keypoints_are_mapped_and_empty_output_is_safe():
    out = np.zeros((1, 56, 3), np.float32)
    out[0, :5, 0] = [100, 100, 40, 80, 0.8]
    out[0, 5:8, 0] = [110, 90, 0.9]                      # first keypoint: x, y, visibility
    boxes, scores, cls, kp = yolo_post.decode(out, 0.5, 0, 40, n_kpt=17)
    assert len(boxes) == 1 and np.allclose(kp[0, 0, :2], [220, 100]) and kp.shape == (1, 17, 3)
    assert yolo_post.decode(np.zeros((1, 56, 3), np.float32), 0.5, 0, 40, n_kpt=17)[0].shape == (0, 4)
