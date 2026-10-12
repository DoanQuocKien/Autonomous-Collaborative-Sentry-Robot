import json

from tools.preflight import battery_status, newest_pose, tilt_status


def test_battery_thresholds_follow_the_jetbot_notes():
    assert battery_status(12.2) == "PASS" and battery_status(11.1) == "PASS"
    assert battery_status(10.8) == "WARN" and battery_status(10.4) == "FAIL"


def test_tilt_must_agree_with_the_stored_pose_within_1_5_deg():
    assert tilt_status(-2.0, -2.33)[0] == "PASS"
    st, d = tilt_status(1.0, -2.33)
    assert st == "FAIL" and abs(d - 3.33) < 1e-9


def test_newest_pose_file_wins_and_yawfix_files_are_ignored(tmp_path):
    import os
    a, b, c = (tmp_path / n for n in ("camera_pose_a.json", "camera_pose_b.json", "camera_pose_b_yawfix.json"))
    for f, p in ((a, 2.6), (b, -2.3), (c, 9.9)):
        f.write_text(json.dumps({"pitch_down_deg": p}))
    os.utime(a, (1, 1)); os.utime(b, (100, 100)); os.utime(c, (200, 200))
    name, pitch = newest_pose(str(tmp_path / "camera_pose_*.json"))
    assert name.endswith("camera_pose_b.json") and pitch == -2.3
    assert newest_pose(str(tmp_path / "nothing_*.json")) == (None, None)
