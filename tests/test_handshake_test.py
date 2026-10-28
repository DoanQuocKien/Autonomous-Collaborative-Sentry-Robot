import json
from types import SimpleNamespace

import cv2
import numpy as np

from tools import handshake_test as ht


def test_decide_is_a_majority_and_empty_is_not_in_view():
    assert ht.decide([True, True, False]) == (True, 2 / 3.0)
    assert ht.decide([True, False]) == (True, 0.5)
    assert ht.decide([False, False, True])[0] is False
    assert ht.decide([]) == (False, 0.0)


def test_tally_counts_correct_accepts_and_rejects():
    t = [{"kind": "accept", "in_view": True}, {"kind": "accept", "in_view": False}, {"kind": "reject", "in_view": False}, {"kind": "reject", "in_view": True}]
    assert ht.tally(t) == {"accepts": 2, "correct_accepts": 1, "rejects": 2, "correct_rejects": 1}


class FakeDetector:
    """In view when the mean brightness of the frame is above 100 (stands in for XFeat + RANSAC)."""

    def __init__(self):
        self.refs = []

    def enroll_esp32(self, frames, rois=None):
        self.refs = list(frames)

    def calibrate(self, negatives):
        return 27, None

    def detect(self, frame):
        return SimpleNamespace(in_view=bool(frame.mean() > 100), inliers=int(frame.mean()))


def test_eval_scores_trials_with_a_fake_detector(tmp_path):
    root = tmp_path / "door"
    for sub in ("ref", "sweep"):
        (root / sub).mkdir(parents=True)
    for i in range(3):
        cv2.imwrite(str(root / "ref" / ("r%04d.jpg" % i)), np.full((48, 64, 3), 200, np.uint8))
        cv2.imwrite(str(root / "sweep" / ("s%04d.jpg" % i)), np.full((48, 64, 3), 20, np.uint8))
    for k, kind in enumerate(["accept", "reject", "accept", "reject"], 1):
        d = root / "trials" / ("t%02d_%s" % (k, kind))
        d.mkdir(parents=True)
        for n, t in enumerate([0.2, 1.0, 2.0, 3.0, 4.0]):                     # the first two are inside the skipped transition
            val = 200 if kind == "accept" else 20
            cv2.imwrite(str(d / ("f%03d_%.2f.jpg" % (n, t))), np.full((48, 64, 3), val, np.uint8))
    res = ht.cmd_eval(SimpleNamespace(), root, detector=FakeDetector())
    assert (res["correct_accepts"], res["accepts"], res["correct_rejects"], res["rejects"]) == (2, 2, 2, 2)
    assert all(t["frames_scored"] == 3 for t in res["trials"]) and json.loads((root / "results.json").read_text())["accepts"] == 2
