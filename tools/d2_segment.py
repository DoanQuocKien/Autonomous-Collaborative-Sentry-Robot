"""Cut the D2 continuous clips into walk-in entries and list every usable face frame.

  python -m tools.d2_segment 1028                 # data/D2/1028/<member>/c*/  ->  faces.csv + entries.csv per clip, data/D2/1028/d2_faces.csv overall

Per frame: face detection (InsightFace buffalo_s, GPU if available) and, for the WALKER, the largest face wider than --min-face px (bystanders in the background
are small; the walker is the biggest face when present). Nothing is thrown away: every frame with a walker face goes to d2_faces.csv with its box, score,
sharpness (variance of the Laplacian of the face crop: low = motion blur) and the entry it belongs to, so the user of the set decides what is good enough
(the team decision 2026-10-28: use every frame we have). An ENTRY is a run of walker frames with gaps of at most --max-gap frames; its direction is the side of the
camera image where the face first appears (L / C / R thirds), its distance proxy is the largest face width in px.
Also writes faces.npz per clip: embeddings (512-D, L2-normalised) of the walker face of each frame, for the ROC.
"""
import argparse
import csv
from pathlib import Path

import numpy as np

IMG_W = 640


def side(cx, width=IMG_W):
    return "L" if cx < width / 3.0 else ("R" if cx > 2 * width / 3.0 else "C")


def segment(rows, max_gap=3):
    """rows: dicts with frame (int), cx (float), width (float) for the frames where the walker was seen, in frame order.
    -> list of entries: dict(first, last, frames, direction, max_width), one per run of frames with gaps <= max_gap."""
    entries, cur = [], None
    for r in rows:
        if cur is not None and r["frame"] - cur["last"] <= max_gap:
            cur["last"] = r["frame"]
            cur["frames"] += 1
            cur["max_width"] = max(cur["max_width"], r["width"])
        else:
            if cur is not None:
                entries.append(cur)
            cur = {"first": r["frame"], "last": r["frame"], "frames": 1, "direction": side(r["cx"]), "max_width": r["width"]}
    if cur is not None:
        entries.append(cur)
    return entries


def sharpness(img, box):
    import cv2
    x1, y1, x2, y2 = [int(v) for v in box]
    h, w = img.shape[:2]
    crop = img[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
    if crop.size == 0:
        return 0.0
    g = cv2.cvtColor(cv2.resize(crop, (112, 112)), cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(g, cv2.CV_64F).var())


def make_encoder():
    from sentry.perception.face import InsightFaceEncoder
    try:
        return InsightFaceEncoder(device="cuda"), "cuda"
    except Exception as e:             # no CUDA provider: slow but works
        print("GPU not usable (%s), using the CPU" % (str(e)[:60],))
        return InsightFaceEncoder(device="cpu"), "cpu"


def process_clip(enc, clip, min_face, max_gap):
    import cv2
    files = sorted(clip.glob("f*.jpg"))
    frame_rows, walker, embs = [], [], []
    for i, f in enumerate(files):
        img = cv2.imread(str(f))
        faces = enc.extract(img)
        big = max(faces, key=lambda x: x["bbox"][2] - x["bbox"][0]) if faces else None
        wd = (big["bbox"][2] - big["bbox"][0]) if big else 0.0
        is_walker = big is not None and wd >= min_face
        cx = (big["bbox"][0] + big["bbox"][2]) / 2.0 if big else -1.0
        sharp = sharpness(img, big["bbox"]) if is_walker else 0.0
        frame_rows.append([f.name, len(faces), round(wd, 1), round(cx, 1), round(big["confidence"], 3) if big else 0, int(is_walker), round(sharp, 1)])
        if is_walker:
            walker.append({"frame": i, "cx": cx, "width": wd, "name": f.name, "box": [round(float(v), 1) for v in big["bbox"]],
                           "score": round(big["confidence"], 3), "sharp": round(sharp, 1)})
            embs.append(big["embedding"])
    entries = segment(walker, max_gap)
    with (clip / "faces.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["frame_file", "n_faces", "biggest_width_px", "biggest_cx", "biggest_score", "walker", "sharpness"])
        w.writerows(frame_rows)
    with (clip / "entries.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["entry", "first_frame", "last_frame", "walker_frames", "direction", "max_width_px"])
        for k, e in enumerate(entries, 1):
            w.writerow([k, e["first"], e["last"], e["frames"], e["direction"], round(e["max_width"], 1)])
    if embs:
        np.savez_compressed(str(clip / "faces.npz"), frame_files=np.array([r["name"] for r in walker]), embeddings=np.array(embs, np.float32))
    for k, e in enumerate(entries, 1):                 # entry number of every walker frame
        for r in walker:
            if e["first"] <= r["frame"] <= e["last"]:
                r["entry"], r["direction"] = k, e["direction"]
    return len(files), walker, entries


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("session", help="folder under data/D2, e.g. 1028")
    ap.add_argument("--min-face", type=float, default=45.0, help="a face at least this wide (px) is the walker; narrower ones are bystanders")
    ap.add_argument("--max-gap", type=int, default=3, help="frames without a walker face that still belong to the same entry")
    ap.add_argument("--out", default="data/D2")
    a = ap.parse_args()
    root = Path(a.out) / a.session
    clips = sorted(p for p in root.glob("*/c*") if p.is_dir())
    if not clips:
        raise SystemExit("no continuous clips under %s" % root)
    enc, dev = make_encoder()
    print("device:", dev, "| clips:", len(clips), flush=True)
    allrows = []
    for clip in clips:
        n, walker, entries = process_clip(enc, clip, a.min_face, a.max_gap)
        member = clip.parent.name
        sharp = [r["sharp"] for r in walker]
        sides = "".join(e["direction"] for e in entries)
        print("%-5s %-4s %3d frames: walker face in %3d (%.0f%%), %d entries [%s], max width %s px, sharpness median %s" % (
            member, clip.name, n, len(walker), 100.0 * len(walker) / max(n, 1), len(entries), sides,
            "%.0f" % max([r["width"] for r in walker]) if walker else "-", "%.0f" % float(np.median(sharp)) if sharp else "-"), flush=True)
        for r in walker:
            allrows.append([member, clip.name, r["name"], r.get("entry", 0), r.get("direction", ""), r["box"][0], r["box"][1], r["box"][2], r["box"][3], round(r["width"], 1), r["score"], r["sharp"]])
    with (root / "d2_faces.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["member", "clip", "frame_file", "entry", "direction", "x1", "y1", "x2", "y2", "width_px", "score", "sharpness"])
        w.writerows(allrows)
    print("wrote %s: %d walker face frames in total" % (root / "d2_faces.csv", len(allrows)))


if __name__ == "__main__":
    main()
