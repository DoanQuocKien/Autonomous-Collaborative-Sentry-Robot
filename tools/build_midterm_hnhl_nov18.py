"""Recompute the post-freeze dorm evidence from the reviewed Git sources."""
import csv
from io import StringIO
import hashlib
import json
import re
import subprocess

from tools.build_midterm_hnhl_nov16 import ROOT, pursuit_metrics

SOURCE = "506bb6b896c0081dacdd5e1725e715b0ca8011ce"
OUT = ROOT / "reports/HuynhNguyenHoaiLoc/midterm/update-2026-11-18.json"
PREFIX = "reports/DoanQuocKien/week-07/"


def collect(ref=SOURCE):
    sources = []

    def read(relative):
        path = PREFIX + relative
        data = subprocess.check_output(["git", "show", ref + ":" + path], cwd=ROOT)
        sources.append(dict(commit=ref, path=path, sha256=hashlib.sha256(data).hexdigest()))
        return data.decode("utf-8")

    range_rows = list(csv.DictReader(StringIO(read("tower_marker_range_1118/summary.csv"))))
    read("tower_marker_range_1118/README.md")
    for name in ("tower_a_reverse_2.csv", "tower_b_reverse_2.csv", "tower_c_reverse_2.csv"):
        read("tower_marker_range_1118/" + name)
    read("tower_avoid_1118/README.md")
    summary = json.loads(read("tower_avoid_1118/pursuit_e_summary.json"))
    rows = list(csv.DictReader(StringIO(read("tower_avoid_1118/pursuit_e_log.csv"))))
    metrics = pursuit_metrics(rows)
    for field, value in metrics.items():
        if field != "hold_frames" and summary[field] != value:
            raise ValueError("pursuit-e summary differs from CSV: " + field)
    events = summary["tower_avoid"]["events"]
    counts = {kind: sum(event["event"] == kind for event in events)
              for kind in ("TRIGGER", "DONE", "ABORT")}
    if counts["DONE"] != summary["tower_avoid"]["count"]:
        raise ValueError("tower completion count differs from event log")
    tower_frames = sum(row["mode"].startswith("TOWER_") for row in rows)
    if tower_frames != summary["frames_tower_avoid"]:
        raise ValueError("tower frame count differs from CSV")
    episodes = []
    for i, row in enumerate(rows):
        if row["mode"] != "SEARCH":
            continue
        if i == 0 or rows[i - 1]["mode"] != "SEARCH":
            episodes.append(dict(start_s=float(row["t"]), duration_s=0.0, frames=0))
        elapsed = min(float(rows[i + 1]["t"]) - float(row["t"]), 0.25) if i + 1 < len(rows) else 0.05
        episodes[-1]["duration_s"] += elapsed
        episodes[-1]["frames"] += 1
    for episode in episodes:
        episode["duration_s"] = round(episode["duration_s"], 3)
    pursuit_d = json.loads(read("tower_avoid_1118/pursuit_d_summary.json"))
    trace = read("tower_avoid_1118/motion_check_dorm_2.txt")
    pose = json.loads(read("tower_avoid_1118/camera_pose_self_1118_1.json"))
    read("tower_avoid_1118/tower_runs_summary.csv")
    return dict(
        date="2026-11-18", timezone="Asia/Bangkok", source_commit=ref,
        added_after_freeze="2026-11-16", sources=sources,
        marker_range=[dict(yaw_deg=float(row["yaw_deg"]), tape_end_m=float(row["end_tape_m"]),
                           last_pnp_m=float(row["event_range_m"]), last_side_px=float(row["event_side_px"]))
                      for row in range_rows],
        pursuit_e=dict(metrics=metrics, tower_events=counts, tower_frames=tower_frames,
                       unfinished_avoids=counts["TRIGGER"] - counts["DONE"] - counts["ABORT"],
                       hold_events=summary["hold_events"], search_episodes=episodes,
                       general_obstacle_detector_enabled=summary["obstacle_avoidance"],
                       range_source=summary["range_source"]),
        pursuit_d=dict(frames=pursuit_d["frames"], run_span_s=pursuit_d["run_span_s"],
                       completed_avoids=pursuit_d["tower_avoid"]["count"], csv_available=False),
        camera_pose=pose,
        motion=dict(measured_ratios=[float(value) for value in re.findall(r"\| ratio ([0-9.]+)", trace)],
                    fit_written="NOT WRITTEN" not in trace, check_failed="CHECK against" in trace and "FAIL" in trace),
        scope=dict(operator_tape_attribution="DQK", physical_contact_independently_verified=False,
                   robot_verification_after_review_fixes=False),
        acceptance=dict(pursuit_pd=False, hold_protocol=False, obstacle_avoidance=False,
                        d3_identity=False, independent_d5=False, automatic_map_vantage=False))


def main():
    result = collect()
    OUT.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(dict(sources=len(result["sources"]), pursuit=result["pursuit_e"]["metrics"])))


if __name__ == "__main__":
    main()
