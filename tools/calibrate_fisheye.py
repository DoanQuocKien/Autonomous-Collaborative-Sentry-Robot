"""Fisheye (equidistant, cv2.fisheye) calibration from the D1 checkerboard photos -> calib/camera.json.

    python -m tools.calibrate_fisheye                          # data/D1/checkerboard/*.jpg, 9x6 inner corners, 25 mm squares
    python -m tools.calibrate_fisheye --metrics reports/<handle>/week-02/fisheye_metrics.json
Exit code 1 when the final RMS reprojection error is above --max-rms (plan 4.3: < 1.0 px).
Views whose own mean error is above --drop-above px are dropped one at a time (worst first, at most --max-drop of the views) and listed in the output: a bent board or a blurred photo is not the lens.
Stability check: the same calibration on the odd and on the even views; fx / cx / cy should agree within a few px.
The images must come from the same stream that the models will see (640x480 from camera_pub.py): K is only valid for that size.
"""
import argparse
import json
from datetime import date
from pathlib import Path

import cv2
import numpy as np

_fisheye = getattr(cv2, "fisheye", cv2)
FLAGS = getattr(_fisheye, "CALIB_RECOMPUTE_EXTRINSIC", getattr(cv2, "CALIB_RECOMPUTE_EXTRINSIC", 2)) + getattr(
    _fisheye, "CALIB_FIX_SKEW", getattr(cv2, "CALIB_FIX_SKEW", 8)
)
CRIT = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 1e-6)


def board_points(pattern=(9, 6), square_m=0.025):
    obj = np.zeros((1, pattern[0] * pattern[1], 3), np.float32)
    obj[0, :, :2] = np.mgrid[0:pattern[0], 0:pattern[1]].T.reshape(-1, 2) * square_m
    return obj


def find_corners(gray, pattern=(9, 6)):
    """(1, N, 2) float64 sub-pixel corners, or None when the board is not found."""
    ok, c = cv2.findChessboardCorners(gray, pattern, cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE)
    if not ok:
        return None
    c = cv2.cornerSubPix(gray, c, (5, 5), (-1, -1), (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.01))
    return c.reshape(1, -1, 2).astype(np.float64)


def _fit(obj, img, size):
    K, D = np.eye(3), np.zeros((4, 1))
    return cv2.fisheye.calibrate(obj, img, size, K, D, flags=FLAGS, criteria=CRIT)


def view_errors(obj, img, K, D, rvecs, tvecs):
    """Mean reprojection error (px) per view."""
    return np.array([np.sqrt(((cv2.fisheye.projectPoints(o, r, t, K, D)[0] - i) ** 2).sum(-1)).mean() for o, i, r, t in zip(obj, img, rvecs, tvecs)])


def calibrate(obj, img, size, drop_above=2.5, max_drop=0.15, min_views=20):
    """obj / img: lists of (1, N, 3) / (1, N, 2) arrays, one per view. -> dict with K, D, rms, kept / dropped view indices and the first fit's per-view errors."""
    keep, dropped, first = list(range(len(img))), [], None
    while True:
        rms, K, D, rv, tv = _fit([obj[i] for i in keep], [img[i] for i in keep], size)
        errs = view_errors([obj[i] for i in keep], [img[i] for i in keep], K, D, rv, tv)
        if first is None:
            first = {"rms": float(rms), "view_errors": {i: float(e) for i, e in zip(keep, errs)}}
        worst = int(np.argmax(errs))
        if errs[worst] <= drop_above or len(dropped) + 1 > max_drop * len(img) or len(keep) - 1 < min_views:
            break
        dropped.append(keep.pop(worst))
    return {"K": K, "D": D, "rms": float(rms), "kept": keep, "dropped": dropped, "first_fit": first}


def stability(obj, img, kept, size):
    """fx, cx, cy of the same calibration on the odd and on the even kept views."""
    out = []
    for part in (kept[0::2], kept[1::2]):
        rms, K, _, _, _ = _fit([obj[i] for i in part], [img[i] for i in part], size)
        out.append({"views": len(part), "rms": float(rms), "fx": float(K[0, 0]), "fy": float(K[1, 1]), "cx": float(K[0, 2]), "cy": float(K[1, 2])})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", default="data/D1/checkerboard")
    ap.add_argument("--pattern", type=int, nargs=2, default=[9, 6], help="inner corners (cols rows)")
    ap.add_argument("--square-mm", type=float, default=25.0)
    ap.add_argument("--out", default="calib/camera.json")
    ap.add_argument("--metrics", default="", help="optional metrics JSON (per-view errors, stability)")
    ap.add_argument("--max-rms", type=float, default=1.0)
    ap.add_argument("--drop-above", type=float, default=2.5)
    ap.add_argument("--max-drop", type=float, default=0.15)
    a = ap.parse_args()
    pattern, obj1 = tuple(a.pattern), board_points(tuple(a.pattern), a.square_mm / 1000.0)
    files, img, size, missing = [], [], None, []
    for f in sorted(Path(a.images).glob("*.jpg")):
        g = cv2.imread(str(f), cv2.IMREAD_GRAYSCALE)
        if size is None:
            size = (g.shape[1], g.shape[0])
        c = find_corners(g, pattern) if (g.shape[1], g.shape[0]) == size else None
        if c is None:
            missing.append(f.name)
        else:
            files.append(f.name)
            img.append(c)
    if len(img) < 20:
        raise SystemExit("only %d usable photos in %s (need 20+; without the board: %s)" % (len(img), a.images, missing[:5]))
    obj = [obj1] * len(img)
    res = calibrate(obj, img, size, a.drop_above, a.max_drop)
    stab = stability(obj, img, res["kept"], size)
    K, D = res["K"], res["D"]
    out = {"model": "opencv_fisheye_equidistant", "image_size": list(size), "K": K.tolist(), "D": D.ravel().tolist(), "rms_px": res["rms"],
           "views_used": len(res["kept"]), "views_dropped": [files[i] for i in res["dropped"]], "square_m": a.square_mm / 1000.0, "pattern": list(pattern),
           "date": date.today().isoformat(), "opencv": cv2.__version__}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    ok = res["rms"] < a.max_rms
    print("%d photos with the board (%d without), dropped %d: %s" % (len(img), len(missing), len(res["dropped"]), out["views_dropped"]))
    print("RMS %.3f px on %d views (all %d views: %.3f px)  fx %.1f fy %.1f cx %.1f cy %.1f  D %s" % (res["rms"], len(res["kept"]), len(img), res["first_fit"]["rms"], K[0, 0], K[1, 1], K[0, 2], K[1, 2], np.round(D.ravel(), 4)))
    print("odd / even halves: fx %.1f / %.1f, cx %.1f / %.1f, cy %.1f / %.1f" % (stab[0]["fx"], stab[1]["fx"], stab[0]["cx"], stab[1]["cx"], stab[0]["cy"], stab[1]["cy"]))
    print("%s (target RMS < %.2f px) -> %s" % ("PASS" if ok else "FAIL", a.max_rms, a.out))
    if a.metrics:
        m = dict(out, passed=ok, max_rms=a.max_rms, first_fit_rms_px=res["first_fit"]["rms"], first_fit_view_errors={files[i]: e for i, e in res["first_fit"]["view_errors"].items()}, photos_without_board=missing, stability=stab)
        Path(a.metrics).parent.mkdir(parents=True, exist_ok=True)
        Path(a.metrics).write_text(json.dumps(m, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
