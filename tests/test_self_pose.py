import json
import math

import numpy as np
import pytest

from tools import self_pose


def test_a_steady_marker_gives_a_pose_with_the_median_pitch_and_the_fixed_lens_height():
    p = self_pose.make_pose([1.0 + 0.02 * (i % 3) for i in range(30)], [0.5] * 30, 0.100, "self_test")
    assert p["pitch_down_deg"] == pytest.approx(1.02, abs=0.01) and p["H_cam_m"] == 0.1 and p["passed"] and p["marker_frames"] == 30
    json.dumps(p)                                                                    # it is writable as JSON
    for key in ("tag", "H_cam_m", "pitch_down_deg", "camera_roll_deg"):                # the fields sentry.perception.camera reads
        assert key in p


def test_too_few_frames_or_a_scattering_marker_is_refused_with_the_reason():
    with pytest.raises(ValueError, match="only 5 usable"):
        self_pose.make_pose([1.0] * 5, [0.0] * 5, 0.1, "t")
    rng = np.random.RandomState(0)
    with pytest.raises(ValueError, match="scatter"):
        self_pose.make_pose(list(rng.uniform(-3, 3, 40)), [0.0] * 40, 0.1, "t")


def test_a_synthetic_marker_recovers_the_pitch_it_was_rendered_with():
    """Render a 4x4_50 marker with a known camera pitch through the real pose estimator: the recovered pitch must match within half a degree."""
    import cv2
    from sentry.perception.camera_pose import pose_from_corners
    K = np.array([[300.0, 0, 320.0], [0, 300.0, 240.0], [0, 0, 1.0]])
    marker_m, bottom_h, cam_h, pitch_deg, dist = 0.15, 0.132, 0.100, 3.0, 1.5
    pitch = math.radians(pitch_deg)
    # marker corners in the world (x forward from the camera foot, y left, z up), as seen by a camera at (0, 0, cam_h) pitched DOWN by pitch_deg
    corners_w = np.array([[dist, marker_m / 2, bottom_h + marker_m], [dist, -marker_m / 2, bottom_h + marker_m],
                          [dist, -marker_m / 2, bottom_h], [dist, marker_m / 2, bottom_h]])
    R = np.array([[0, -1, 0], [0, 0, -1], [1, 0, 0]], float)                           # world (forward, left, up) -> camera (right, down, forward) for a level camera
    c, s = math.cos(pitch), math.sin(pitch)
    Rp = np.array([[1, 0, 0], [0, c, -s], [0, s, c]])                                  # rotate about the camera x axis: looking down by `pitch`
    pts = []
    for w in corners_w:
        pc = Rp @ (R @ (w - np.array([0, 0, cam_h])))
        pts.append([K[0, 0] * pc[0] / pc[2] + K[0, 2], K[1, 1] * pc[1] / pc[2] + K[1, 2]])
    est = pose_from_corners(np.array(pts, np.float32), K, marker_m, bottom_h, cam_h)
    assert est is not None and abs(est["pitch_deg"] - pitch_deg) < 0.5


def test_collect_counts_only_estimates_the_filter_accepted(monkeypatch):
    ests = [{"pitch_deg": 1.0, "pitch_ori_deg": 1.0, "roll_deg": 0.2, "bearing_rad": 0.0, "reproj_px": 0.5, "distance_m": 1.5, "height_m": 0.1}] * 10
    ests += [{"pitch_deg": 9.0, "pitch_ori_deg": 9.0, "roll_deg": 0.2, "bearing_rad": 0.0, "reproj_px": 0.5, "distance_m": 1.5, "height_m": 0.1}] * 3      # a jump of 8 deg: rejected
    ests += [{"pitch_deg": 1.0, "pitch_ori_deg": 1.0, "roll_deg": 0.2, "bearing_rad": 0.0, "reproj_px": 5.0, "distance_m": 1.5, "height_m": 0.1}]           # bad reprojection
    ests += [dict(ests[0]) for _ in range(20)]                                                                                                              # more good ones: the history is full (15)
    it = iter([dict(e) for e in ests])

    def fake(self, img, K, marker_m, bottom_h, marker_id=None, camera_h=None):
        est = next(it)
        self.update(est)
        return est
    monkeypatch.setattr(self_pose.TiltFilter, "update_frame", fake)
    pitches, rolls, tilt = self_pose.collect([None] * len(ests), None, lambda im: im, 0.15, 0.132, 0.1)
    assert len(pitches) == 10 + 20 and all(abs(p - 1.0) < 1e-9 for p in pitches) and tilt.rejected == 3


def test_the_marker_heights_come_from_the_config_wherever_their_section_is():
    from sentry.config import load
    cfg = load()
    assert self_pose._cfg_value(cfg, "aruco_square_above_page_m", -1) == 0.132
    assert self_pose._cfg_value(cfg, "aruco_page_bottom_h_m", -1) == 0.0
    assert self_pose._cfg_value({"a": {"x": 1}}, "missing", 7.5) == 7.5
