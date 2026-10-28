"""Edge conversion parity (plan 4.3): TensorRT FP16 engines on the robot against ONNX Runtime FP32 on the laptop, on the same inputs.

  1. python -m tools.edge_parity prep --onnx-dir data/parity/onnx           # laptop: inputs + ONNX Runtime outputs -> data/parity/
  2. copy data/parity/parity_in.npz to the robot, run jetson/parity_run.py there, copy parity_trt.npz back
  3. python -m tools.edge_parity compare                                    # table + data/parity/parity_results.json

Inputs: 200 D1 obstacle frames (no faces; data/D1_obstacles_1015/*/jetbot, evenly spaced) plus public photos (ultralytics bus and zidane, insightface t1 and Tom Hanks, each
also flipped) for the detectors and SCRFD, 256x128 crops of the same frames for OSNet, and aligned public faces (also darker / brighter) for MobileFaceNet. The ONNX files must be
the robot's own copies (the engines were built from them). Pass criteria (plan 4.3 'Edge conversion parity'): cosine >= 0.999 on every output; detector boxes matched at
IoU >= 0.9 for >= 95 % of detections and the same count.
"""
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "jetson"))
import face_post  # noqa: E402
import parity_run as pr  # noqa: E402
import yolo_post  # noqa: E402

ONNX = {"det": "yolov8n_320_op11.onnx", "pose": "yolov8n-pose_320_op11.onnx", "osnet": "osnet_x0_25_256x128.onnx", "scrfd": "det_500m_deconv320.onnx", "mbf": "w600k_mbf.onnx"}
COS_MIN, IOU_MIN, MATCH_MIN = 0.999, 0.9, 0.95


def d1_frames(n=200):
    files = sorted((ROOT / "data" / "D1_obstacles_1015").glob("*/jetbot/*.jpg"))
    idx = np.linspace(0, len(files) - 1, min(n, len(files))).astype(int)
    return [files[i] for i in idx]


def public_images():
    import insightface
    import ultralytics
    a = Path(ultralytics.__file__).parent / "assets"
    b = Path(insightface.__file__).parent / "data" / "images"
    paths = [a / "bus.jpg", a / "zidane.jpg", b / "t1.jpg", b / "Tom_Hanks_54745.png"]
    imgs = [cv2.imread(str(p)) for p in paths if p.exists()]
    return imgs + [cv2.flip(i, 1) for i in imgs]


def session(onnx_dir, name):
    import onnxruntime as ort
    return ort.InferenceSession(str(Path(onnx_dir) / ONNX[name]), providers=["CPUExecutionProvider"])


def run_ort(sess, blob):
    return sess.run(None, {sess.get_inputs()[0].name: blob})


def cmd_prep(a):
    out = Path(a.dir)
    out.mkdir(parents=True, exist_ok=True)
    frames = [cv2.imread(str(p)) for p in d1_frames(a.n)]
    pub = public_images()
    both = frames + pub
    yo = [pr.yolo_canvas(f) for f in both]
    yc, ym = [x[0] for x in yo], [x[1:] for x in yo]               # canvas; (scale, px, py) to map boxes back
    sc, ss = zip(*[pr.scrfd_canvas(f) for f in both])
    crops = [cv2.resize(f, (128, 256)) for f in frames]
    sess = {k: session(a.onnx_dir, k) for k in ONNX}
    # aligned public faces for MobileFaceNet: SCRFD (ONNX Runtime) finds them; each also darker and brighter
    faces = []
    for img in pub:
        canvas, scale = pr.scrfd_canvas(img)
        outs = run_ort(sess["scrfd"], pr.scrfd_blob(canvas))
        _, _, kps = face_post.decode_scrfd(outs, scale, 320, 0.5)
        for k in kps:
            f = face_post.align(img, k)
            faces += [f, np.clip(f.astype(np.float32) * 0.7, 0, 255).astype(np.uint8), np.clip(f.astype(np.float32) * 1.3, 0, 255).astype(np.uint8)]
    inp = {"yolo_canvas": np.stack(yc), "yolo_meta": np.array(ym, np.float32), "scrfd_canvas": np.stack(sc), "scrfd_scale": np.array(ss, np.float32),
           "osnet_crop": np.stack(crops), "mbf_face": np.stack(faces), "n_d1": np.array(len(frames))}
    np.savez_compressed(str(out / "parity_in.npz"), **inp)
    ort_out = {}
    for name, imgs, blob_fn, by_shape in [("det", inp["yolo_canvas"], pr.yolo_blob, False), ("pose", inp["yolo_canvas"], pr.yolo_blob, False),
                                          ("osnet", inp["osnet_crop"], pr.osnet_blob, False), ("scrfd", inp["scrfd_canvas"], pr.scrfd_blob, True),
                                          ("mbf", inp["mbf_face"], pr.mbf_blob, False)]:
        per = [run_ort(sess[name], blob_fn(im)) for im in imgs]
        ort_out.update(pr.stack_outputs(name, per, sort_by_shape=by_shape))
        print("%-6s %d inputs" % (name, len(imgs)), flush=True)
    np.savez_compressed(str(out / "parity_ort.npz"), **ort_out)
    print("wrote", out / "parity_in.npz", "and parity_ort.npz;", len(frames), "D1 frames,", len(pub), "public photos,", len(faces), "aligned faces")


def cosines(a, b):
    a = a.reshape(len(a), -1).astype(np.float64)
    b = b.reshape(len(b), -1).astype(np.float64)
    return (a * b).sum(1) / (np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1) + 1e-12)


