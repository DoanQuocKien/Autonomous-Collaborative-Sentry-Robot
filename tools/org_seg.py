"""Experiment B: reflection-robust floor/obstacle segmentation, trained on the ORG dataset (Xue et al., IJCV 2023: obstacles on reflective ground, robot view, pixel labels) and judged on UNSEEN ORG scenes.

  python -m tools.org_seg cache                      # 960x540 JPEG/PNG cache of data/ORG (once)
  python -m tools.org_seg train --epochs 15          # fine-tune data/models/segformer-b0-ade (3 classes: background, ground, obstacle) -> data/org_seg/segformer_org.pt
  python -m tools.org_seg eval  [--weights W]        # ORG test scenes (different buildings from train): ground/obstacle IoU, object recall, false components, contact-row error

ORG label ids: 0 = background, 1 = ground, >= 2 = an obstacle category (38 train / 43 test categories, e.g. wallet, phone, keys, book, chair wheel). Data is local (data/, gitignored), no licence stated by the authors:
used here for evaluation and fine-tuning in a course project, cited, not redistributed. Reproducibility: seed 0, the exact command lines and library versions are written into the output JSON.
"""
import argparse
import json
import math
import multiprocessing as mp
import os
import random
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ORG = ROOT / "data" / "ORG"
CACHE = ROOT / "data" / "org_seg" / "cache"
OUT = ROOT / "data" / "org_seg"
SEG_W, SEG_H = 960, 540
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32) * 255
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32) * 255
CLASSES = ("background", "ground", "obstacle")


def _cache_one(args):
    split, img_path = args
    img_path = Path(img_path)
    stem = img_path.name.replace("_image.png", "")
    scene = img_path.parent.parent.name
    lab = ORG / "gtCoarse_Segmentation" / split / scene / (stem + "_gtCoarse_labelIds.png")
    js = ORG / "gtCoarse" / split / scene / (stem + "_gtCoarse_obstacles.json")
    if not lab.exists() or not js.exists():
        return None
    img = cv2.imread(str(img_path))
    m = cv2.imread(str(lab), cv2.IMREAD_UNCHANGED)
    if img is None or m is None:
        return None
    d = CACHE / split
    d.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(d / (stem + ".jpg")), cv2.resize(img, (SEG_W, SEG_H), interpolation=cv2.INTER_AREA), [cv2.IMWRITE_JPEG_QUALITY, 95])
    cls = np.where(m == 0, 0, np.where(m == 1, 1, 2)).astype(np.uint8)
    cv2.imwrite(str(d / (stem + ".png")), cv2.resize(cls, (SEG_W, SEG_H), interpolation=cv2.INTER_NEAREST))
    info = json.load(open(js))
    ob = info.get("objects") or []
    ob = ob if isinstance(ob, list) else [ob]
    boxes = [[o["boundingbox"][0] * SEG_W / 1920.0, o["boundingbox"][1] * SEG_H / 1080.0, o["boundingbox"][2] * SEG_W / 1920.0, o["boundingbox"][3] * SEG_H / 1080.0, o["type_ID"], o["name"]]
             for o in ob if isinstance(o, dict) and len(o.get("boundingbox", [])) == 4]
    return dict(split=split, scene=scene, stem=stem, boxes=boxes)


def cache():
    items = []
    for split in ("train", "test"):
        items += [(split, p) for p in sorted((ORG / "image" / split).glob("*/*/*_image.png"))]
    print("images:", len(items), flush=True)
    with mp.Pool(6) as pool:
        recs = [r for r in pool.imap(_cache_one, items, chunksize=16) if r]
    (CACHE / "index.json").write_text(json.dumps(recs))
    print("cached", len(recs), "labelled images:", {s: sum(1 for r in recs if r["split"] == s) for s in ("train", "test")})


def load_index(split):
    return [r for r in json.load(open(CACHE / "index.json")) if r["split"] == split]


def to_tensor(img_bgr):
    import torch
    x = (cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB).astype(np.float32) - MEAN) / STD
    return torch.from_numpy(x.transpose(2, 0, 1))


