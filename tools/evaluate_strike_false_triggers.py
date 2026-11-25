"""False-trigger evaluation CLI for strike detection (`Implementation Plan.md` §4.3, Week 8).

Acceptance target (`Implementation Plan.md` §4.3):
    <= 1 false trigger / 5 min of walking (<= 0.20 / min); recall >= 90 % on D4.

Modes:
  1. Synthetic T0 benchmark (no GPU/dataset needed):
     python -m tools.evaluate_strike_false_triggers --synthetic \\
         --out reports/kouun-rokku/week-08/strike_false_trigger_harness.json

  2. Recorded D4 predictions JSONL (+ optional label_events.py CSV):
     python -m tools.evaluate_strike_false_triggers \\
         --predictions data/D4/pose_predictions.jsonl \\
         --events data/D4/events.csv \\
         --out reports/kouun-rokku/week-08/d4_false_triggers.json

  3. Recorded D4 predictions with explicit pluggable detector callable (`module:attr`):
     python -m tools.evaluate_strike_false_triggers \\
         --predictions data/D4/tracks.jsonl \\
         --detector sentry.perception.pose:LungeDetector \\
         --events data/D4/events.csv \\
         --out reports/kouun-rokku/week-08/d4_false_triggers.json
"""
import argparse
import importlib
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from sentry.app.strike_eval import (
    BboxStrikeBaseline,
    StrikeEvalConfig,
    evaluate_false_triggers,
    evaluate_onsets,
    generate_synthetic_lunge_burst_stream,
    generate_synthetic_walking_stream,
)
from tools.label_events import extract_intervals, load_events


def load_predictions_jsonl(path: Path) -> List[Dict[str, Any]]:
    path = Path(path)
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def load_detector_callable(spec: str) -> Callable[[float, Dict[str, Any]], bool]:
    """Load `module.path:attribute` and instantiate if it is a class."""
    if ":" not in spec:
        raise ValueError(f"detector spec must be 'module:callable', got {spec!r}")
    mod_name, attr_name = spec.split(":", 1)
    mod = importlib.import_module(mod_name)
    obj = getattr(mod, attr_name)
    if isinstance(obj, type):
        obj = obj()
    if not callable(obj):
        raise TypeError(f"loaded detector {spec!r} is not callable")
    return obj


def _events_constraints(
    events_path: Optional[Path],
    *,
    exclude_window: Tuple[float, float] = (-0.5, 1.5),
) -> Tuple[Optional[List[Tuple[float, float]]], List[float]]:
    if events_path is None:
        return None, []
    rows = load_events(events_path)
    neg_intervals = extract_intervals(rows, "neg_start", "neg_end")
    hard_intervals = extract_intervals(rows, "hard_neg_start", "hard_neg_end")
    combined_neg = (neg_intervals + hard_intervals) or None
    onsets = [r.effective_t() for r in rows if r.label == "lunge" and r.valid]
    return combined_neg, onsets


def run_synthetic_suite(
    duration_s: float = 600.0,
    fps: float = 20.0,
    seed: int = 532,
) -> Dict[str, Any]:
    """Run T0 synthetic walking + cooldown gating + lunge sanity checks."""
    cfg = StrikeEvalConfig.from_toml()
    walking = generate_synthetic_walking_stream(duration_s=duration_s, fps=fps, seed=seed)
    walk_res = evaluate_false_triggers(
        walking,
        detector=BboxStrikeBaseline(cfg.strike_area_growth, cfg.strike_window_s),
        cfg=cfg,
    )

    burst_onsets = (5.0, 15.0, 25.0)
    burst_stream = generate_synthetic_lunge_burst_stream(duration_s=30.0, fps=fps, onset_times=burst_onsets)
    onset_res = evaluate_onsets(
        burst_stream,
        burst_onsets,
        detector=BboxStrikeBaseline(cfg.strike_area_growth, cfg.strike_window_s),
        cfg=cfg,
    )

    # Stress check: repeated synthetic false spikes 0.2 s apart must be gated by 1.0 s cooldown
    spike_stream = [{"t": i * 0.05, "strike": (i in (20, 24, 28, 60))} for i in range(200)]
    spike_res = evaluate_false_triggers(spike_stream, cfg=cfg)

    return {
        "evaluation_tier": "T0_SYNTHETIC_HARNESS",
        "detector_used": "BboxStrikeBaseline(dA/A > %.2f in %.2fs)" % (cfg.strike_area_growth, cfg.strike_window_s),
        "config": {
            "strike_area_growth": cfg.strike_area_growth,
            "strike_window_s": cfg.strike_window_s,
            "evade_duration_s": cfg.evade_duration_s,
            "evade_cooldown_s": cfg.evade_cooldown_s,
            "max_false_triggers_per_5min": cfg.max_false_triggers_per_5min,
        },
        "normal_walking_10min": walk_res,
        "lunge_burst_sanity": onset_res,
        "cooldown_gating_sanity": {
            "raw_strike_frames": spike_res["raw_strike_frames"],
            "evade_entries": spike_res["evade_entries"],
            "cooldown_suppressed": spike_res["cooldown_suppressed"],
        },
        "t0_harness_passed": bool(
            walk_res["limit_met"]
            and walk_res["protocol_complete"]
            and onset_res["recall_met"]
            and spike_res["evade_entries"] == 2
            and spike_res["cooldown_suppressed"] == 2
        ),
        "note": (
            "T0 synthetic benchmark only; does NOT establish D4 T1 acceptance "
            "until run on recorded D4 video with HNHL's pose/lunge detector."
        ),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--synthetic", action="store_true", help="Run deterministic T0 synthetic walking benchmark")
    ap.add_argument("--duration", type=float, default=600.0, help="Synthetic walking duration in seconds (default 600)")
    ap.add_argument("--predictions", type=Path, default=None, help="Frame predictions JSONL for D4 evaluation")
    ap.add_argument("--events", type=Path, default=None, help="Optional label_events.py CSV for negative intervals / onsets")
    ap.add_argument("--detector", default=None, help="Optional pluggable detector 'module:callable'")
    ap.add_argument("--out", type=Path, default=None, help="Write JSON evaluation report here")
    args = ap.parse_args(argv)

    if not args.synthetic and args.predictions is None:
        ap.error("pass either --synthetic or --predictions <jsonl>")

    if args.synthetic:
        report = run_synthetic_suite(duration_s=args.duration)
        ok = report["t0_harness_passed"]
    else:
        cfg = StrikeEvalConfig.from_toml()
        samples = load_predictions_jsonl(args.predictions)
        det = load_detector_callable(args.detector) if args.detector else None
        neg_intervals, onsets = _events_constraints(args.events)
        neg_res = evaluate_false_triggers(
            samples,
            detector=det,
            cfg=cfg,
            negative_intervals=neg_intervals,
            exclude_onsets=onsets if (onsets and neg_intervals is None) else None,
        )
        pos_res = evaluate_onsets(samples, onsets, detector=det, cfg=cfg) if onsets else None
        report = {
            "evaluation_tier": "T1_OFFLINE_RECORDING",
            "predictions_file": str(args.predictions),
            "events_file": str(args.events) if args.events else None,
            "detector_used": args.detector or "precomputed_or_BboxStrikeBaseline",
            "false_triggers": neg_res,
            "onset_recall": pos_res,
            "t1_passed": bool(neg_res["t1_passed"] and (pos_res["recall_met"] if pos_res else True)),
        }
        ok = report["t1_passed"]

    text = json.dumps(report, indent=2, allow_nan=False) + "\n"
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