def iou(a, b):
    x1, y1 = np.maximum(a[0], b[:, 0]), np.maximum(a[1], b[:, 1])
    x2, y2 = np.minimum(a[2], b[:, 2]), np.minimum(a[3], b[:, 3])
    inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1]) - inter + 1e-9)


def match_boxes(ba, bb):
    """Greedy best-IoU matching. -> (matched at IoU >= IOU_MIN, number of boxes in ba)."""
    if not len(ba):
        return 0, 0
    if not len(bb):
        return 0, len(ba)
    used, ok = set(), 0
    for a in ba:
        v = iou(a, bb)
        for j in np.argsort(-v):
            if int(j) not in used:
                if v[j] >= IOU_MIN:
                    ok += 1
                    used.add(int(j))
                break
    return ok, len(ba)


def detector_stats(o_arr, t_arr, meta, conf, n_kpt=0, cls_must_match=False):
    nt = mt = fa = 0
    same = 0
    for i in range(len(o_arr)):
        scale, px, py = meta[i]
        bo, so, co, _ = yolo_post.decode(o_arr[i][None], scale, px, py, conf=conf, n_kpt=n_kpt)
        bt, st, ct, _ = yolo_post.decode(t_arr[i][None], scale, px, py, conf=conf, n_kpt=n_kpt)
        ok, n = match_boxes(bo, bt)
        mt += ok
        nt += n
        fa += len(bt)
        same += int(len(bo) == len(bt))
    return {"onnx_detections": nt, "trt_detections": fa, "matched_iou_ge_0.9": mt, "matched_fraction": round(mt / nt, 4) if nt else None, "frames_with_same_count": same, "frames": len(o_arr)}


def scrfd_stats(o, t, scales, n_d1):
    nt = mt = fa = 0
    same = 0
    lm = []
    keys = [k for k in o if k.startswith("scrfd_")]
    for i in range(len(scales)):
        oo = [o[k][i] for k in keys]
        tt = [t[k][i] for k in keys]
        bo, so, ko = face_post.decode_scrfd(oo, float(scales[i]), 320, 0.5)
        bt, st, kt = face_post.decode_scrfd(tt, float(scales[i]), 320, 0.5)
        ok, n = match_boxes(bo, bt)
        mt += ok
        nt += n
        fa += len(bt)
        same += int(len(bo) == len(bt))
        for j, b in enumerate(bo):
            v = iou(b, bt) if len(bt) else []
            if len(v) and v.max() >= IOU_MIN:
                lm.append(float(np.linalg.norm(ko[j] - kt[int(np.argmax(v))], axis=1).mean()))
    return {"onnx_faces": nt, "trt_faces": fa, "matched_iou_ge_0.9": mt, "matched_fraction": round(mt / nt, 4) if nt else None, "frames_with_same_count": same, "frames": len(scales),
            "landmark_error_px_mean": round(float(np.mean(lm)), 3) if lm else None}


def cmd_compare(a):
    d = Path(a.dir)
    inp, o, t = np.load(d / "parity_in.npz"), np.load(d / "parity_ort.npz"), np.load(d / "parity_trt.npz")
    res = {"cosine": {}, "detectors": {}}
    for k in sorted(o.files):
        if k not in t.files:
            res["cosine"][k] = "MISSING in the TensorRT run"
            continue
        c = cosines(o[k], t[k])
        res["cosine"][k] = {"n": int(len(c)), "min": round(float(c.min()), 6), "p5": round(float(np.percentile(c, 5)), 6), "mean": round(float(c.mean()), 6), "pass": bool(c.min() >= COS_MIN)}
    meta = inp["yolo_meta"]
    res["detectors"]["det_conf0.25"] = detector_stats(o["det_0"], t["det_0"], meta, 0.25)
    res["detectors"]["pose_conf0.25"] = detector_stats(o["pose_0"], t["pose_0"], meta, 0.25, n_kpt=17)
    sk = {k: o[k] for k in o.files if k.startswith("scrfd_")}
    st = {k: t[k] for k in t.files if k.startswith("scrfd_")}
    res["detectors"]["scrfd_thr0.5"] = scrfd_stats(sk, st, inp["scrfd_scale"], int(inp["n_d1"]))
    allcos = [v for v in res["cosine"].values() if isinstance(v, dict)]
    res["pass_cosine_all_outputs"] = bool(allcos) and all(v["pass"] for v in allcos) and len(allcos) == len(res["cosine"])
    det_ok = []
    for name, s in res["detectors"].items():
        n = s.get("onnx_detections", s.get("onnx_faces", 0))
        f = s["matched_fraction"]
        det_ok.append(n == 0 or (f is not None and f >= MATCH_MIN and s.get("onnx_detections", s.get("onnx_faces")) == s.get("trt_detections", s.get("trt_faces"))))
    res["pass_detectors"] = all(det_ok)
    res["inputs"] = {"d1_frames": int(inp["n_d1"]), "yolo_scrfd_images": int(len(inp["yolo_canvas"])), "osnet_crops": int(len(inp["osnet_crop"])), "mbf_faces": int(len(inp["mbf_face"]))}
    (d / "parity_results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prep")
    p.add_argument("--onnx-dir", default="data/parity/onnx")
    p.add_argument("--dir", default="data/parity")
    p.add_argument("--n", type=int, default=200)
    p.set_defaults(fn=cmd_prep)
    c = sub.add_parser("compare")
    c.add_argument("--dir", default="data/parity")
    c.set_defaults(fn=cmd_compare)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