class TrainSet(object):
    def __init__(self, recs, crop=512, seed=0):
        self.recs, self.crop, self.rng = recs, crop, random.Random(seed)

    def __len__(self):
        return len(self.recs)

    def __getitem__(self, i):
        import torch
        r = self.recs[i]
        d = CACHE / r["split"]
        img = cv2.imread(str(d / (r["stem"] + ".jpg")))
        lab = cv2.imread(str(d / (r["stem"] + ".png")), cv2.IMREAD_UNCHANGED)
        h, w = lab.shape
        c = self.crop
        if r["boxes"] and self.rng.random() < 0.7:                          # bias the crop to contain an obstacle
            bx, by, bw, bh = random.choice(r["boxes"])[:4]
            cx, cy = int(bx + bw / 2), int(by + bh / 2)
            x0 = min(max(0, cx - self.rng.randint(40, c - 40)), w - c)
            y0 = min(max(0, cy - self.rng.randint(40, c - 40)), h - c)
        else:
            x0, y0 = self.rng.randint(0, w - c), self.rng.randint(0, h - c)
        img, lab = img[y0:y0 + c, x0:x0 + c], lab[y0:y0 + c, x0:x0 + c]
        if self.rng.random() < 0.5:
            img, lab = img[:, ::-1], lab[:, ::-1]
        if self.rng.random() < 0.8:                                          # mild photometric jitter
            img = np.clip(img.astype(np.float32) * self.rng.uniform(0.8, 1.2) + self.rng.uniform(-20, 20), 0, 255).astype(np.uint8)
        return to_tensor(np.ascontiguousarray(img)), torch.from_numpy(np.ascontiguousarray(lab)).long()


def build_model(weights=None):
    import torch
    from transformers import SegformerForSemanticSegmentation
    src = ROOT / "data" / "models" / "segformer-b0-ade"
    m = SegformerForSemanticSegmentation.from_pretrained(str(src), num_labels=3, ignore_mismatched_sizes=True, id2label=dict(enumerate(CLASSES)), label2id={c: i for i, c in enumerate(CLASSES)})
    if weights:
        m.load_state_dict(torch.load(weights, map_location="cpu"))
    return m


def predict(model, img_bgr, device="cuda"):
    """-> (h, w) uint8 class map at the input resolution (bgr uint8 any size; padded to a multiple of 32 internally)."""
    import torch
    h, w = img_bgr.shape[:2]
    H, W = int(math.ceil(h / 32.0) * 32), int(math.ceil(w / 32.0) * 32)
    x = to_tensor(cv2.copyMakeBorder(img_bgr, 0, H - h, 0, W - w, cv2.BORDER_REFLECT))[None].to(device)
    with torch.no_grad(), torch.autocast("cuda", dtype=torch.float16):
        lg = model(pixel_values=x).logits
    lg = torch.nn.functional.interpolate(lg.float(), size=(H, W), mode="bilinear", align_corners=False)[0, :, :h, :w]
    return lg.argmax(0).cpu().numpy().astype(np.uint8)


def train(a):
    import torch
    torch.manual_seed(0)
    np.random.seed(0)
    random.seed(0)
    recs = load_index("train")
    ds = TrainSet(recs)
    dl = torch.utils.data.DataLoader(ds, batch_size=a.batch, shuffle=True, num_workers=4, drop_last=True, persistent_workers=True)
    model = build_model().cuda().train()
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=0.01)
    steps = a.epochs * len(dl)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=a.lr, total_steps=steps, pct_start=0.1)
    scaler = torch.amp.GradScaler("cuda")
    weight = torch.tensor([1.0, 1.0, a.obstacle_weight]).cuda()
    OUT.mkdir(parents=True, exist_ok=True)
    log, t0, it = [], time.time(), 0
    for ep in range(a.epochs):
        tot = 0.0
        for x, y in dl:
            x, y = x.cuda(non_blocking=True), y.cuda(non_blocking=True)
            with torch.autocast("cuda", dtype=torch.float16):
                lg = model(pixel_values=x).logits
            lg = torch.nn.functional.interpolate(lg.float(), size=y.shape[-2:], mode="bilinear", align_corners=False)
            loss = torch.nn.functional.cross_entropy(lg, y, weight=weight)
            opt.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.step(opt)
            scaler.update()
            sched.step()
            tot += float(loss)
            it += 1
        log.append(dict(epoch=ep + 1, loss=round(tot / len(dl), 4), seconds=round(time.time() - t0)))
        print("epoch %2d/%d  loss %.4f  (%.0f s, peak GPU memory %.2f GB)" % (ep + 1, a.epochs, tot / len(dl), time.time() - t0, torch.cuda.max_memory_allocated() / 1e9), flush=True)
        torch.save(model.state_dict(), OUT / "segformer_org.pt")
    import transformers
    (OUT / "train_log.json").write_text(json.dumps(dict(args=vars(a), log=log, torch=torch.__version__, transformers=transformers.__version__, train_images=len(recs), seed=0, base="data/models/segformer-b0-ade", date=time.strftime("%Y-%m-%d %H:%M")), indent=1))


def components(mask, min_area):
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    return [(int(s[0]), int(s[1]), int(s[2]), int(s[3]), int(s[4])) for s in stats[1:] if s[4] >= min_area]


