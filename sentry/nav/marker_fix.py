"""Marker pose fixes for the live deployment: the robot pose (x, y, yaw) in the room frame from the ArUco boards in view, against anchors measured with the tape.

Why: on 2026-10-30 the dead-reckoned deployment ended 0.8 m from the sweet spot with the camera turned the wrong way (an unlevel floor: the turns and drift of the model are wrong, see tools/motion_check.py).
The robot's own video sees the boards, so the pose is corrected while the robot is still or driving straight (tools/deploy_live.py applies the fixes).
Noise: a 150 mm board's orientation is noisy beyond about 1.5 m (a still robot read yaws of -22 to +17 deg and lateral jumps of 0.6 m at 2 m on 2026-10-30), so the fix is the median of the last few
measurements and boards beyond `max_range_m` (1.5) are ignored.
"""
import collections
import math

import numpy as np


def _wrap(a):
    return math.atan2(math.sin(a), math.cos(a))


class MarkerFix(object):
    def __init__(self, anchors_csv, camera_calib="calib/camera.json", max_range_m=1.5, median_n=5):
        from sentry.nav.localization import LocalizationTracker, RobotPose
        self._pose0 = RobotPose
        # the tracker blends toward its current pose beyond 0.8 m unless its own range limit is huge: the limit is applied here instead
        self.tr = LocalizationTracker(motion_calib=None, camera_calib=camera_calib, max_marker_distance_m=1e6)
        self.tr.load_anchors_csv(anchors_csv)
        self.anchors = dict(self.tr.anchors)
        self.max_range_m = max_range_m
        self.recent = collections.deque(maxlen=median_n)
        self.n = 0                                      # counts published fixes

    def measure(self, frame_bgr):
        """-> (n, x, y, yaw, distance_m) of the median over the last measurements, or None when no known board is in range in this frame."""
        near = {d.marker_id: d.distance_m for d in self.tr.detect_markers(frame_bgr) if d.marker_id in self.anchors and d.distance_m <= self.max_range_m}
        if not near:
            return None
        self.tr.anchors = {k: self.anchors[k] for k in near}
        self.tr.pose, self.tr.corrections_count = self._pose0(), 0           # a fresh start: no jump rejection, no blending
        try:
            self.tr.update_with_markers(frame_bgr, alpha=1.0)
        finally:
            self.tr.anchors = self.anchors
        if not self.tr.corrections_count:
            return None
        p = self.tr.pose
        self.recent.append((p.x, p.y, p.theta, min(near.values())))
        a = np.array(self.recent)
        ref = a[0, 2]
        yaw = _wrap(ref + float(np.median([_wrap(t - ref) for t in a[:, 2]])))
        self.n += 1
        return self.n, float(np.median(a[:, 0])), float(np.median(a[:, 1])), yaw, float(a[-1, 3])
