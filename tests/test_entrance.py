import csv
import math
import os

import cv2
import numpy as np
import pytest

from sentry.perception.entrance import DINO_REPO, XFEAT_WEIGHTS, Camera, EntranceConfig, EntranceDetector, EntranceFilter, EntranceResult

K = np.array([[300.0, 0, 320.0], [0, 300.0, 240.0], [0, 0, 1.0]])
GRID = np.float32([[x, y] for x in range(40, 600, 40) for y in range(40, 440, 40)])      # 14 x 10 = 140 fake keypoints


def frame(kind, dx=0, dy=0, scale=1.0):
    """A tiny stand-in for a camera frame: pixel (0,0) encodes the scenario for the fakes (0 = no door, 1 = door shifted by dx, dy)."""
    f = np.zeros((480, 640, 3), np.uint8)
    f[0, 0] = (kind, (dx + 128) % 256, (dy + 128) % 256)
    f[1, 0, 0] = int(scale * 10)
    return f


class FakeMatcher:
    """features() tags the frame, match() returns the reference points and where a door would be (a homography: shift + scale), plus outliers."""

    def __init__(self, neg_inliers=3):
        self.neg_inliers = neg_inliers

    def features(self, img):
        return {"kp": GRID, "tag": (int(img[0, 0, 0]), int(img[0, 0, 1]) - 128, int(img[0, 0, 2]) - 128, int(img[1, 0, 0]) / 10.0)}

    def match(self, ref, cur):
        kind, dx, dy, sc = cur["tag"]
        rng = np.random.default_rng(0)
        if kind == 1:
            moved = (GRID - [320, 240]) * sc + [320 + dx, 240 + dy]
            bad = rng.uniform(0, 600, (20, 2)).astype(np.float32)
            return np.vstack([GRID, GRID[:20]]), np.vstack([moved, bad]).astype(np.float32)
        n = self.neg_inliers
        return GRID[:n + 12], np.vstack([GRID[:n] + [5, 5], rng.uniform(0, 600, (12, 2))]).astype(np.float32)


class FakeDescriber:
    """Door frames (and every reference, phone photos included) get one direction plus a little noise; other frames get other directions."""

    def describe(self, images):
        out = []
        for i, im in enumerate(images):
            rng = np.random.default_rng(int(im[0, 0, 1]) * 7 + i)
            v = np.ones(16) if im[0, 0, 0] == 1 else np.eye(16)[int(im[0, 0, 1]) % 16]       # a negative is some other direction: cosine 0.25 to the door
            v = v + rng.normal(scale=0.03, size=16)
            out.append(v / np.linalg.norm(v))
        return np.array(out)


def detector(policy="auto", neg_inliers=3):
    return EntranceDetector(Camera(K), EntranceConfig(policy=policy), FakeMatcher(neg_inliers), FakeDescriber())


def test_xfeat_path_accepts_a_shifted_door_with_a_bearing_and_rejects_the_rest():
    d = detector()
    d.enroll_robot([frame(1)], rois=[(200, 100, 440, 380)])
    r = d.detect(frame(1, dx=60, dy=-10))
    assert r.in_view and r.inliers >= 140 and r.similarity is None
    assert abs(r.bearing_rad - (-math.atan(60 / 300))) < 0.01                  # ROI centre (320, 240) moved 60 px to the right: negative bearing (positive = left)
    assert d.detect(frame(1, dx=-90)).bearing_rad > 0                           # moved left: positive
    n = d.detect(frame(0))
    assert not n.in_view and n.bearing_rad is None and n.quad is None


def test_a_degenerate_homography_is_rejected_even_with_many_inliers():
    d = detector()
    d.enroll_robot([frame(1)])
    assert d.detect(frame(1, scale=1.0)).in_view
    assert not d.detect(frame(1, scale=0.1)).in_view                            # the door would shrink to 1 % of its area: not a door
    assert not d.detect(frame(1, scale=9.0)).in_view


