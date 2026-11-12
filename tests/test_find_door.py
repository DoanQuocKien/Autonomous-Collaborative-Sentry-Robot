import math

from tools.find_door import dominant_bearing


def test_dominant_cluster_beats_the_median_of_false_sightings():
    true = [(math.radians(-48 + d), 30) for d in (-2, -1, 0, 1, 2, 0, 1)]                 # the door, seen at several stops
    false = [(math.radians(a), 28) for a in (140, 262, 175, 100)]                           # the detector firing elsewhere
    b, n, total, second = dominant_bearing(true + false)
    assert abs(b - (-48)) < 2 and n == 7 and total == 11 and second <= 1


def test_wraps_around_180_and_handles_none():
    d = [(math.radians(a), 30) for a in (178, -179, 179, -178)]
    b, n, _, _ = dominant_bearing(d)
    assert n == 4 and abs(abs(b) - 180) < 2
    assert dominant_bearing([]) == (None, 0, 0, 0)


def test_baseline_turn_is_across_the_line_of_sight_the_short_way():
    from tools.find_door import baseline_turn_deg
    assert abs(baseline_turn_deg(0.0, 0.0, "left") - 90) < 1e-9 and abs(baseline_turn_deg(0.0, 0.0, "right") + 90) < 1e-9
    assert abs(baseline_turn_deg(113.5, 373.7, "left") - (-170.2)) < 1e-6          # heading 373.7 = 13.7 deg; target 203.5 deg: the short way is 170.2 deg to the RIGHT


def test_clear_radius_rules():
    from tools.find_door import max_baseline_s, required_clear_radius_m
    assert abs(required_clear_radius_m(5.5) - (5.5 * 0.35 + 0.6)) < 1e-9 and required_clear_radius_m(5.5) > 2.5     # 1.9 m were driven in 5.6 s on 2026-11-12
    assert abs(max_baseline_s(1.2) - (0.6 / 0.35)) < 1e-9 and max_baseline_s(0.5) == 0.0
    assert abs(required_clear_radius_m(max_baseline_s(2.0)) - 2.0) < 1e-9


def test_door_vs_drive_angle():
    from tools.find_door import door_vs_drive_deg
    assert abs(door_vs_drive_deg(11.1, 361.0, 0.0) - 11.1) < 1e-6              # fd11: the door was nearly straight ahead: refused
    assert abs(door_vs_drive_deg(-90.0, 360.0, 0.0) + 90.0) < 1e-6             # door 90 deg to the right of the drive: ideal
    assert abs(door_vs_drive_deg(175.0, 0.0, 0.0) - 175.0) < 1e-6 and abs(door_vs_drive_deg(-175.0, 0.0, 0.0) + 175.0) < 1e-6
