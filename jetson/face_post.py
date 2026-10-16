"""Face pipeline pre/post-processing for the TensorRT engines on the Jetson (numpy + cv2 only, Python 3.6).

SCRFD (insightface det_500m): 9 outputs = scores (n,1), boxes (n,4), landmarks (n,10) for strides 8/16/32, two anchors per cell, n = 2*(S/stride)^2.
TensorRT returns the outputs in ANOTHER order than the ONNX file, so decode_scrfd() sorts them by their anchor count, not by position.
align() warps a face to the 112x112 ArcFace template from its 5 landmarks; embed_blob() makes the MobileFaceNet (w600k_mbf) input.
"""
import numpy as np
import cv2

from yolo_post import nms

ARCFACE_112 = np.array([[38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366], [41.5493, 92.3655], [70.7299, 92.2041]], np.float32)
STRIDES = (8, 16, 32)


def scrfd_input(frame, size=320):
    """BGR frame -> (blob (1,3,S,S) float32 normalised (x-127.5)/128 RGB, scale, pad_x, pad_y); letterboxed top-left like insightface."""
    h, w = frame.shape[:2]
    scale = min(size / float(w), size / float(h))
    nw, nh = int(round(w * scale)), int(round(h * scale))
    canvas = np.zeros((size, size, 3), np.uint8)
    canvas[:nh, :nw] = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LINEAR)
    return cv2.dnn.blobFromImage(canvas, 1.0 / 128.0, (size, size), (127.5, 127.5, 127.5), swapRB=True), scale


def _anchors(size, stride):
    n = size // stride
    ys, xs = np.mgrid[:n, :n]
    c = np.stack([xs, ys], -1).reshape(-1, 2).astype(np.float32) * stride
    return np.repeat(c, 2, axis=0)                         # two anchors per cell, same centre


def decode_scrfd(outs, scale, size=320, thr=0.5, iou=0.4):
    """-> (boxes (k,4) xyxy in ORIGINAL pixels, scores (k,), landmarks (k,5,2) in ORIGINAL pixels)."""
    by_n = {}
    for o in outs:
        o = np.asarray(o)
        by_n.setdefault(o.shape[0], {})[o.shape[1]] = o
    boxes, scores, kps = [], [], []
    for stride in STRIDES:
        d = by_n.get(2 * (size // stride) ** 2)
        if d is None:
            continue
        a = _anchors(size, stride)
        s = d[1][:, 0]
        m = s > thr
        if not m.any():
            continue
        a, dist, kp = a[m], d[4][m] * stride, d[10][m] * stride
        boxes.append(np.stack([a[:, 0] - dist[:, 0], a[:, 1] - dist[:, 1], a[:, 0] + dist[:, 2], a[:, 1] + dist[:, 3]], 1))
        kps.append(kp.reshape(-1, 5, 2) + a[:, None, :])
        scores.append(s[m])
    if not boxes:
        return np.zeros((0, 4), np.float32), np.zeros(0, np.float32), np.zeros((0, 5, 2), np.float32)
    boxes, scores, kps = np.concatenate(boxes), np.concatenate(scores), np.concatenate(kps)
    keep = nms(boxes, scores, iou)
    return (boxes[keep] / scale).astype(np.float32), scores[keep], (kps[keep] / scale).astype(np.float32)


def align(frame, kps5):
    """5 landmarks (5,2) in frame pixels -> 112x112 BGR face crop (similarity transform to the ArcFace template)."""
    m = cv2.estimateAffinePartial2D(np.asarray(kps5, np.float32), ARCFACE_112, method=cv2.LMEDS)[0]
    return cv2.warpAffine(frame, m, (112, 112), borderValue=0)


def embed_blob(face112):
    """112x112 BGR crop -> MobileFaceNet input (1,3,112,112) float32, (x-127.5)/127.5, RGB."""
    return cv2.dnn.blobFromImage(face112, 1.0 / 127.5, (112, 112), (127.5, 127.5, 127.5), swapRB=True)


def unit(v):
    v = np.asarray(v, np.float32).ravel()
    return v / (np.linalg.norm(v) + 1e-12)
