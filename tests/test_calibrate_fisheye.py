import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

from tools.calibrate_fisheye import board_points, calibrate

K_TRUE = np.array([[310.0, 0, 320.0], [0, 306.0, 240.0], [0, 0, 1.0]])
D_TRUE = np.array([[-0.03], [-0.001], [-0.005], [0.0015]])


def synthetic_views(n=25, noise=0.2, seed=532):
    """Boards in random poses seen through a known fisheye model, with pixel noise; only views fully inside 640x480."""
    rng = np.random.RandomState(seed)
    obj1 = board_points()
    obj, img = [], []
    while len(img) < n:
        rvec = rng.uniform(-0.7, 0.7, (3, 1))
        tvec = np.array([[rng.uniform(-0.15, 0.1)], [rng.uniform(-0.1, 0.1)], [rng.uniform(0.3, 0.9)]])
        pts, _ = cv2.fisheye.projectPoints(obj1.astype(np.float64), rvec, tvec, K_TRUE, D_TRUE)
        if pts[..., 0].min() > 5 and pts[..., 0].max() < 635 and pts[..., 1].min() > 5 and pts[..., 1].max() < 475:
            obj.append(obj1)
            img.append(pts + rng.normal(0, noise, pts.shape))
    return obj, img


def test_recovers_a_known_lens_from_noisy_views():
    obj, img = synthetic_views()
    res = calibrate(obj, img, (640, 480))
    assert res["rms"] < 0.4
    assert abs(res["K"][0, 0] - 310) < 3 and abs(res["K"][0, 2] - 320) < 3 and abs(res["K"][1, 2] - 240) < 3


def test_a_corrupted_view_is_dropped_and_reported():
    obj, img = synthetic_views()
    img[3] = img[3] + np.random.RandomState(1).normal(0, 6.0, img[3].shape)  # a "bent board" view
    res = calibrate(obj, img, (640, 480))
    assert 3 in res["dropped"] and res["rms"] < 0.5


@pytest.mark.replay
@pytest.mark.skipif(not Path("data/D1/checkerboard").exists(), reason="needs data/D1/checkerboard (not in git)")
def test_real_photos_meet_the_plan_target(tmp_path):
    out, metrics = tmp_path / "camera.json", tmp_path / "metrics.json"
    r = subprocess.run([sys.executable, "-m", "tools.calibrate_fisheye", "--out", str(out), "--metrics", str(metrics)], capture_output=True, text=True)
    m = json.loads(metrics.read_text())
    assert r.returncode == 0 and m["rms_px"] < 1.0, r.stdout
    assert abs(m["stability"][0]["fx"] - m["stability"][1]["fx"]) < 10  # the two halves agree
