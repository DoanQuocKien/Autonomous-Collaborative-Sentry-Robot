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
    assert abs(door_vs_drive_deg(11.1, 361.0, 0.0) - 10.1) < 1e-6              # fd11: the door was nearly straight ahead (heading 361 deg = 1 deg): 10 deg, refused
    assert abs(door_vs_drive_deg(-90.0, 360.0, 0.0) + 90.0) < 1e-6             # door 90 deg to the right of the drive: ideal
    assert abs(door_vs_drive_deg(175.0, 0.0, 0.0) - 175.0) < 1e-6 and abs(door_vs_drive_deg(-175.0, 0.0, 0.0) + 175.0) < 1e-6


def test_clear_radius_scales_with_the_drive_command():
    from tools.drive_model import drive_distance_m, drive_speed_m_s
    from tools.find_door import max_baseline_s, required_clear_radius_m
    assert abs(drive_speed_m_s(0.85) - 0.35) < 1e-9 and abs(drive_speed_m_s(1.0) - 0.435) < 1e-9 and drive_speed_m_s(0.5) < drive_speed_m_s(0.85)
    assert required_clear_radius_m(10.0, 1.0) > required_clear_radius_m(10.0, 0.85)          # the audit case: a 10 s drive at v 1.0 needs more than at 0.85
    assert abs(required_clear_radius_m(10.0, 1.0) - (4.35 + 0.6)) < 1e-9
    assert abs(required_clear_radius_m(max_baseline_s(2.0, 1.0), 1.0) - 2.0) < 1e-9 and drive_distance_m(0.85, 5.5) > 1.9


import pytest


@pytest.mark.parametrize("tool, extra", [
    ("find_door", ["--clear-radius-m", "nan"]),
    ("find_door", ["--turn-deg", "90", "--clear-radius-m", "0.6", "--clear-ahead-m", "nan"]),
    ("find_door", ["--clear-radius-m", "inf"]),
    ("find_door", ["--clear-radius-m", "3", "--spin-s", "0.4"]),       # the fallback pulse angle is calibrated for 0.2 s only
    ("find_door", ["--clear-radius-m", "3", "--samples", "0"]),
    ("find_door", ["--clear-radius-m", "3", "--wait", "nan"]),
    ("approach_door", ["--door-range-m", "inf", "--path-clear"]),
    ("approach_door", ["--door-range-m", "nan", "--path-clear"]),
    ("approach_door", ["--door-range-m", "3", "--path-clear", "--max-steps", "0"]),
    ("approach_door", ["--door-range-m", "3", "--path-clear", "--stop-range=-inf"]),
    ("scan_boards", ["--spin-s", "0.3"]),
    ("scan_boards", ["--min-battery", "nan"]),
])
def test_a_bad_operator_value_aborts_before_any_live_setup(monkeypatch, tool, extra):
    """HNHL review of #108: NaN passed `clear_radius_m < required` and infinity passed the range bounds. A guard that let them through would
    reach the live setup, which opens the camera-pose file first (FileNotFoundError here), not a SystemExit."""
    import importlib
    import sys
    mod = importlib.import_module("tools." + tool)
    base = {"find_door": ["--entrance", "e"], "approach_door": ["--entrance", "e"], "scan_boards": []}[tool]
    monkeypatch.setattr(sys, "argv", [tool, "--label", "t", "--camera-pose", "missing_pose.json"] + base + extra)
    with pytest.raises(SystemExit, match="ABORT"):
        mod.main()


@pytest.mark.parametrize("tool, extra", [("find_door", ["--entrance", "e", "--clear-radius-m", "3"]), ("approach_door", ["--entrance", "e", "--door-range-m", "3", "--path-clear"])])
def test_good_values_pass_the_guards(monkeypatch, tool, extra):
    import importlib
    import sys
    mod = importlib.import_module("tools." + tool)
    monkeypatch.setattr(sys, "argv", [tool, "--label", "t", "--camera-pose", "missing_pose.json"] + extra)
    with pytest.raises(FileNotFoundError):                                # got past every guard to the first live step
        mod.main()