def test_calibrate_raises_the_xfeat_threshold_above_the_negatives_never_below_the_config():
    d = detector(neg_inliers=35)
    d.enroll_robot([frame(1)])
    assert d.xfeat_thr == 27
    thr, _ = d.calibrate([frame(0)] * 5)
    assert thr == 37                                                             # 35 + 2
    d2 = detector(neg_inliers=3)
    d2.enroll_robot([frame(1)])
    assert d2.calibrate([frame(0)] * 5)[0] == 27


def test_dino_path_with_a_phone_photo_needs_a_calibrated_threshold():
    d = detector()
    d.enroll_phone(frame(1))
    with pytest.raises(RuntimeError):
        d.detect(frame(1))                                                       # no threshold yet: refuse to guess
    _, thr = d.calibrate([frame(0, dx=i) for i in range(10)])
    assert 0 < thr < 1
    r = d.detect(frame(1, dx=3))
    assert r.in_view and r.similarity > thr and r.inliers == 0 and r.bearing_rad is None   # DINOv2 says "in view", no bearing
    assert not d.detect(frame(0, dx=40)).in_view


def test_policies_and_or_combine_both_methods():
    for pol, door_only_x, expected in (("and", True, False), ("or", True, True), ("and", False, True)):
        d = detector(policy=pol)
        d.enroll_robot([frame(1)])
        d.enroll_phone(frame(1))
        d.calibrate([frame(0, dx=i) for i in range(10)])
        if door_only_x:
            d.dino_thr = 2.0                                                     # DINOv2 cannot agree: only XFeat sees the door
        assert d.detect(frame(1)).in_view == expected, (pol, door_only_x)
    with pytest.raises(RuntimeError):
        detector(policy="xfeat").detect(frame(1))                                # nothing enrolled


def test_save_and_load_round_trip_keeps_references_and_thresholds(tmp_path):
    d = detector()
    d.enroll_robot([frame(1)], rois=[(200, 100, 440, 380)])
    d.enroll_phone(frame(1))
    d.calibrate([frame(0, dx=i) for i in range(10)])
    d.save(tmp_path / "room")
    d2 = EntranceDetector.load(tmp_path / "room", Camera(K), FakeMatcher(), FakeDescriber())
    assert d2.xfeat_thr == d.xfeat_thr and d2.dino_thr == d.dino_thr and d2.robot_refs[0]["roi"] == [200, 100, 440, 380]
    a, b = d.detect(frame(1, dx=40)), d2.detect(frame(1, dx=40))
    assert a.in_view and b.in_view and abs(a.bearing_rad - b.bearing_rad) < 1e-9


def test_filter_debounces_found_and_lost_and_takes_the_median_bearing():
    f = EntranceFilter(enter=3, exit=5)
    seen = lambda b: EntranceResult(True, 40, None, b)
    gone = EntranceResult(False)
    assert [f.update(seen(0.1)), f.update(gone), f.update(seen(0.1)), f.update(seen(0.3))] == [None] * 4      # the dropout restarted the count
    assert f.update(seen(0.2)) == ("ENTRANCE_FOUND", 0.2)                        # median of 0.1... of the last three: 0.1, 0.3, 0.2 -> 0.2
    assert f.update(seen(0.2)) is None                                           # reported once
    assert [f.update(gone) for _ in range(4)] == [None] * 4                      # 4 misses: still found (hysteresis)
    assert f.update(gone) == ("ENTRANCE_LOST", None)
    assert f.update(gone) is None


def test_camera_bearing_sign_and_fisheye_symmetry():
    cam = Camera(K)
    assert abs(cam.bearing_rad(320, 100)) < 1e-9
    assert cam.bearing_rad(420, 240) < 0 < cam.bearing_rad(220, 240)
    assert abs(cam.bearing_rad(420, 240) + 100 / 300) < 1e-9                       # equidistant fisheye: the angle is r / f
    fish = Camera(K, [-0.03, 0.0005, -0.006, 0.0017])
    assert abs(fish.bearing_rad(420, 240) + fish.bearing_rad(220, 240)) < 1e-6


