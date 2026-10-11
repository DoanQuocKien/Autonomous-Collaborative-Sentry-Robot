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


def test_centre_row_ignores_where_on_a_tilted_strip_you_click():
    from tools.measure_camera_pose import centre_rows
    rows, slopes, roll = centre_rows([(100, 210), (500, 190), (50, 300), (600, 300)], 300)   # no cy: no roll correction
    assert abs(rows[0] - 200) < 1e-9 and abs(rows[1] - 300) < 1e-9 and abs(slopes[0] + 2.86) < 0.01 and roll == 0


def test_camera_roll_is_measured_and_removed():
    from tools.measure_camera_pose import centre_rows
    a = math.radians(6)   # every strip slants 6 deg: a rolled camera; strips at rows 100 and 200 once derotated
    def rot(x, y): return 300 + math.cos(a) * (x - 300) - math.sin(a) * (y - 240), 240 + math.sin(a) * (x - 300) + math.cos(a) * (y - 240)
    pts = [rot(x, y) for y in (100, 200) for x in (50, 550)]
    rows, slopes, roll = centre_rows(pts, 300, 240)
    assert abs(roll - 6) < 1e-6 and abs(rows[0] - 100) < 1e-6 and abs(rows[1] - 200) < 1e-6


def test_click_order_does_not_matter():
    from tools.measure_camera_pose import centre_rows
    a = centre_rows([(100, 210), (500, 190), (600, 300), (50, 300)], 300, 240)   # second strip clicked right end first
    b = centre_rows([(500, 190), (100, 210), (50, 300), (600, 300)], 300, 240)
    assert a[0] == b[0] and all(abs(x) < 15 for x in a[1])
