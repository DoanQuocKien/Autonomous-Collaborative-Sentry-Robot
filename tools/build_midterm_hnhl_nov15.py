"""Pin the merged 15-Nov evidence for HNHL's current Markdown handoff.

No inference, network, private data or Word regeneration. Numeric sources
come from git; current Markdown is hashed separately with LF newlines.
"""
import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess

from sentry.config import DEFAULT_PATH

ROOT = DEFAULT_PATH.parent
OUT = ROOT / "reports/HuynhNguyenHoaiLoc/midterm/update-2026-11-15.json"
SOURCE = "1a20ba5d439b13b359d7a66301418209b0381b7d"


def collect(ref=SOURCE, markdown_ref=None):
    sources = []
    def read(path):
        data = subprocess.check_output(["git", "show", ref + ":" + path], cwd=ROOT)
        sources.append(dict(path=path, sha256=hashlib.sha256(data).hexdigest()))
        return data.decode("utf-8")
    def document(path):
        return json.loads(read(path))

    gpu = {}
    for name in ("both", "xfeat", "both_5hz"):
        data = document("reports/DoanQuocKien/week-06/gpu_rtx4050_1113/pipeline_" + name + ".json")
        gpu[name] = {k: data[k] for k in ("fps", "p95_ms", "device_used_peak_gib", "actual_door_hz", "t1_accepted")}
    genuine, impostor, straight_impostor = [], [], []
    subjects = ("DQK", "HNHL", "KR")
    for subject in subjects:
        rows = csv.DictReader(io.StringIO(read("reports/DoanQuocKien/week-06/t2_1114/frames_" + subject + ".csv")))
        for row in rows:
            straight = row["window"].endswith("straight")
            if straight:
                genuine.append(float(row["cos_" + subject]) if row["cos_" + subject] else -1.)
            for other in subjects:
                if other != subject and row["cos_" + other]:
                    impostor.append(float(row["cos_" + other]))
                    if straight:
                        straight_impostor.append(float(row["cos_" + other]))
    threshold = document("reports/HuynhNguyenHoaiLoc/week-07/threshold-118-2026-11-15/summary.json")
    door = dict(genuine_hits=sum(x >= .45 for x in genuine), genuine_n=len(genuine),
                impostor_accepts=sum(x >= .45 for x in impostor), impostor_n=len(impostor),
                straight_impostor_accepts=sum(x >= .45 for x in straight_impostor), straight_impostor_n=len(straight_impostor),
                impostor_max=max(impostor), threshold=.45, top_k=3, minimum_votes=2,
                clip_bootstrap_95_interval=threshold["operating_points"][0]["clip_bootstrap_95_interval"], t1_passed=False)
    pilot = document("reports/HuynhNguyenHoaiLoc/week-07/live_adjusted_2026-11-14.json")
    wifi = document("reports/HuynhNguyenHoaiLoc/week-07/analysis-2026-11-14/wifi-reconnected.json")["recorded_summary"]
    deployment = {}
    for number in (8, 9):
        data = document(f"reports/DoanQuocKien/week-06/t2_1114/summary_run{number}.json")
        deployment[str(number)] = {k: data[k] for k in ("mode", "success", "chosen_vantage", "end_reason")}
    read("reports/DoanQuocKien/week-06/t2_1114/README.md")
    read("reports/DoanQuocKien/week-06/heartbeat_dryrun_1114/README.md")
    read("reports/DoanQuocKien/week-06/classroom_1111_pm/README.md")
    read("docs/Implementation Plan.md")
    markdown = {}
    for name in ("chapter-05-current.md", "chapter-07-rows.md", "code-appendix.md", "update-2026-11-15.md"):
        if markdown_ref is None:
            data = (OUT.parent / name).read_bytes().replace(b"\r\n", b"\n")
        else:
            path = "reports/HuynhNguyenHoaiLoc/midterm/" + name
            data = subprocess.check_output(["git", "show", markdown_ref + ":" + path], cwd=ROOT)
        markdown[name] = hashlib.sha256(data).hexdigest()
    return dict(schema_version=1, date="2026-11-15", timezone="Asia/Bangkok", source_commit=ref,
                current_markdown_sha256_lf=markdown,
                sources=sources, rtx4050=dict(owner="DQK", runs=gpu, combined_live_accepted=False),
                door=door, pilot=dict(code_commit=pilot["code_commit"], t1_passed=pilot["t1_passed"],
                count_unit=pilot["count_unit"], runs={k: pilot[k]["summary"] for k in ("genuine", "impostor")}),
                wifi_empty_scene=wifi, deployment_manual_vantage=deployment,
                acceptance=dict(door_t1=False, d3_identity_accuracy=False, independent_d5=False,
                                automatic_map_vantage=False, rtx4050_precision_accuracy=False, full_loop=False))


def main():
    later_snapshot = OUT.parent / "update-2026-11-16.json"
    markdown_ref = None
    if later_snapshot.exists():
        markdown_ref = json.loads(later_snapshot.read_text(encoding="utf-8"))["base_commit"]
    result = collect(markdown_ref=markdown_ref)
    OUT.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(dict(source=result["source_commit"], sources=len(result["sources"]), door=result["door"])))


if __name__ == "__main__":
    main()
