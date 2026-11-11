"""D2 door clips of 2026-11-11 (3 members, 793 walker-face frames, 43 automatic entries): does averaging the frames of an entry help, and how does the score depend on the face width?
Embeddings are the buffalo_s ones that tools.d2_segment saved (faces.npz). Protocol = leave-one-member-out like the pilot: the third member is the stranger; a registered member's template = the mean
embedding of ALL frames of his first entry; every later entry of a registered member is a genuine query, every entry of the stranger an impostor. Score = cosine to the best template; an
entry is accepted when the score >= threshold AND the best template is the right member (genuine). Frame level: the same with single frames. Entries and identities are the automatic labels (the
clips contain one walker each, checked on 16 frames per clip). n is small (43 entries): the numbers are descriptive, not a TAR@FAR=1 % estimate.
  PYTHONPATH=. python reports/DoanQuocKien/week-06/classroom_1111_pm/scripts/d2_entry_level.py"""
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parents[5]
S = R / "data/D2/class_door_1111"
rows = list(csv.DictReader(open(S / "d2_faces.csv")))
emb = {}
for m in ("DQK", "HNHL", "KR"):
    z = np.load(S / m / "c01/faces.npz", allow_pickle=True)
    emb.update({(m, str(f)): e for f, e in zip(z["frame_files"], z["embeddings"])})
ent = defaultdict(list)                                   # (member, entry) -> [(embedding, width)]
for r in rows:
    ent[(r["member"], int(r["entry"]))].append((emb[(r["member"], r["frame_file"])], float(r["width_px"])))
members = sorted({m for m, _ in ent})
unit = lambda v: v / np.linalg.norm(v)
dest = R / "reports/DoanQuocKien/week-06/classroom_1111_pm/data/d2_entry_level_1111.json"
if dest.exists():
    sys.exit("refusing to overwrite %s" % dest)


def run(level, weight, min_w, thrs=(0.30, 0.35, 0.40, 0.45)):
    """-> {threshold: (TAR, FAR, n_gen, n_imp)} averaged over the three leave-one-member-out folds (counts summed)."""
    out = {t: [0, 0, 0, 0] for t in thrs}
    gen_s, imp_s = [], []
    for stranger in members:
        reg = [m for m in members if m != stranger]
        tmpl = {}
        for m in reg:
            first = min(e for (mm, e) in ent if mm == m)
            fr = [x for x in ent[(m, first)] if x[1] >= min_w]
            if not fr:
                break
            tmpl[m] = unit(np.mean([unit(e) for e, _ in fr], 0))
        else:
            queries = []                                   # (true member, embedding)
            for (m, e), fr in ent.items():
                fr = [x for x in fr if x[1] >= min_w]
                if not fr or (m in reg and e == min(k for (mm, k) in ent if mm == m)):
                    continue
                if level == "entry":
                    w = np.array([x[1] if weight == "width" else 1.0 for x in fr])
                    queries.append((m, unit(np.sum([unit(x[0]) * wi for x, wi in zip(fr, w)], 0))))
                else:
                    queries += [(m, unit(x[0])) for x in fr]
            for m, q in queries:
                sc = {k: float(q @ t) for k, t in tmpl.items()}
                best = max(sc, key=sc.get)
                (imp_s if m == stranger else gen_s).append(sc[best] if m == stranger else sc[m])
                for t in thrs:
                    if m == stranger:
                        out[t][2 + 1] += 1
                        out[t][1] += sc[best] >= t
                    else:
                        out[t][2] += 1
                        out[t][0] += (sc[best] >= t and best == m)
    auc = float(np.mean([[g > i] for g in gen_s for i in imp_s])) if gen_s and imp_s else None    # P(genuine score > impostor score): 0.5 = no separation
    return {"auc": round(auc, 3) if auc is not None else None, **{t: dict(TAR=round(v[0] / v[2], 3) if v[2] else None, FAR=round(v[1] / v[3], 3) if v[3] else None, n_genuine=v[2], n_impostor=v[3]) for t, v in out.items()}}


res = {}
for level, weight in (("frame", "-"), ("entry", "mean"), ("entry", "width")):
    for min_w in (24, 30, 36):
        res["%s/%s/min_width_%d" % (level, weight, min_w)] = run(level, weight, min_w)
        r0 = res["%s/%s/min_width_%d" % (level, weight, min_w)]
        print("%-28s" % ("%s %s >=%d px" % (level, weight, min_w)), " ".join("t%.2f TAR %s FAR %s (n %d/%d) |" % (t, v["TAR"], v["FAR"], v["n_genuine"], v["n_impostor"]) for t, v in r0.items() if t in (0.35, 0.45)), "AUC", r0["auc"])
dest.write_text(json.dumps(dict(note=__doc__.split("\n")[0], results={k: {str(t): v for t, v in d.items()} for k, d in res.items()}), indent=1, allow_nan=False))
