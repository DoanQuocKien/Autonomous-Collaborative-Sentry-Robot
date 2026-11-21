"""Recompute 20-Nov diagnostics and existing F7 evidence for HNHL's addendum.

Reads immutable Git sources and a dated GitHub metadata snapshot. No inference,
camera connection or motor commands. Workflow completion and physical acceptance
are separate fields.
"""
import csv
import hashlib
import io
import json
import math
import re
import statistics
import subprocess

from tools.build_midterm_hnhl_nov16 import ROOT, pursuit_metrics
from sentry.net.latency import percentile

SOURCE = "55ddfc845530cbae7ede5be3d5e25549da3785d5"
FOLDER = "reports/DoanQuocKien/week-07/finddoor_1120/"
OUT = ROOT / "reports/HuynhNguyenHoaiLoc/midterm/update-2026-11-21.json"
GITHUB = OUT.parent / "github-2026-11-21.json"


def latency_snapshot(summary, rows):
    times, latencies, seqs = [], [], []
    for row in rows:
        timestamp = float(row['t_decode_laptop_s'])
        offset = float(row['offset_jetson_minus_laptop_s'])
        corrected = (timestamp - (float(row['t_cap_jetson_s']) - offset)) * 1000
        latency = float(row['decoded_latency_ms'])
        if not all(math.isfinite(value) for value in (timestamp, offset, corrected, latency)):
            raise ValueError('nonfinite latency timestamps')
        if abs(corrected - latency) > .001:
            raise ValueError('latency differs from corrected raw timestamps')
        times.append(timestamp)
        latencies.append(latency)
        seqs.append(int(row['seq']))
    if len(times) < 2 or any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError('latency timestamps must increase')
    metrics = dict(frames=len(rows), observed_duration_s=times[-1] - times[0],
        delivered_fps=(len(rows) - 1) / (times[-1] - times[0]),
        decoded_latency_p50_ms=percentile(latencies, .5), decoded_latency_p95_ms=percentile(latencies, .95),
        negative_latency_frames=sum(int(row['negative_latency']) for row in rows),
        sequence_resets=sum(b <= a for a, b in zip(seqs, seqs[1:])),
        sequence_gaps=sum(max(0, b - a - 1) for a, b in zip(seqs, seqs[1:])))
    for field, value in metrics.items():
        if not math.isclose(value, summary[field], rel_tol=1e-8, abs_tol=1e-5):
            raise ValueError('latency summary differs from CSV: ' + field)
    metrics.update(run_fps=len(rows) / summary['measurement_duration_s'],
        clock_samples=summary['clock_samples'], clock_rtt_s=summary['clock_rtt_s'],
        clock_uncertainty_ms=summary['clock_uncertainty_ms'],
        session_label='latency_1111; classroom_1111_pm README late addition',
        source_owner='DQK', exposure_included=False, packet_loss_measured=False,
        fps_20_met=metrics['delivered_fps'] >= 20,
        decoded_p95_50ms_met=metrics['decoded_latency_p95_ms'] <= 50)
    return metrics


def pursuit_snapshot(summary, rows):
    metrics = pursuit_metrics(rows)
    for field, value in metrics.items():
        if field != "hold_frames" and value != summary[field]:
            raise ValueError("pursuit summary differs from CSV: " + field)
    tower_frames = sum(row["mode"].startswith("TOWER_") for row in rows)
    if tower_frames != summary["frames_tower_avoid"]:
        raise ValueError("tower frame count differs from CSV")
    events = summary["tower_avoid"]["events"]
    counts = {kind: sum(event["event"] == kind for event in events)
              for kind in ("TRIGGER", "DONE", "ABORT")}
    if counts["DONE"] != summary["tower_avoid"]["count"]:
        raise ValueError("tower completion count differs from event list")
    return dict(metrics=metrics, tower_events=counts, tower_frames=tower_frames,
                hold_events=summary["hold_events"],
                general_obstacle_detector_enabled=summary["obstacle_avoidance"],
                range_source=summary["range_source"], end_reason=summary["end_reason"],
                battery_v_start=summary["battery_v_start"],
                distance_fraction_meets_08=metrics["time_fraction_distance_in_band_of_run"] >= .8,
                centred_fraction_meets_08=metrics["time_fraction_centred_of_run"] >= .8,
                independent_t2=False, identity_accuracy_measured=False)


