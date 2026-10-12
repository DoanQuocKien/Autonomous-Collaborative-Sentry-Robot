"""Entrance-matching bake-off on the D1 doorway sets (cafe glass door, classroom white door): ORB baseline vs XFeat vs DINOv2 global descriptors.

  python -m tools.bench_entrance --doors cafe_glass class_door --methods orb xfeat dino_s dino_b --step 3 --xfeat-dir <accelerated_features checkout>
Reference = the robot-eye frame of each door (hold-out: the reference position is left out of the evaluation, so is the excluded reference row).
Score per frame: ORB/XFeat = RANSAC homography inliers against the reference, DINOv2 = cosine similarity of the global descriptor.
Reports AUC (door in view vs not), TPR at 5 % FPR (threshold = 95th percentile of the negatives of the same door) and the median score per position.
Also: a linear probe on frozen DINOv2 features trained on one door and tested on the other (does "door-ness" generalise?).
"""
import argparse
import csv
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

REFS = {"cafe_glass": ("data/D1/jetbot/{ref_frame}", 2), "class_door": ("data/D1/class_door_iref_robot.jpg", 2)}   # reference image, position left out
D1 = Path("data/D1")


def load_rows(door, step):
    rows = [r for r in csv.DictReader(open(D1 / ("manifest_%s.csv" % door), encoding="utf-8"))]
    out = []
    for i, r in enumerate(rows):
        if i % step:
            continue
        r["path"] = str(D1 / "jetbot" / r["frame_file"])
        out.append(r)
    return out


