"""Range to a person from the size of the shoulder-to-hip trunk (pose keypoints) and a population prior: no floor, no depth model, no per-person constant.

Pinhole model on the RECTIFIED image: a vertical segment of length T at camera depth Z has the pixel length f * T / Z, so Z = f * T / px. With the camera pitch the
forward distance is Z * (cos p - sin p * y) with y the normalised image row of the trunk centre, and left = -Z * x (x the normalised column, ignoring roll).
The prior (about 0.50 m for adults, about +/- 6 % in the literature) is a population value, not tuned on one person; on the saved single-person sets the error was
-0.02 to +0.16 m at 1.25-1.8 m (reports/DoanQuocKien/week-06/classroom_1109/README.md): a lead, not an accepted ranging method.
"""
import math

import numpy as np

SHOULDER_L, SHOULDER_R, HIP_L, HIP_R = 5, 6, 11, 12          # COCO keypoint indices


def iou(a, b):
    x1, y1, x2, y2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def trunk_range(kxy, kconf, undistort_points, K, pitch, trunk_m=0.50, conf_min=0.8, min_px=8.0):
    """kxy: (17, 2) raw pixels, kconf: (17,). -> (forward_m, left_m) or None when a trunk keypoint is not confident or the trunk is too small to measure."""
    idx = (SHOULDER_L, SHOULDER_R, HIP_L, HIP_R)
    if len(kxy) < 13 or min(float(kconf[i]) for i in idx) < conf_min:
        return None
    p = np.asarray(undistort_points(np.asarray(kxy, dtype=float)[list(idx)]), dtype=float).reshape(-1, 2)
    shoulders, hips = (p[0] + p[1]) / 2.0, (p[2] + p[3]) / 2.0
    px = float(np.linalg.norm(shoulders - hips))
    if not math.isfinite(px) or px < min_px:
        return None
    z = K[0, 0] * trunk_m / px
    mid = (shoulders + hips) / 2.0
    x, y = (mid[0] - K[0, 2]) / K[0, 0], (mid[1] - K[1, 2]) / K[1, 1]
    forward = z * (math.cos(pitch) - math.sin(pitch) * y)
    return (forward, -z * x) if forward > 0 else None
