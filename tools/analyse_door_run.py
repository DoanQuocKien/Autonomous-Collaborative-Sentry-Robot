"""Summarize private door logs without inferring unavailable historical causes."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from tools.monitor_door import private_path


def read_rows(path):
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def quantiles(values):
    if not values:
        return None
    if not all(math.isfinite(v) for v in values):
        raise ValueError("finite measurements required")
    return dict(n=len(values), p50=float(np.median(values)), p95=float(np.percentile(values, 95)),
                maximum=float(max(values)))


def analyse(folder):
    folder = private_path(folder)
    metadata = json.loads((folder / "session.json").read_text(encoding="utf-8"))
    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    entries = read_rows(folder / "entries.jsonl")
    diagnostic_path = folder / "frames.jsonl"
    index_path = diagnostic_path if diagnostic_path.exists() else folder / "overlay_frames.jsonl"
    frames = read_rows(index_path) if index_path.exists() else []
    times = [r["receive_t"] for r in frames]
    if (any(not math.isfinite(t) for t in times)
            or any(b <= a for a, b in zip(times, times[1:]))):
        raise ValueError("strictly increasing finite processed-frame timestamps required")
    if len({r["entry_id"] for r in entries}) != len(entries):
        raise ValueError("duplicate entry IDs")
    gaps = [b - a for a, b in zip(times, times[1:])]
    gap_limit = metadata["settings"]["max_gap_s"]
    stages = {}
    for frame in frames:
        for key, value in frame.get("timings_ms", {}).items():
            stages.setdefault(key, []).append(value)
        if "consume_ms" in frame:
            stages.setdefault("consume", []).append(frame["consume_ms"])
    rejected_faces = Counter()
    rejected_associations = Counter()
    for frame in frames:
        rejected_faces.update(frame.get("sample_rejections", {}))
        rejected_associations.update(frame.get("association_rejections", {}))
    incomplete = []
    for number, row in enumerate(entries):
        if row["decision"] not in ("unresolved", "interrupted"):
            continue
        incomplete.append(dict(segment=number, decision=row["decision"], reason=row["reason"],
            end_trigger=row.get("end_trigger"), retained_face_samples=len(row["selected_faces"]),
            total_accepted_face_samples=row.get("total_accepted_face_samples"),
            confirmation_resets=row.get("confirmation_resets"),
            rejection_counts=row.get("sample_rejections"),
            duration_s=row["decision_t"] - row["first_seen_t"],
            stream_samples_in_time_window=sum(row["first_seen_t"] <= t <= row["decision_t"] for t in times),
            historical_rejection_details_available="sample_rejections" in row))
    files = [folder / name for name in ("session.json", "summary.json", "entries.jsonl")]
    if index_path.exists():
        files.append(index_path)
    return dict(schema_version=1, run_name=folder.name, requested_hz=metadata["settings"]["inference_hz"],
        recorded_summary=summary, decisions=dict(Counter(r["decision"] for r in entries)),
        logged_segments=len(entries), incomplete_segments=incomplete,
        cadence=dict(processed_samples=len(times), intervals_s=quantiles(gaps),
            effective_hz=(len(times) - 1) / (times[-1] - times[0]) if len(times) > 1 else None,
            after_first_interval_hz=(len(times) - 2) / (times[-1] - times[1]) if len(times) > 2 else None,
            large_processed_gaps=[dict(after_processed_sample=i, gap_s=gap)
                                  for i, gap in enumerate(gaps) if gap > gap_limit]),
        frame_diagnostics_available=diagnostic_path.exists(),
        stage_wall_ms={name: quantiles(values) for name, values in stages.items()},
        frame_sample_rejections=dict(rejected_faces), frame_association_rejections=dict(rejected_associations),
        source_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        t1_passed=False,
        interpretation="Processed-frame gaps alone do not identify network or inference causes. "
                       "Historical missing diagnostics remain unknown. Automatic segments require physical-attempt labels.")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    result = analyse(args.run_dir)
    with args.out.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps(dict(run=result["run_name"], decisions=result["decisions"],
                         cadence=result["cadence"], stage_wall_ms=result["stage_wall_ms"])))


if __name__ == "__main__":
    main()
