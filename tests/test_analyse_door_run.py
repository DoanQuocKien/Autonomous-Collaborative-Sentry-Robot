import json

import pytest

from tools import analyse_door_run, monitor_door


@pytest.fixture
def run_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(monitor_door, "ROOT", tmp_path)
    folder = tmp_path / "data/run"
    folder.mkdir(parents=True)
    (folder / "session.json").write_text(json.dumps(dict(settings=dict(max_gap_s=1, inference_hz=5))))
    (folder / "summary.json").write_text(json.dumps(dict(status="completed")))
    entry = dict(entry_id="a", decision="unresolved", reason="insufficient_face_evidence",
                 selected_faces=[], first_seen_t=0., decision_t=2.)
    (folder / "entries.jsonl").write_text(json.dumps(entry) + "\n")
    return folder


def test_historical_missing_diagnostics_stay_unknown(run_dir):
    rows = [dict(seq=i, receive_t=t) for i, t in enumerate([0., .25, 1.75])]
    (run_dir / "overlay_frames.jsonl").write_text("\n".join(map(json.dumps, rows)))
    result = analyse_door_run.analyse(run_dir)
    assert result["cadence"]["intervals_s"]["maximum"] == 1.5
    assert result["cadence"]["large_processed_gaps"] == [dict(after_processed_sample=1, gap_s=1.5)]
    assert result["frame_diagnostics_available"] is False and result["stage_wall_ms"] == {}
    assert result["incomplete_segments"][0]["rejection_counts"] is None
    assert result["t1_passed"] is False


def test_frame_timing_aggregation_and_output_protection(run_dir, tmp_path):
    rows = [dict(seq=i, receive_t=i * .2, timings_ms=dict(process=10., face=4.),
                 sample_rejections=dict(blurred_face=1), association_rejections={}) for i in range(3)]
    path = run_dir / "frames.jsonl"
    path.write_text("\n".join(map(json.dumps, rows)))
    result = analyse_door_run.analyse(run_dir)
    assert result["cadence"]["effective_hz"] == 5
    assert result["stage_wall_ms"]["process"]["p95"] == 10
    assert result["frame_sample_rejections"] == dict(blurred_face=3)
    output = tmp_path / "report.json"
    output.write_text("original")
    with pytest.raises(FileExistsError):
        analyse_door_run.main(["--run-dir", str(run_dir), "--out", str(output)])
    assert output.read_text() == "original"
    rows[1]["receive_t"] = 0.
    path.write_text("\n".join(map(json.dumps, rows)))
    with pytest.raises(ValueError, match="increasing"):
        analyse_door_run.analyse(run_dir)
