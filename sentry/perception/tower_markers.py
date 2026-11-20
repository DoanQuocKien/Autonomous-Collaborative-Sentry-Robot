"""The four ArUco markers (DICT_4X4_50, 50 mm black square) on the ESP32 tower, with the heights measured on 2026-11-20 (tape, cm above the floor).

Each marker was taped slightly diagonal, so both lower corners were measured: `le` / `re` = the left / right end of the square's lower edge as seen facing that face.
Height used for the camera pose = the mean (the lower edge's centre); `tilt_deg` = the marker's in-plane tilt, atan((re - le) / side), positive = right end higher.
Remeasure and edit here if a marker is re-taped."""
import math

MARKER_M = 0.05
# id: (side, le_m, re_m); the back is id 10, the front id 11 (printed upside down), right id 12, left id 13 (sides as seen looking from the back to the front)
TOWER = {10: ("back", 0.006, 0.005), 11: ("front", 0.005, 0.004), 12: ("right", 0.006, 0.010), 13: ("left", 0.005, 0.005)}


def bottom_h(marker_id):
    """Height of the lower edge's centre above the floor (m)."""
    _, le, re = TOWER[marker_id]
    return (le + re) / 2.0


def tilt_deg(marker_id):
    """In-plane tilt of the marker from the measured edge heights (deg, + = right end higher)."""
    _, le, re = TOWER[marker_id]
    return math.degrees(math.atan2(re - le, MARKER_M))


class PlacementGate(object):
    """Is the tower (its BACK marker, id 10, toward the robot) standing in front of the robot? Fed with marker_range()'s (range_m, bearing_deg) of every robot frame, or None.
    `ok(now)` is True once the back marker has been inside the range and bearing window for `hold_s` seconds without a gap, and stays True while it is still seen (`fresh_s`).
    Range is the camera-to-marker floor distance by PnP (it read 0.23 m for a tape 0.20 m on 2026-11-20: window 0.2-0.3 m)."""

    def __init__(self, range_m=(0.2, 0.3), bearing_deg=15.0, hold_s=1.0, fresh_s=0.7):
        self.lo, self.hi, self.bmax, self.hold_s, self.fresh_s = range_m[0], range_m[1], bearing_deg, hold_s, fresh_s
        self.t_start = self.t_last = None
        self.frames = self.frames_in = 0
        self.last = None

    def update(self, t, mr):
        self.frames += 1
        self.last = mr
        inside = mr is not None and self.lo <= mr[0] <= self.hi and abs(mr[1]) <= self.bmax
        if not inside:
            if mr is not None or self.t_last is None or t - self.t_last > self.fresh_s:
                self.t_start = self.t_last = None      # seen but outside the window (moved, knocked over): revoke at once; a frame with no marker is only a dropout (fresh_s)
            return
        self.frames_in += 1
        if self.t_start is None or t - self.t_last > self.fresh_s:
            self.t_start = t
        self.t_last = t

    def ok(self, now):
        return self.t_start is not None and now - self.t_last <= self.fresh_s and self.t_last - self.t_start >= self.hold_s

    def summary(self):
        return dict(range_m=[self.lo, self.hi], bearing_deg=self.bmax, hold_s=self.hold_s, frames=self.frames, frames_in_window=self.frames_in,
                    last=None if self.last is None else [round(self.last[0], 3), round(self.last[1], 1)])
