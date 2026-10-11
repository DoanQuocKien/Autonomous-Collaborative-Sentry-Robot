import math

import numpy as np

from tools.measure_camera_pose import fit_pose

FY, CY = 306.0, 239.0


def rows_for(H, pitch_deg, marks):
    p = math.radians(pitch_deg)
    return [CY + FY * math.tan(math.atan(H / d) - p) for d in marks]


def test_fit_recovers_height_and_tilt():
    marks = [0.3, 0.5, 0.75, 1.0, 1.5, 2.0]
    for H, pitch in [(0.105, 0.0), (0.11, 15.0), (0.10, 8.0)]:
        v = np.array(rows_for(H, pitch, marks)) + np.random.default_rng(0).normal(0, 0.7, len(marks))   # ~1 px click error
        h, p, rms, _ = fit_pose(v, marks, FY, CY)
        assert abs(h - H) < 0.01 and abs(p - pitch) < 1.5 and rms < 0.02, (H, pitch, h, p, rms)