def deployment_snapshot(summary, rows, handshake, frames, tape):
    times = [float(row["t"]) for row in rows]
    if not times or any(not math.isfinite(t) for t in times) or any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError("deployment CSV needs finite increasing timestamps")
    # The control CSV is rounded to milliseconds; transitions retain full precision.
    for timestamp, state in summary["state_changes"]:
        first = next((row for row in rows if row["state"] == state), None)
        if first is None or abs(float(first["t"]) - timestamp) > .001:
            raise ValueError("deployment state transition differs from CSV: " + state)
    hs = summary["handshake"]
    in_view = sum(int(row["in_view"]) for row in handshake)
    if len(handshake) != hs["frames"] or in_view != hs["in_view_frames"]:
        raise ValueError("handshake counts differ from CSV")
    if not handshake or int(handshake[-1]["inliers"]) != hs["last_inliers"]:
        raise ValueError("handshake last inliers differ from CSV")
    if len(frames) != summary["tower_place"]["frames"]:
        raise ValueError("robot frame count differs from CSV")
    if summary['success'] != (rows[-1]['state'] == 'STANDBY'):
        raise ValueError('deployment success differs from final CSV state')
    last_range = summary["find_door_measures"][-1][2]
    if tape["runner_final_range_estimate_m"] != last_range:
        raise ValueError("tape note refers to a different final estimate")
    standby = next((t for t, state in summary["state_changes"] if state == "STANDBY"), None)
    return dict(mode=summary["mode"], runner_success=summary["success"],
                standby_s=round(standby, 3) if standby is not None else None,
                state_changes=summary["state_changes"], log_rows=len(rows),
                measurements=len(summary["find_door_measures"]),
                first_estimate_m=summary["find_door_measures"][0][2], last_estimate_m=last_range,
                handshake=dict(frames=len(handshake), in_view_frames=in_view,
                               last_inliers=hs["last_inliers"],
                               max_inliers=max(int(row["inliers"]) for row in handshake), rule=hs["rule"]),
                tower_gate=summary["tower_place"], operator_tape=tape,
                tape_position_attribution="DQK README: stop point before reverse, approximate",
                independent_t2=False, automatic_map_vantage=False)