def reference_image(door, rows_all):
    path, _ = REFS[door]
    if "{ref_frame}" in path:   # no saved robot-eye reference: the sharpest frame of the left-out position
        pos = [r for r in rows_all if int(r["position_id"]) == REFS[door][1]]
        sharp = lambda r: cv2.Laplacian(cv2.cvtColor(cv2.imread(str(D1 / "jetbot" / r["frame_file"])), cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()
        best = max(pos, key=sharp)
        return cv2.imread(str(D1 / "jetbot" / best["frame_file"])), best["frame_file"]
    return cv2.imread(path), Path(path).name


def auc(pos, neg):
    s = np.concatenate([pos, neg])
    ranks = s.argsort().argsort() + 1.0
    for v in np.unique(s):          # average ranks of ties
        m = s == v
        ranks[m] = ranks[m].mean()
    return (ranks[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def inliers(p0, p1):
    if len(p0) < 8:
        return float(len(p0) // 2)
    _, mask = cv2.findHomography(np.float32(p0), np.float32(p1), cv2.RANSAC, 5.0)
    return 0.0 if mask is None else float(mask.sum())


class Orb:
    name = "orb"

    def __init__(self, **_):
        self.orb, self.bf, self.clahe = cv2.ORB_create(2000), cv2.BFMatcher(cv2.NORM_HAMMING), cv2.createCLAHE(3.0, (8, 8))

    def feat(self, im):
        return self.orb.detectAndCompute(self.clahe.apply(cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)), None)

    def prepare(self, ref):
        self.ref = self.feat(ref)

    def score(self, im):
        (k1, d1), (k2, d2) = self.ref, self.feat(im)
        if d1 is None or d2 is None or len(k2) < 8:
            return 0.0
        m = [a for a, b in (p for p in self.bf.knnMatch(d1, d2, k=2) if len(p) == 2) if a.distance < 0.75 * b.distance]
        return inliers([k1[x.queryIdx].pt for x in m], [k2[x.trainIdx].pt for x in m])


class XFeatMatcher:
    name = "xfeat"

    def __init__(self, xfeat_dir, **_):
        import torch
        sys.path.insert(0, str(Path(xfeat_dir).resolve()))
        from modules.xfeat import XFeat
        self.xf = XFeat(weights=str(Path(xfeat_dir).resolve() / "weights" / "xfeat.pt"), top_k=2048)
        self.torch = torch

    def prepare(self, ref):
        self.ref = ref

    def score(self, im):
        p0, p1 = self.xf.match_xfeat(self.ref, im, top_k=2048)
        return inliers(p0, p1)


class Dino:
    def __init__(self, size, **_):
        import torch
        self.torch = torch
        self.name = "dino_" + size
        self.model = torch.hub.load("facebookresearch/dinov2", "dinov2_vit%s14" % size, verbose=False).cuda().eval().half()
        self.mean = torch.tensor([0.485, 0.456, 0.406], device="cuda").view(1, 3, 1, 1)
        self.std = torch.tensor([0.229, 0.224, 0.225], device="cuda").view(1, 3, 1, 1)

    def describe(self, ims):
        t = np.stack([cv2.resize(cv2.cvtColor(i, cv2.COLOR_BGR2RGB), (448, 336)) for i in ims])
        x = (self.torch.from_numpy(t).cuda().permute(0, 3, 1, 2).float() / 255 - self.mean) / self.std
        with self.torch.no_grad():
            o = self.model.forward_features(x.half())
            cls, pat = o["x_norm_clstoken"].float(), o["x_norm_patchtokens"].float()
            g = pat.clamp(min=1e-6).pow(3).mean(1).pow(1 / 3)              # GeM of the patch tokens
            d = self.torch.nn.functional.normalize(self.torch.cat([cls, g], 1), dim=1)
        return d.cpu().numpy()

    def prepare(self, ref):
        self.ref = self.describe([ref])[0]

    def score_many(self, ims):
        return self.describe(ims) @ self.ref


def evaluate(method, door, rows, ref, left_out):
    method.prepare(ref)
    ev = [r for r in rows if int(r["position_id"]) != left_out]
    t0 = time.perf_counter()
    if hasattr(method, "score_many"):
        sc = np.concatenate([method.score_many([cv2.imread(r["path"]) for r in ev[i:i + 32]]) for i in range(0, len(ev), 32)])
    else:
        sc = np.array([method.score(cv2.imread(r["path"])) for r in ev])
    ms = 1000 * (time.perf_counter() - t0) / len(ev)
    lab = np.array([r["door_visible"] == "yes" for r in ev])
    pos, neg = sc[lab], sc[~lab]
    thr = np.percentile(neg, 95)
    groups = {}
    for r, s in zip(ev, sc):
        if r["door_visible"] == "yes":
            groups.setdefault("%sm %s" % (r["distance_m"], r["angle_deg"]), []).append(s)
    return {"door": door, "method": method.name, "n_pos": int(lab.sum()), "n_neg": int((~lab).sum()), "auc": round(float(auc(pos, neg)), 3),
            "tpr_at_5pct_fpr": round(float((pos > thr).mean()), 3), "neg_p95": round(float(thr), 3), "pos_median": round(float(np.median(pos)), 3),
            "neg_median": round(float(np.median(neg)), 3), "ms_per_frame": round(ms, 1),
            "per_position_median": {k: round(float(np.median(v)), 3) for k, v in sorted(groups.items())}}, sc, lab


def logistic(torch, x, y, x_test, l2=1e-2, iters=200):
    """Class-balanced L2 logistic regression with LBFGS (no scikit-learn dependency). -> decision values for x_test."""
    X, Y = torch.tensor(x, dtype=torch.float32), torch.tensor(y, dtype=torch.float32)
    w = torch.zeros(X.shape[1], requires_grad=True)
    b = torch.zeros(1, requires_grad=True)
    wt = torch.where(Y > 0, 0.5 / Y.mean(), 0.5 / (1 - Y.mean()))
    opt = torch.optim.LBFGS([w, b], max_iter=iters)

    def closure():
        opt.zero_grad()
        loss = (wt * torch.nn.functional.binary_cross_entropy_with_logits(X @ w + b, Y, reduction="none")).mean() + l2 * (w ** 2).sum()
        loss.backward()
        return loss
    opt.step(closure)
    return (torch.tensor(x_test, dtype=torch.float32) @ w + b).detach().numpy()


def probe(size, step):
    """Linear probe on frozen DINOv2 features, trained on one door and tested on the other (no reference photo needed)."""
    import torch
    d = Dino(size)
    feats = {}
    for door in ("cafe_glass", "class_door"):
        rows = load_rows(door, step)
        f = np.concatenate([d.describe([cv2.imread(r["path"]) for r in rows[i:i + 32]]) for i in range(0, len(rows), 32)])
        feats[door] = (f, np.array([r["door_visible"] == "yes" for r in rows]))
    out = {}
    for a, b in (("cafe_glass", "class_door"), ("class_door", "cafe_glass")):
        s = logistic(torch, *feats[a], feats[b][0])
        out["train %s -> test %s" % (a, b)] = {"auc": round(float(auc(s[feats[b][1]], s[~feats[b][1]])), 3)}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--doors", nargs="+", default=["cafe_glass", "class_door"])
    ap.add_argument("--methods", nargs="+", default=["orb", "xfeat", "dino_s", "dino_b"])
    ap.add_argument("--step", type=int, default=3)
    ap.add_argument("--xfeat-dir", default=None)
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--fusion", action="store_true", help="also score XFeat + DINOv2 together (needs both in --methods; xfeat as log1p(inliers))")
    ap.add_argument("--out", default="reports/DoanQuocKien/week-02/d1/entrance_bench.json")
    a = ap.parse_args()
    results, kept = [], {}
    for name in a.methods:
        m = {"orb": lambda: Orb(), "xfeat": lambda: XFeatMatcher(a.xfeat_dir), "dino_s": lambda: Dino("s"), "dino_b": lambda: Dino("b")}[name]()
        for door in a.doors:
            rows_all = [r for r in csv.DictReader(open(D1 / ("manifest_%s.csv" % door), encoding="utf-8"))]
            ref, ref_name = reference_image(door, rows_all)
            res, sc, lab = evaluate(m, door, load_rows(door, a.step), ref, REFS[door][1])
            kept[(name, door)] = (sc, lab)
            res["reference"] = ref_name
            results.append(res)
            print("%-8s %-11s AUC %.3f  TPR@5%%FPR %.2f  pos median %.3f  neg p95 %.3f  %.1f ms/frame" % (name, door, res["auc"], res["tpr_at_5pct_fpr"], res["pos_median"], res["neg_p95"], res["ms_per_frame"]), flush=True)
    transfer = {}
    for name in {k[0] for k in kept}:                      # the fairer test: the threshold comes from the OTHER door's negatives (95th percentile)
        for da in a.doors:
            for db in a.doors:
                if da != db and (name, da) in kept and (name, db) in kept:
                    thr = np.percentile(kept[(name, da)][0][~kept[(name, da)][1]], 95)
                    sb, lb = kept[(name, db)]
                    transfer["%s: threshold from %s -> applied to %s" % (name, da, db)] = {"tpr": round(float((sb[lb] > thr).mean()), 3), "fpr": round(float((sb[~lb] > thr).mean()), 3), "threshold": round(float(thr), 3)}
    for k, v in sorted(transfer.items()):
        print("transfer", k, v, flush=True)
    if a.fusion and any(k[0] == "xfeat" for k in kept) and any(k[0].startswith("dino") for k in kept):
        dname = [k[0] for k in kept if k[0].startswith("dino")][-1]
        for door in a.doors:
            (xs, lab), (ds, _) = kept[("xfeat", door)], kept[(dname, door)]
            parts = []
            for v in (np.log1p(xs), ds):
                neg = v[~lab]
                parts.append((v - np.median(neg)) / (neg.std() + 1e-9))      # z-score against the door's own negatives
            f = parts[0] + parts[1]
            thr = np.percentile(f[~lab], 95)
            res = {"door": door, "method": "xfeat+" + dname, "auc": round(float(auc(f[lab], f[~lab])), 3), "tpr_at_5pct_fpr": round(float((f[lab] > thr).mean()), 3)}
            results.append(res)
            print("fusion   %-11s AUC %.3f  TPR@5%%FPR %.2f" % (door, res["auc"], res["tpr_at_5pct_fpr"]), flush=True)
    probes = {}
    if a.probe:
        for size in ("s", "b"):
            probes["dino_" + size] = probe(size, a.step)
            print("probe dino_%s:" % size, probes["dino_" + size], flush=True)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    json.dump({"step": a.step, "results": results, "threshold_transfer": transfer, "linear_probe": probes}, open(a.out, "w"), indent=2)


if __name__ == "__main__":
    main()
