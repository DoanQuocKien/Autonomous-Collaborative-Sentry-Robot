from types import SimpleNamespace

import numpy as np
import pytest

from sentry.app.phase2_live import DoorSettings
from sentry.net.frame import VideoFrame
from tools.enroll_door import capture, pose_feedback


def test_guided_stream_enrolment_requires_all_five_poses_and_closes_receiver():
    image = np.random.default_rng(3).integers(0, 255, (140, 140, 3), np.uint8)
    class Source:
        t = 0
        closed = False
        seq = 0

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.closed = True

        def read(self, timeout):
            self.t += .1
            self.seq += 1
            return VideoFrame(self.seq, self.t, self.t, self.t, image, b"")
    source = Source()
    class Encoder:
        calls = 0

        def extract(self, img):
            # Two observations per hold, five instructed poses.
            pose = min(self.calls // 2, 4)
            yaw = [0, .3, -.3, 0, 0][pose]
            self.calls += 1
            kps = np.array([[20, 20], [100, 20], [60 + 80 * yaw, 40], [30, 70], [90, 70]])
            embedding = np.zeros(512, np.float32)
            embedding[pose] = 1
            return [dict(bbox=(10, 10, 120, 120), confidence=.9, kps=kps, embedding=embedding)]
    settings = DoorSettings(min_sharpness=0)
    enrol = dict(min_face_width=80, hold_s=.09, turn_min=.2, turn_max=.45)
    result = capture(source, Encoder(), settings, enrol, 3, clock=lambda: source.t)
    assert source.closed and result.shape == (5, 512)
    assert np.allclose(np.linalg.norm(result, axis=1), 1)
    source = Source()
    with pytest.raises(TimeoutError, match="no embeddings saved"):
        capture(source, SimpleNamespace(extract=lambda image: []), settings, enrol, .4, clock=lambda: source.t)
    assert source.closed


def test_pose_feedback_distinguishes_wrong_turn_from_face_size():
    image = np.ones((140, 140, 3), np.uint8)
    f = dict(bbox=(10, 10, 120, 120), confidence=.9,
             kps=np.array([[20, 20], [100, 20], [80, 40], [30, 70], [90, 70]]))
    settings = DoorSettings(min_sharpness=0)
    enrol = dict(min_face_width=80)
    assert "other way" in pose_feedback(f, image, (-.45, -.2), enrol, settings)
    f["bbox"] = (10, 10, 40, 100)
    assert "closer" in pose_feedback(f, image, (-.45, -.2), enrol, settings)