def collect(ref=SOURCE):
    if not re.fullmatch(r"[0-9a-f]{40}", ref):
        raise ValueError("source must be a full immutable Git SHA")
    sources = {}

    def read(path):
        data = subprocess.check_output(["git", "show", ref + ":" + path], cwd=ROOT)
        sources[path] = dict(commit=ref, path=path, sha256=hashlib.sha256(data).hexdigest())
        return data

    def document(relative):
        return json.loads(read(FOLDER + relative))

    def rows(relative):
        return list(csv.DictReader(io.StringIO(read(FOLDER + relative).decode("utf-8"))))

    for path in subprocess.check_output(["git", "ls-tree", "-r", "--name-only", ref, "--", FOLDER],
                                         cwd=ROOT, text=True).splitlines():
        read(path)
    deployment = deployment_snapshot(document("stage1_take3_a_1/summary.json"),
        rows("stage1_take3_a_1/log.csv"), rows("stage1_take3_a_1/handshake.csv"),
        rows("stage1_take3_a_1/frames.csv"), document("stage1_take3_a_1/tape_note.json"))
    pursuit = {name: pursuit_snapshot(document(name + "/summary.json"), rows(name + "/log.csv"))
               for name in ("pursuit_take3_b_1", "pursuit_take3_b_2")}
    approaches = {}
    for name in ("approach_ap_ref_1120_1", "approach_ap_chain_1120_1"):
        summary, log = document(name + "/summary.json"), rows(name + "/log.csv")
        if len(log) != summary["steps"] or float(log[-1]["range_m"]) != summary["last_range_est_m"]:
            raise ValueError("approach summary differs from CSV: " + name)
        approaches[name] = summary
    pose = document("tower_register/camera_pose_tower_1120_2.json")
    pitches = [face["pitch_deg"] for face in pose["tower_faces"].values()]
    if abs(statistics.median(pitches) - pose["pitch_down_deg"]) > .01:
        raise ValueError("tower median pitch differs from registered faces")
    prior_pose = document("tower_register/camera_pose_tower_1120_1.json")
    latency = {}
    for name in ('video_latency_1111', 'video_latency_1111_settled'):
        prefix = 'reports/DoanQuocKien/week-06/latency_1111/' + name
        latency[name] = latency_snapshot(json.loads(read(prefix + '.json')),
            list(csv.DictReader(io.StringIO(read(prefix + '.csv').decode('utf-8')))))
    read('reports/DoanQuocKien/week-06/classroom_1111_pm/README.md')
    read('reports/DoanQuocKien/week-06/figures/F7_video_latency.png')
    for path in ("docs/Mid-Term Report Plan.md", "docs/Implementation Plan.md",
                 "reports/midterm_report_draft.md", "reports/kouun-rokku/week-07/editor-source-registry.json",
                 "reports/HuynhNguyenHoaiLoc/reviews/PR-133-2026-11-21.json",
                 "reports/HuynhNguyenHoaiLoc/reviews/PR-133-2026-11-21.md"):
        read(path)
    review = json.loads(read("reports/HuynhNguyenHoaiLoc/reviews/PR-133-2026-11-21.json"))
    github_bytes = GITHUB.read_bytes().replace(b"\r\n", b"\n")
    github = json.loads(github_bytes)
    for pr in github["pull_requests"]:
        if not pr["merged"]:
            raise ValueError("expected merged PR in dated GitHub snapshot")
        subprocess.run(["git", "merge-base", "--is-ancestor", pr["merge_commit_sha"], ref], cwd=ROOT, check=True)
    return dict(schema_version=1, date="2026-11-21", robot_diagnostic_date="2026-11-20",
                timezone="Asia/Bangkok", added_after_freeze="2026-11-16", source_commit=ref,
                sources=list(sources.values()), github_snapshot=github,
                github_snapshot_sha256_lf=hashlib.sha256(github_bytes).hexdigest(),
                deployment=deployment, pursuit=pursuit, approach=approaches, existing_f7_latency=latency,
                camera_pose=dict(pose=pose, face_pitch_range_deg=round(max(pitches) - min(pitches), 3),
                    face_pitch_std_deg=round(statistics.pstdev(pitches), 3),
                    previous_pitch_deg=prior_pose["pitch_down_deg"], roll_measured=False),
                review_validation=review,
                scope=dict(measurement_owner="DQK", review_and_report_owner="HNHL",
                           new_inference=False, new_hardware_trials=False,
                           raw_frames_committed=False, workflow_closure_is_acceptance=False),
                acceptance=dict(door_t1=False, automatic_map_vantage=False, pursuit_pd=False,
                    hold_protocol=False, independent_d5=False, d3_identity_accuracy=False,
                    reid_gallery_rank1=False, rtx4050_precision_accuracy=False,
                    jetbot_video_latency=False, jetbot_video_fps=False, full_loop=False))


def main():
    result = collect()
    OUT.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(dict(sources=len(result["sources"]), standby_s=result["deployment"]["standby_s"],
                         pursuit={name: item["metrics"] for name, item in result["pursuit"].items()})))


if __name__ == "__main__":
    main()
