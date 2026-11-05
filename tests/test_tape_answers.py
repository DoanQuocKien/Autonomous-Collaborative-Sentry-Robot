import json

import pytest

from tools.tape_answers import add_answers, clean, load_answers_file


def _run(tmp_path, answers):
    (tmp_path / "summary.json").write_text(json.dumps({"label": "t", "tape_answers": answers}))
    return tmp_path


def test_answers_are_merged_into_the_summary_with_the_offset_length(tmp_path):
    out = add_answers(_run(tmp_path, {"collisions": ""}), {"offset_x_forward_m": -0.18, "offset_y_left_m": 0.19, "collisions": 0, "door_distance_m_tape": None})
    assert json.loads((tmp_path / "summary.json").read_text())["tape_answers"] == out
    assert out["offset_m"] == 0.262 and out["collisions"] == 0 and "door_distance_m_tape" not in out


def test_blank_answers_stay_unanswered_and_a_later_partial_update_works(tmp_path):
    d = _run(tmp_path, {"offset_x_forward_m": "", "offset_y_left_m": "", "collisions": ""})
    out = add_answers(d, {"collisions": 0})
    assert out == {"collisions": 0} and "offset_m" not in out                       # blanks are not zeros, one coordinate gives no length
    out = add_answers(d, {"offset_x_forward_m": 0.3})
    assert "offset_m" not in out
    assert add_answers(d, {"offset_y_left_m": -0.4})["offset_m"] == 0.5


@pytest.mark.parametrize("bad", [{"offset_x_forward_m": float("nan")}, {"offset_y_left_m": float("inf")}, {"collisions": -1}, {"collisions": 1.5},
                                 {"door_distance_m_tape": -2}, {"line_of_sight_clear": "maybe"}, {"offset_x_forward_m": "abc"}])
def test_invalid_input_is_refused_and_the_file_is_left_untouched(tmp_path, bad):
    d = _run(tmp_path, {"collisions": 0})
    before = (tmp_path / "summary.json").read_text()
    with pytest.raises(ValueError):
        add_answers(d, bad)
    assert (tmp_path / "summary.json").read_text() == before


def test_an_answers_file_is_validated_before_a_run(tmp_path):
    with pytest.raises(ValueError, match="cannot read"):
        load_answers_file(tmp_path / "missing.json")
    (tmp_path / "bad.json").write_text("{not json")
    with pytest.raises(ValueError, match="cannot read"):
        load_answers_file(tmp_path / "bad.json")
    (tmp_path / "list.json").write_text("[1, 2]")
    with pytest.raises(ValueError, match="JSON object"):
        load_answers_file(tmp_path / "list.json")
    (tmp_path / "ok.json").write_text(json.dumps({"collisions": "0", "line_of_sight_clear": "Y", "offset_x_forward_m": ""}))
    assert load_answers_file(tmp_path / "ok.json") == {"collisions": 0, "line_of_sight_clear": "y"}
    assert clean({}) == {}