def test_config_and_pins():
    assert EntranceConfig.from_toml({"min_inliers": 30}).min_inliers == 30
    with pytest.raises(TypeError):
        EntranceConfig.from_toml({"min_inlier": 30})                             # a typo is an error
    from tools import fetch_models
    assert fetch_models.DINO_REPO == DINO_REPO and fetch_models.SHA256["xfeat.pt"] and fetch_models.HTTP[0][0].name == "xfeat.pt"


# ---- with the real XFeat weights (python -m tools.fetch_models) ------------------------------------------------------------------------------------------------------

needs_xfeat = pytest.mark.skipif(not XFEAT_WEIGHTS.exists(), reason="weights/xfeat.pt missing: python -m tools.fetch_models")


def textured(seed):
    rng = np.random.default_rng(seed)
    img = cv2.GaussianBlur(rng.integers(0, 255, (480, 640, 3), dtype=np.uint8), (0, 0), 2.0)
    for _ in range(40):                                                          # blobs and lines: corners for the detector
        cv2.circle(img, tuple(int(x) for x in rng.integers(20, 600, 2)), int(rng.integers(8, 30)), tuple(int(c) for c in rng.integers(0, 255, 3)), -1)
    return img


@needs_xfeat
def test_real_xfeat_recovers_a_warped_reference_and_its_bearing():
    ref, other = textured(1), textured(2)
    Hm = cv2.getRotationMatrix2D((320, 240), 8, 0.85)
    Hm[:, 2] += (50, -20)
    warped = cv2.warpAffine(ref, Hm, (640, 480))
    d = EntranceDetector(Camera(K), EntranceConfig(xfeat_top_k=1024), describer=object())   # DINOv2 is not used by the xfeat policy
    d.enroll_robot([ref], rois=[(160, 120, 480, 360)])
    r = d.detect(warped)
    expected = Hm @ [320, 240, 1]                                                # the ROI centre after the warp
    assert r.in_view and r.inliers >= 40
    assert abs(r.bearing_rad - (-math.atan((expected[0] - 320) / 300))) < 0.03
    assert not d.detect(other).in_view


@needs_xfeat
@pytest.mark.replay
def test_replay_on_the_classroom_door_meets_the_plan_thresholds():
    """T1 on data/D1 (not in git): robot reference + calibration from some negative positions, tested on the other positions."""
    ref_path, manifest = "data/D1/class_door_iref_robot.jpg", "data/D1/manifest_class_door.csv"
    if not (os.path.exists(ref_path) and os.path.exists(manifest)):
        pytest.skip("D1 classroom data not on this machine")
    rows = [r for r in csv.DictReader(open(manifest, encoding="utf-8")) if int(r["position_id"]) != 2]     # position 2 is the reference position
    neg_pos = sorted({int(r["position_id"]) for r in rows if r["door_visible"] == "no"})
    calib_pos = set(neg_pos[:2])
    read = lambda r: cv2.imread("data/D1/jetbot/" + r["frame_file"])
    d = EntranceDetector(Camera.from_json("calib/camera.json"), EntranceConfig())
    d.enroll_robot([cv2.imread(ref_path)])
    d.calibrate([read(r) for r in rows[::7] if int(r["position_id"]) in calib_pos])
    test = [r for r in rows[::9] if int(r["position_id"]) not in calib_pos]
    pos = [d.detect(read(r)).in_view for r in test if r["door_visible"] == "yes"]
    neg = [d.detect(read(r)).in_view for r in test if r["door_visible"] == "no"]
    assert len(pos) >= 40 and len(neg) >= 15
    assert np.mean(pos) >= 0.90 and np.mean(neg) <= 0.05, (np.mean(pos), np.mean(neg))


def test_config_toml_section_matches_the_defaults():
    from sentry.config import load
    assert EntranceConfig.from_toml(load()["entrance"]) == EntranceConfig()
