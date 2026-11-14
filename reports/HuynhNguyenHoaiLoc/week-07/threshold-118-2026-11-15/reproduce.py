"""Recompute numeric frame ROC from DQK's pinned public CSVs; no images/models.

python reports/HuynhNguyenHoaiLoc/week-07/threshold-118-2026-11-15/reproduce.py \
  --csv-dir reports/DoanQuocKien/week-06/t2_1114 --out-dir data/threshold-rerun
Outputs must not already exist. Input provenance is checked against git.
"""
import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import subprocess

import numpy as np

SOURCE = "b831e76f073e7de51a774fdaf06b5aee2590f274"
PREFIX = "reports/DoanQuocKien/week-06/t2_1114"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    subjects = ("DQK", "HNHL", "KR")
    clips, impostor, straight_impostor, provenance = {}, [], [], {}
    for subject in subjects:
        name = f"frames_{subject}.csv"
        data = (args.csv_dir / name).read_bytes().replace(b"\r\n", b"\n")
        pinned = subprocess.check_output(["git", "show", f"{SOURCE}:{PREFIX}/{name}"])
        if data != pinned:
            raise ValueError(f"{name} differs from pinned source {SOURCE}")
        provenance[name] = hashlib.sha256(data).hexdigest()
        for row in csv.DictReader(io.StringIO(data.decode("utf-8"))):
            straight = row["window"].endswith("straight")
            for identity in subjects:
                raw = row["cos_" + identity]
                score = None if raw == "" else float(raw)
                if score is not None and (not math.isfinite(score) or not -1 <= score <= 1):
                    raise ValueError("finite cosine in [-1, 1] required")
                if identity == subject and straight:
                    # Missing faces are genuine misses at every threshold.
                    clips.setdefault((subject, row["window"]), []).append(score)
                elif identity != subject and score is not None:
                    impostor.append(score)
                    if straight:
                        straight_impostor.append(score)
    genuine = np.array([v if v is not None else -np.inf for clip in clips.values() for v in clip])
    impostor, straight_impostor = np.array(impostor), np.array(straight_impostor)
    if len(clips) != 9 or not genuine.size or not impostor.size:
        raise ValueError("expected nine genuine clips and available impostor scores")
    def rates(threshold):
        return dict(threshold=threshold, genuine_hits=int((genuine >= threshold).sum()), genuine_n=genuine.size,
                    tar=float((genuine >= threshold).mean()), impostor_accepts=int((impostor >= threshold).sum()),
                    impostor_n=impostor.size, far=float((impostor >= threshold).mean()))
    sweep = [rates(i / 100) for i in range(100, -101, -1)]
    rng = np.random.default_rng(0)
    arrays = [np.array([v if v is not None else -np.inf for v in clip]) for clip in clips.values()]
    operating_points = []
    for threshold in (.45, .40, .35, .30):
        point = rates(threshold)
        if threshold != .30:
            hits = np.array([(a >= threshold).sum() for a in arrays])
            sizes = np.array([a.size for a in arrays])
            indices = rng.integers(0, len(arrays), (5000, len(arrays)))
            point["clip_bootstrap_95_interval"] = np.percentile(hits[indices].sum(axis=1) / sizes[indices].sum(axis=1), [2.5, 97.5]).tolist()
        operating_points.append(point)
    result = dict(source_commit=SOURCE, csv_sha256_lf=provenance, genuine="straight frames, missing face counts as miss",
                  impostor="available scores of every frame against each other enrolment", bootstrap=dict(seed=0, resamples=5000, units=9),
                  operating_points=operating_points, impostor_max=float(impostor.max()),
                  straight_impostor_n=straight_impostor.size, straight_impostor_accepts_at_045=int((straight_impostor >= .45).sum()),
                  selected_policy=dict(threshold=.45, top_k=3, minimum_same_identity_votes=2, calibrated=False),
                  exact_live_policy_evaluated=False, t1_passed=False,
                  limitations=["3 people, one session and camera; six ordered identity pairs",
                               "correlated frames and clips from the same subjects; bootstrap is descriptive, not population validation",
                               "CSVs lack sharpness and track/entry truth for the live quality-selected rule"])
    args.out_dir.mkdir(parents=True, exist_ok=True)
    targets = [args.out_dir / name for name in ("summary.json", "roc.csv", "roc.png")]
    if any(path.exists() for path in targets):
        raise FileExistsError("choose a fresh output directory")
    targets[0].write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    with targets[1].open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(sweep[0]))
        writer.writeheader()
        writer.writerows(sweep)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), layout="constrained")
    for ax, limit in zip(axes, (1., .01)):
        ax.step([r["far"] for r in sweep], [r["tar"] for r in sweep], where="post", label="0.01 threshold grid")
        for point, marker in zip(operating_points, ("o", "s", "^", "x")):
            ax.scatter(point["far"], point["tar"], marker=marker, label=f"threshold {point['threshold']:.2f}", s=40)
        ax.set(xlim=(-limit * .03, limit), ylim=(0, 1.025), xlabel="Observed FAR (all available impostor scores)", ylabel="Observed TAR (straight genuine frames)")
        ax.grid(alpha=.25)
    axes[0].set_title("Frame ROC: full range")
    axes[1].set_title("Frame ROC: FAR up to 1%")
    axes[0].legend(fontsize=8, loc="lower right")
    fig.suptitle("Three people, one session — descriptive scores; T1 not passed", fontsize=11)
    fig.savefig(targets[2], dpi=160)
    plt.close(fig)
    print(json.dumps(operating_points))


if __name__ == "__main__":
    main()