def evaluate(a):
    import torch
    model = build_model(a.weights or str(OUT / "segformer_org.pt")).cuda().eval()
    recs = load_index("test")[::a.every]
    conf = np.zeros((3, 3), dtype=np.int64)
    n_obj = hit_obj = n_fp = 0
    contact_err, per_scene = [], {}
    for k, r in enumerate(recs):
        d = CACHE / "test"
        img = cv2.imread(str(d / (r["stem"] + ".jpg")))
        lab = cv2.imread(str(d / (r["stem"] + ".png")), cv2.IMREAD_UNCHANGED)
        pred = predict(model, img)
        conf += np.bincount(lab.reshape(-1).astype(np.int64) * 3 + pred.reshape(-1), minlength=9).reshape(3, 3)
        obst = pred == 2
        comps = components(obst, a.min_area)
        gt_boxes = [b[:4] for b in r["boxes"]]
        covered = np.zeros(len(comps), dtype=bool)
        sc = per_scene.setdefault(r["scene"], dict(objects=0, found=0, fp=0, images=0))
        sc["images"] += 1
        for bx, by, bw, bh in gt_boxes:
            x0, y0, x1, y1 = int(bx), int(by), int(bx + bw) + 1, int(by + bh) + 1
            area = max(1, (x1 - x0) * (y1 - y0))
            cov = obst[max(0, y0):y1, max(0, x0):x1].sum() / float(area)
            n_obj += 1
            sc["objects"] += 1
            if cov >= a.min_cover:
                hit_obj += 1
                sc["found"] += 1
                ys = np.nonzero(obst[max(0, y0 - 6):y1 + 6, max(0, x0 - 6):x1 + 6].any(1))[0]
                if len(ys):
                    contact_err.append(float(ys.max() + max(0, y0 - 6) - (by + bh)))
            for i, (cx, cy, cw, ch, _) in enumerate(comps):                  # a component overlapping a GT box (dilated by 12 px) is not a false one
                if cx < x1 + 12 and cx + cw > x0 - 12 and cy < y1 + 12 and cy + ch > y0 - 12:
                    covered[i] = True
        fp = int((~covered).sum())
        n_fp += fp
        sc["fp"] += fp
        if (k + 1) % 200 == 0:
            print("  %d/%d images" % (k + 1, len(recs)), flush=True)
    iou = [conf[c, c] / float(conf[c].sum() + conf[:, c].sum() - conf[c, c]) for c in range(3)]
    ce = np.array(contact_err) if contact_err else np.array([0.0])
    res = dict(images=len(recs), iou={CLASSES[c]: round(iou[c], 4) for c in range(3)}, miou=round(float(np.mean(iou)), 4),
               obstacle_pixel_precision=round(conf[2, 2] / float(conf[:, 2].sum()), 4), obstacle_pixel_recall=round(conf[2, 2] / float(conf[2].sum()), 4),
               ground_pixels_called_obstacle_fraction=round(conf[1, 2] / float(conf[1].sum()), 6),
               objects=n_obj, objects_found=hit_obj, object_recall=round(hit_obj / float(max(1, n_obj)), 4), false_components=n_fp, false_components_per_image=round(n_fp / float(len(recs)), 3),
               contact_row_error_px_at_960x540=dict(median_abs=round(float(np.median(np.abs(ce))), 2), p90_abs=round(float(np.percentile(np.abs(ce), 90)), 2), median_signed=round(float(np.median(ce)), 2), n=len(contact_err)),
               per_scene=per_scene, min_area=a.min_area, min_cover=a.min_cover, weights=a.weights or str(OUT / "segformer_org.pt"), test_scenes=sorted(per_scene))
    out = OUT / ("eval_%s.json" % a.tag)
    out.write_text(json.dumps(res, indent=1))
    print(json.dumps({k: v for k, v in res.items() if k != "per_scene"}, indent=1))
    print("saved", out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("cache")
    t = sub.add_parser("train")
    t.add_argument("--epochs", type=int, default=15)
    t.add_argument("--batch", type=int, default=6)
    t.add_argument("--lr", type=float, default=6e-5)
    t.add_argument("--obstacle-weight", type=float, default=8.0)
    e = sub.add_parser("eval")
    e.add_argument("--weights", default=None)
    e.add_argument("--every", type=int, default=1, help="use every n-th test image")
    e.add_argument("--min-area", type=int, default=30, help="smallest predicted obstacle component (pixels at 960x540)")
    e.add_argument("--min-cover", type=float, default=0.3)
    e.add_argument("--tag", default="test")
    a = ap.parse_args()
    {"cache": lambda: cache(), "train": lambda: train(a), "eval": lambda: evaluate(a)}[a.cmd]()


if __name__ == "__main__":
    main()
