"""T0 unit tests for sentry/app/strike_eval.py and tools/evaluate_strike_false_triggers.py."""
import json
import pytest

from sentry.app.strike_eval import (
    BboxStrikeBaseline,
    StrikeEvalConfig,
    evaluate_false_triggers,
    evaluate_onsets,
    generate_synthetic_lunge_burst_stream,
    generate_synthetic_walking_stream,
)
from tools.evaluate_strike_false_triggers import main, run_synthetic_suite
from tools.label_events import EventRow, save_events


def test_config_loads_spec_values():
    cfg = StrikeEvalConfig.from_toml()
    assert cfg.strike_area_growth == 0.40
    assert cfg.strike_window_s == 0.10
    assert cfg.evade_duration_s == 0.40
    assert cfg.evade_cooldown_s == 1.00
    assert cfg.max_false_triggers_per_5min == 1.0


def test_bbox_baseline_uses_timestamp_window_not_frame_count():
    det = BboxStrikeBaseline(area_growth=0.40, window_s=0.10)
    # 100x200 = 20000 px^2 at t=0.0
    assert not det(0.0, {"bbox": (100, 100, 200, 300)})
    # Growth of +50% across 0.25 s (> 0.10 s window) must NOT trigger
    assert not det(0.25, {"bbox": (100, 100, 250, 300)})
    # Growth of +50% inside 0.05 s (<= 0.10 s window) MUST trigger
    assert det(0.30, {"bbox": (100, 100, 325, 300)})


def test_synthetic_10min_walking_passes_and_short_run_does_not_claim_t1_pass():
    short_stream = generate_synthetic_walking_stream(duration_s=60.0, fps=20.0, seed=1)
    short_res = evaluate_false_triggers(short_stream)
    assert short_res["evade_entries"] == 0
    assert short_res["limit_met"] is True
    assert short_res["protocol_complete"] is False
    assert short_res["t1_passed"] is False

    suite = run_synthetic_suite(duration_s=600.0, fps=20.0, seed=532)
    assert suite["t0_harness_passed"] is True
    assert suite["normal_walking_10min"]["t1_passed"] is True
    assert suite["normal_walking_10min"]["false_triggers_per_5min"] <= 1.0
    assert suite["lunge_burst_sanity"]["recall"] == 1.0


def test_cooldown_gating_and_rate_limit_failure():
    # 100 s stream with spikes:
    # - t=1.0 (accepted -> EVADE 1.0..1.4, cooldown 1.4..2.4)
    # - t=1.2 (suppressed during EVADE)
    # - t=1.8 (suppressed during cooldown)
    # - t=5.0 (accepted -> EVADE 5.0..5.4, cooldown 5.4..6.4)
    # 2 EVADE entries in 100 s = 6.0 / 5 min -> exceeds <= 1 / 5 min limit
    samples = [{"t": i * 0.1, "strike": (i in (10, 12, 18, 50))} for i in range(1001)]
    res = evaluate_false_triggers(samples)
    assert res["raw_strike_frames"] == 4
    assert res["evade_entries"] == 2
    assert res["cooldown_suppressed"] == 2
    assert res["false_triggers_per_min"] == pytest.approx(1.2, abs=1e-3)
    assert res["false_triggers_per_5min"] == pytest.approx(6.0, abs=1e-2)
    assert res["limit_met"] is False
    assert res["t1_passed"] is False


def test_events_csv_negative_intervals_and_onset_exclusion_with_cli(tmp_path):
    events_csv = tmp_path / "events.csv"
    rows = [
        EventRow(1, "lunge", "A", 5.0, "2026-11-26 08:10:00.000", 5.0, refined_t_local=5.0, valid=True),
        EventRow(2, "neg_start", "", 10.0, "2026-11-26 08:10:05.000", 10.0, valid=True),
        EventRow(3, "neg_end", "", 70.0, "2026-11-26 08:10:65.000", 70.0, valid=True),
    ]
    save_events(events_csv, rows)

    # True lunge at t=5.0 s, clean walking during 10..70 s, plus one false trigger at t=30 s
    pred_path = tmp_path / "preds.jsonl"
    preds = []
    for i in range(150):
        t = i * 0.5
        preds.append({"t": t, "strike": (t in (5.0, 30.0))})
    pred_path.write_text("\n".join(json.dumps(p) for p in preds) + "\n", encoding="utf-8")

    out_json = tmp_path / "report.json"
    rc = main(["--predictions", str(pred_path), "--events", str(events_csv), "--out", str(out_json)])
    assert rc == 1  # 1 false trigger in 60 s = 5 / 5 min > 1, and duration < 600 s
    data = json.loads(out_json.read_text(encoding="utf-8"))
    # Positive lunge at t=5.0 is outside negative interval 10..70, so only t=30.0 counts as false trigger
    assert data["false_triggers"]["evade_entries"] == 1
    assert data["false_triggers"]["duration_s"] == pytest.approx(60.0)
    assert data["onset_recall"]["recall"] == 1.0
    assert data["onset_recall"]["median_delay_ms"] == 0.0

    # Also test exclude_onsets mode directly
    res_ex = evaluate_false_triggers(preds, exclude_onsets=[5.0], exclude_window=(-0.5, 1.5))
    assert res_ex["evade_entries"] == 1
    assert res_ex["duration_s"] == pytest.approx(72.5)


def test_lunge_onset_matching_and_invalid_inputs(tmp_path):
    stream = generate_synthetic_lunge_burst_stream(duration_s=20.0, fps=20.0, onset_times=(4.0, 12.0))
    res = evaluate_onsets(stream, [4.0, 12.0])
    assert res["total_onsets"] == 2 and res["matched_onsets"] == 2
    assert res["recall"] == 1.0 and res["median_delay_ms"] is not None

    with pytest.raises(ValueError):
        evaluate_false_triggers([{"t": 0.0, "strike": False}])
    with pytest.raises(ValueError):
        evaluate_false_triggers([{"t": 2.0, "strike": False}, {"t": 1.0, "strike": False}])
    with pytest.raises(ValueError):
        evaluate_false_triggers([{"t": float("nan"), "strike": False}, {"t": 1.0, "strike": False}])

    out_syn = tmp_path / "syn.json"
    assert main(["--synthetic", "--out", str(out_syn)]) == 0
    assert json.loads(out_syn.read_text(encoding="utf-8"))["t0_harness_passed"] is True
