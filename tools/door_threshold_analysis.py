"""Threshold analysis of the door-camera recognition test, from the per-frame CSVs only (no images, no GPU):

  python -m tools.door_threshold_analysis --csv-dir reports/DoanQuocKien/week-06/t2_1114

Input: frames_<SUBJECT>.csv written by `tools.door_recognition_seq score` (cos_<ID> = best cosine of the frame against that enrolment; empty = no face found).
1. impostor scores per ordered pair (whose frames, whose enrolment): the margin to a threshold is max-impostor vs threshold.
2. pooled TAR with a clip-level bootstrap (the straight clips are the independent units; frames inside a clip are strongly correlated). Seeded.
3. entry-level rules on windows of N consecutive frames (max | mean | k-th best score), a missing face counts as no evidence. Windows overlap: the counts are NOT independent trials.
Limits: three people, one session, one camera, six ordered pairs: a zero FAR here is not a bound on the FAR of a population."""
import argparse
import csv
from pathlib import Path

import numpy as np


def _f(x):
    return float(x) if x not in ("", None) else np.nan


def load(csv_dir):
    out = {}
    for p in sorted(Path(csv_dir).glob("frames_*.csv")):
        out[p.stem[len("frames_"):]] = list(csv.DictReader(open(p)))
    return out


def pair_margins(R):
    res = {}
    for a in R:
        for b in R:
            if a != b:
                v = np.array([_f(r["cos_" + b]) for r in R[a]])
                res[(a, b)] = v[~np.isnan(v)]
    return res


def clip_scores(R):
    clips = {}
    for s in R:
        for r in R[s]:
            if r["window"].endswith("straight"):
                clips.setdefault((s, r["window"]), []).append(_f(r["cos_" + s]))
    return clips


def pooled_tar(clips, keys, thr):
    hits = n = 0
    for k in keys:
        v = np.array(clips[k])
        n += len(v)
        hits += np.nansum(v >= thr)                      # no face = a miss
    return hits / n


def window_score(frames, enrol, rule, k):
    v = np.array([_f(r["cos_" + enrol]) for r in frames])
    v = np.where(np.isnan(v), -1.0, v)
    return {"max": v.max(), "mean": v.mean(), "kofn": np.sort(v)[::-1][k - 1]}[rule]


def window_rates(R, n, rule, thr, k=1):
    """TAR over windows of straight frames against the own enrolment, FAR over windows of every frame against the other enrolments."""
    def seqs(s, straight):
        d = {}
        for r in R[s]:
            if r["window"].endswith("straight") == straight:
                d.setdefault(r["window"], []).append(r)
        return d.values()
    g, im = [], []
    for s in R:
        for fr in seqs(s, True):
            g += [window_score(fr[i:i + n], s, rule, k) for i in range(len(fr) - n + 1)]
        for straight in (True, False):
            for fr in seqs(s, straight):
                for i in range(len(fr) - n + 1):
                    im += [window_score(fr[i:i + n], o, rule, k) for o in R if o != s]
    g, im = np.array(g), np.array(im)
    return (g >= thr).mean(), (im >= thr).mean(), im.max(), len(g), len(im)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv-dir", required=True)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--resamples", type=int, default=5000)
    a = ap.parse_args()
    R = load(a.csv_dir)
    print("1) impostor scores by ordered pair (frames of A against the enrolment of B)")
    for (x, y), v in pair_margins(R).items():
        print("   %-5s -> %-5s n=%d p99 %.3f max %.3f  >=0.40: %d  >=0.45: %d" % (x, y, len(v), np.percentile(v, 99), v.max(), (v >= 0.40).sum(), (v >= 0.45).sum()))
    clips = clip_scores(R)
    keys = list(clips)
    rng = np.random.default_rng(a.seed)
    print("\n2) pooled TAR, clip-level bootstrap (%d clips, %d resamples): point [2.5 %%, 97.5 %%]" % (len(keys), a.resamples))
    for thr in (0.45, 0.40, 0.35):
        bs = [pooled_tar(clips, [keys[i] for i in rng.integers(0, len(keys), len(keys))], thr) for _ in range(a.resamples)]
        print("   thr %.2f: %.3f [%.3f, %.3f]" % (thr, pooled_tar(clips, keys, thr), *np.percentile(bs, [2.5, 97.5])))
    print("\n3) entry-level rules on windows of N consecutive frames (12.5 fps: N=12 is about 1 s); windows overlap, counts are not independent")
    for n, rule, k in ((1, "max", 1), (5, "max", 1), (12, "max", 1), (5, "mean", 1), (12, "mean", 1), (5, "kofn", 3), (12, "kofn", 6)):
        for thr in (0.45, 0.40):
            t, fa, mx, ng, ni = window_rates(R, n, rule, thr, k)
            print("   N=%-2d %-5s%s thr %.2f: TAR %.3f FAR %.4f max impostor %.3f (%d genuine, %d impostor windows)" % (n, rule, "(k=%d)" % k if rule == "kofn" else "     ", thr, t, fa, mx, ng, ni))


if __name__ == "__main__":
    main()
