"""Recompute the 16-Nov classroom evidence from pinned public Git files."""
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import subprocess

from sentry.config import DEFAULT_PATH

ROOT = DEFAULT_PATH.parent
OUT = ROOT / "reports/HuynhNguyenHoaiLoc/midterm/update-2026-11-16.json"
BASE = "4d3eff1743f0d185886473a94d77b5490c5f9b7c"
EVIDENCE = "ddfc31e112e6fd858505e8326ad561bdbe37c9fc"
REPORT = "b8e1f9f216a93360d71e759e15ec5faf723e8748"
FOLDER = "reports/DoanQuocKien/week-07/classroom_1116/"


def pursuit_metrics(rows):
    times = [float(row["t"]) for row in rows]
    if not times or any(not math.isfinite(t) for t in times):
        raise ValueError("finite pursuit timestamps required")
    if any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError("pursuit timestamps must increase")
    weights = [min(b - a, .25) for a, b in zip(times, times[1:])] + [.05]
    run_seconds = max(times[-1] - times[0] + .05, sum(weights))
    tracked = [(row, weight) for row, weight in zip(rows, weights) if row["yaw_err"]]
    ranged = [(row, weight) for row, weight in tracked if row["dist_m"]]
    tracked_seconds = sum(weight for _, weight in tracked)
    in_band_seconds = sum(weight for row, weight in ranged if abs(float(row["dist_m"]) - 1.2) <= .2)
    centred_seconds = sum(weight for row, weight in tracked if abs(float(row["yaw_err"])) / 2 <= .1)
    return dict(frames=len(rows), frames_with_distance=len(ranged),
                run_span_s=round(run_seconds, 2), observed_time_s=round(sum(weights), 2),
                tracked_time_s=round(tracked_seconds, 2),
                coverage_tracked_fraction=round(tracked_seconds / run_seconds, 3),
                time_fraction_distance_in_band_of_run=round(in_band_seconds / run_seconds, 3),
                time_fraction_centred_of_run=round(centred_seconds / run_seconds, 3),
                frames_obstacle_blocked=sum(row["obstacle_blocked"] == "1" for row in rows),
                reacquires=sum(row["event"] == "REACQUIRE" for row in rows),
                hold_frames=sum(row["mode"] == "HOLD" for row in rows))


def collect():
    sources = {}
    def read(ref, path):
        data = subprocess.check_output(["git", "show", ref + ":" + path], cwd=ROOT)
        sources[(ref, path)] = dict(commit=ref, path=path, sha256=hashlib.sha256(data).hexdigest())
        return data
    def document(path):
        return json.loads(read(EVIDENCE, FOLDER + path))
    def rows(path):
        return list(csv.DictReader(io.StringIO(read(EVIDENCE, FOLDER + path).decode("utf-8"))))

    deployment = document("deploy/t2_1116_1/summary.json")
    deploy_log = rows("deploy/t2_1116_1/log.csv")
    handshake_rows = rows("deploy/t2_1116_1/handshake.csv")
    if len(handshake_rows) != deployment["handshake"]["frames"]:
        raise ValueError("deployment handshake count differs from log")
    pursuit = document("pursuit/pursuit_1116_1/summary.json")
    metrics = pursuit_metrics(rows("pursuit/pursuit_1116_1/log.csv"))
    for field, value in metrics.items():
        if field != "hold_frames" and value != pursuit[field]:
            raise ValueError("pursuit summary differs from log: " + field)
    if metrics["hold_frames"] or pursuit["hold_events"]:
        raise ValueError("expected the documented zero-HOLD run")
    rehearsals = {}
    for run in ("rehearsal_1116_1", "rehearsal_1116_2", "rehearsal_1116_p1_1",
                "rehearsal_1116_p1_2", "rehearsal_1116_p2_1", "rehearsal_1116_p2b_1", "dry_1116_1"):
        summary = document("deploy/" + run + "/summary.json")
        rehearsals[run] = dict(success=summary["success"], frames=summary["handshake"]["frames"],
                               in_view_frames=summary["handshake"]["in_view_frames"])
    pose = document("calib/camera_pose_self_1116_3.json")
    root_pose = json.loads(read(EVIDENCE, "calib/camera_pose_self_1116_3.json"))
    if pose != root_pose:
        raise ValueError("session and root camera pose differ")
    for image in ("F3_devices_door_1116.png", "F3_devices_marker_1116.png"):
        read(EVIDENCE, "reports/DoanQuocKien/week-07/figures/" + image)
    read(EVIDENCE, FOLDER + "README.md")
    for path in ("reports/DoanQuocKien/midterm-chapter-03.md", "reports/DoanQuocKien/midterm-chapter-04.md",
                 "reports/DoanQuocKien/midterm-chapter-08.md", "docs/Mid-Term Report Plan.md",
                 "docs/Classroom Session 2026-11-19.md", "tools/plot_dqk_report_figures.py",
                 "reports/DoanQuocKien/week-07/figures/F17b_pursuit_1116.png"):
        read(REPORT, path)
    return dict(schema_version=1, date="2026-11-16", timezone="Asia/Bangkok", base_commit=BASE,
                evidence_commit=EVIDENCE, report_commit=REPORT, sources=list(sources.values()),
                deployment=dict(mode=deployment["mode"], chosen_vantage=deployment["chosen_vantage"],
                    success=deployment["success"], standby_s=deployment["state_changes"][-1][0],
                    handshake=deployment["handshake"], tape_answers=deployment["tape_answers"],
                    log_rows=len(deploy_log), counted_team_runs_reported=7),
                pursuit=dict(metrics=metrics, hold_events=pursuit["hold_events"],
                    distance_fraction_meets_08=metrics["time_fraction_distance_in_band_of_run"] >= .8,
                    centred_fraction_meets_08=metrics["time_fraction_centred_of_run"] >= .8,
                    range_source=pursuit["range_source"], tape_accuracy_verified=False),
                rehearsals=rehearsals, camera_pose=pose,
                owner_reported=dict(power_mode="5 W read at session end", reenrolment_dqk_tar=.930,
                    reenrolment_misses=21, reenrolment_raw_scores_committed=False,
                    estop_r1_cut_ms=10, estop_r1_motors_zero_after_log_ms=78,
                    estop_other_cut_ms=6, estop_other_motors_zero_after_log_ms=38,
                    estop_raw_logs_committed=False, remaining_video_shots="2026-11-19"),
                acceptance=dict(door_t1=False, automatic_map_vantage=False, pursuit_pd=False,
                    hold_protocol=False, independent_d5=False, d3_identity_accuracy=False, full_loop=False))


def main():
    result = collect()
    result["current_markdown_sha256_lf"] = {}
    for name in ("chapter-05-current.md", "chapter-07-rows.md", "code-appendix.md", "update-2026-11-16.md"):
        data = (OUT.parent / name).read_bytes().replace(b"\r\n", b"\n")
        result["current_markdown_sha256_lf"][name] = hashlib.sha256(data).hexdigest()
    OUT.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(dict(sources=len(result["sources"]), pursuit=result["pursuit"]["metrics"])))


if __name__ == "__main__":
    main()
