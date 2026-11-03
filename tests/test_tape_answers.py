import json

from tools.tape_answers import add_answers


def test_answers_are_merged_into_the_summary_with_the_offset_length(tmp_path):
    (tmp_path / "summary.json").write_text(json.dumps({"label": "t", "tape_answers": {"collisions": ""}}))
    out = add_answers(tmp_path, {"offset_x_forward_m": -0.18, "offset_y_left_m": 0.19, "collisions": 0, "door_distance_m_tape": None})
    saved = json.loads((tmp_path / "summary.json").read_text())["tape_answers"]
    assert saved == out and out["offset_m"] == 0.262 and out["collisions"] == 0 and "door_distance_m_tape" not in out
