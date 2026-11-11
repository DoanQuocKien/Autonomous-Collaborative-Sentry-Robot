"""Does a bigger recogniser help on the small door faces of 2026-11-11? Same 793 walker-face frames (the boxes tools.d2_segment found with buffalo_s), embeddings recomputed with each InsightFace pack
(buffalo_s = MobileFaceNet, buffalo_l = ResNet50, both trained on WebFace600K) and, as a control, the face crop upsampled x2 before detection. Reports the ROC AUC (P(genuine score > impostor score);
0.5 = no separation) with the leave-one-member-out protocol of d2_entry_level.py, frame level and entry level (mean embedding per entry). Frames stay local; writes results/d2_model_compare_1111.json.
  PYTHONPATH=. python reports/DoanQuocKien/week-06/classroom_1111_pm/scripts/d2_model_compare.py"""
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
from insightface.app import FaceAnalysis

R = Path(__file__).resolve().parents[5]
S = R / "data/D2/class_door_1111"
dest = R / "reports/DoanQuocKien/week-06/classroom_1111_pm/data/d2_model_compare_1111.json"
if dest.exists():
    sys.exit("refusing to overwrite %s" % dest)
rows = list(csv.DictReader(open(S / "d2_faces.csv")))
unit = lambda v: v / np.linalg.norm(v)


def iou(a, b):
    x1, y1, x2, y2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    i = max(0, x2 - x1) * max(0, y2 - y1)
    return i / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i + 1e-9)


def embed_all(pack, scale):
    app = FaceAnalysis(name=pack, providers=["CUDAExecutionProvider", "CPUExecutionProvider"], allowed_modules=["detection", "recognition"])
    app.prepare(ctx_id=0, det_size=(640, 640), det_thresh=0.2)
    out, miss = {}, 0
    for r in rows:
        img = cv2.imread(str(S / r["member"] / r["clip"] / r["frame_file"]))
        if scale != 1:
            img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        box = [float(r[k]) * scale for k in ("x1", "y1", "x2", "y2")]
        fa = app.get(img)
        best = max(fa, key=lambda f: iou(f.bbox, box)) if fa else None
        if best is None or iou(best.bbox, box) < 0.3:
            miss += 1
            continue
        out[(r["member"], r["frame_file"])] = best.normed_embedding
    return out, miss


def auc_protocol(emb):
    ent = defaultdict(list)
    for r in rows:
        k = (r["member"], r["frame_file"])
        if k in emb:
            ent[(r["member"], int(r["entry"]))].append(emb[k])
    members = sorted({m for m, _ in ent})
    res = {}
    for level in ("frame", "entry"):
        gen, imp = [], []
        for stranger in members:
            reg = [m for m in members if m != stranger]
            firsts = {m: min(e for (mm, e) in ent if mm == m) for m in reg}
            if any(not ent.get((m, firsts[m])) for m in reg):
                continue
            tmpl = {m: unit(np.mean([unit(e) for e in ent[(m, firsts[m])]], 0)) for m in reg}
            for (m, e), fr in ent.items():
                if not fr or (m in reg and e == firsts[m]):
                    continue
                qs = [unit(np.mean([unit(x) for x in fr], 0))] if level == "entry" else [unit(x) for x in fr]
                for q in qs:
                    sc = {k: float(q @ t) for k, t in tmpl.items()}
                    (imp if m == stranger else gen).append(max(sc.values()) if m == stranger else sc[m])
        res[level] = dict(auc=round(float(np.mean([g > i for g in gen for i in imp])), 3) if gen and imp else None, n_genuine=len(gen), n_impostor=len(imp))
    return res


out = {"note": __doc__.split("\n")[0]}
for pack, scale in (("buffalo_s", 1), ("buffalo_l", 1), ("buffalo_s", 2), ("buffalo_l", 2)):
    if not (Path.home() / ".insightface/models" / pack / ("w600k_r50.onnx" if pack == "buffalo_l" else "w600k_mbf.onnx")).exists():
        print("skipping", pack, "(not downloaded)")
        continue
    emb, miss = embed_all(pack, scale)
    out["%s x%d" % (pack, scale)] = dict(frames_embedded=len(emb), frames_missed=miss, **auc_protocol(emb))
    print(pack, "x%d" % scale, out["%s x%d" % (pack, scale)], flush=True)
dest.write_text(json.dumps(out, indent=1, allow_nan=False))
