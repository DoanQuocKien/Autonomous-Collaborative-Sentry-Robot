"""T0 unit tests for tools/label_events.py (D4 keypress onset labeller)."""
import json
from pathlib import Path
import pytest

from tools.label_events import (
    EventRecorder,
    align_events_to_frames,
    apply_refined_shift,
    load_events,
    load_meta_frames,
    main,
    run_live_session,
    save_events,
    summarize_events,
)


def _make_clocks(start_wall=1700000000.0, start_perf=10.0, step=1.5):
    state = {"i": -1}

    def wall():
        state["i"] += 1
        return start_wall + state["i"] * step

    def perf():
        return start_perf + state["i"] * step

    return wall, perf


def test_keypress_session_records_lunges_claps_invalidations_and_segments(tmp_path):
    csv_path = tmp_path / "events.csv"
    wall, perf = _make_clocks(start_wall=1700000000.0, start_perf=5.0, step=2.0)
    rec = EventRecorder(csv_path, initial_set="A", wall_clock=wall, perf_clock=perf)

    keys = iter([
        "c",        # clap sync at t=0
        " ",        # lunge #1 in Set A
        "x",        # mark lunge #1 invalid (e.g. stumbled)
        "l",        # lunge #2 in Set A (replacement)
        "2",        # switch to Set B
        "\n",       # lunge #3 in Set B
        "C",        # switch to Set C (uppercase C)
        " ",        # lunge #4 in Set C
        "n",        # neg_start
        "n",        # neg_end
        "h",        # hard_neg_start
        "h",        # hard_neg_end
        "q",        # quit
    ])
    logs = []
    summary = run_live_session(rec, read_key=lambda: next(keys), output=logs.append)

    loaded = load_events(csv_path)
    assert [r.label for r in loaded] == [
        "clap",
        "lunge",
        "lunge",
        "lunge",
        "lunge",
        "neg_start",
        "neg_end",
        "hard_neg_start",
        "hard_neg_end",
    ]
    assert [r.event_id for r in loaded] == list(range(1, 10))
    assert loaded[1].valid is False and "invalid" in loaded[1].notes
    assert loaded[2].valid is True and loaded[2].set_id == "A"
    assert loaded[3].set_id == "B"
    assert loaded[4].set_id == "C"
    assert all(r.refined_t_local is None for r in loaded)
    assert summary["valid_lunges"] == 3
    assert summary["invalid_lunges"] == 1
    assert summary["claps"] == 1
    assert summary["valid_by_set"] == {"A": 1, "B": 1, "C": 1, "D": 0, "E": 0, "F": 0}
    assert summary["negative_duration_s"] == pytest.approx(2.0)
    assert summary["hard_negative_duration_s"] == pytest.approx(2.0)


def test_resume_appends_ids_and_preserves_open_negative_segment(tmp_path):
    csv_path = tmp_path / "events.csv"
    t = {"w": 100.0, "p": 1.0}
    rec1 = EventRecorder(csv_path, wall_clock=lambda: t["w"], perf_clock=lambda: t["p"])
    rec1.handle_key(" ")
    t["w"] += 1.0
    t["p"] += 1.0
    rec1.handle_key("n")  # opens neg_start

    t["w"] += 10.0
    t["p"] += 10.0
    rec2 = EventRecorder(csv_path, wall_clock=lambda: t["w"], perf_clock=lambda: t["p"])
    action, row = rec2.handle_key("n")  # should close with neg_end
    assert action == "recorded" and row is not None and row.label == "neg_end"
    assert row.event_id == 3

    summary = summarize_events(load_events(csv_path))
    assert summary["negative_duration_s"] == pytest.approx(10.0)


def test_shift_refined_and_align_to_jetbot_meta(tmp_path):
    csv_path = tmp_path / "events.csv"
    meta_path = tmp_path / "jetbot_meta.jsonl"
    frames = [
        {"seq": i, "t_cap": 100.0 + i * 0.05, "t_local": 1000.0 + i * 0.05, "file": f"{i:06d}.jpg"}
        for i in range(40)
    ]
    meta_path.write_text("\n".join(json.dumps(f) for f in frames) + "\n", encoding="utf-8")

    # Raw press lagged by +0.25 s relative to actual onset at t_local=1000.50
    t_vals = iter([1000.75, 1001.25])
    rec = EventRecorder(csv_path, wall_clock=lambda: next(t_vals), perf_clock=lambda: 1.0)
    rec.handle_key(" ")
    rec.handle_key(" ")

    # Shift refined timestamps by -0.25 s via CLI
    assert main(["--out", str(csv_path), "--shift-refined", "-0.25"]) == 0
    rows = load_events(csv_path)
    assert rows[0].t_local == pytest.approx(1000.75)
    assert rows[0].refined_t_local == pytest.approx(1000.50)
    assert rows[1].refined_t_local == pytest.approx(1001.00)

    # Align to jetbot_meta.jsonl via CLI
    aligned_path = tmp_path / "events_aligned.csv"
    assert main(["--out", str(csv_path), "--align", str(meta_path), "--aligned-out", str(aligned_path)]) == 0
    text = aligned_path.read_text(encoding="utf-8")
    assert "000010.jpg" in text and "000020.jpg" in text

    aligned = align_events_to_frames(rows, load_meta_frames(meta_path))
    assert aligned[0]["frame_seq"] == "10" and abs(float(aligned[0]["dt_ms"])) < 1e-3
    assert aligned[1]["frame_seq"] == "20" and abs(float(aligned[1]["dt_ms"])) < 1e-3


def test_invalid_inputs_rejected(tmp_path):
    with pytest.raises(ValueError):
        EventRecorder(tmp_path / "e.csv", initial_set="Z")
    with pytest.raises(ValueError):
        apply_refined_shift([], float("nan"))
    with pytest.raises(ValueError):
        align_events_to_frames([], [])
    save_events(tmp_path / "empty.csv", [])
    assert main(["--out", str(tmp_path / "empty.csv"), "--summary"]) == 0
