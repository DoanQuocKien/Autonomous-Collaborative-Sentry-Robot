"""YOLOv8 pre/post-processing for the TensorRT engines on the Jetson (numpy + cv2 only, Python 3.6).

letterbox(): BGR frame -> (1,3,S,S) float32 blob in [0,1], RGB, grey padding (114) like ultralytics; returns what is needed to map boxes back.
decode(): raw output (1, 4+nc, N) of a detect model, or (1, 4+1+17*3, N) of the pose model -> boxes in ORIGINAL image pixels.
The NMS is plain numpy: after the confidence filter there are only a few dozen boxes, so it is not worth a dependency.
"""
import numpy as np
import cv2


def letterbox(frame, size=320):
    h, w = frame.shape[:2]
    scale = min(size / float(w), size / float(h))
    nw, nh = int(round(w * scale)), int(round(h * scale))
    img = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LINEAR)
    px, py = (size - nw) // 2, (size - nh) // 2
    canvas = np.full((size, size, 3), 114, np.uint8)
    canvas[py:py + nh, px:px + nw] = img
    blob = cv2.dnn.blobFromImage(canvas, 1.0 / 255.0, swapRB=True)    # one C++ pass: BGR->RGB, /255, NCHW float32 (was 3 numpy passes)
    return blob, scale, px, py


def nms(boxes, scores, iou_thr=0.45):
    """boxes (n,4) xyxy -> indices kept, best score first."""
    order = np.argsort(-scores)
    keep = []
    while order.size:
        i = order[0]
        keep.append(int(i))
        if order.size == 1:
            break
        rest = order[1:]
        xx1 = np.maximum(boxes[i, 0], boxes[rest, 0]); yy1 = np.maximum(boxes[i, 1], boxes[rest, 1])
        xx2 = np.minimum(boxes[i, 2], boxes[rest, 2]); yy2 = np.minimum(boxes[i, 3], boxes[rest, 3])
        inter = np.clip(xx2 - xx1, 0, None) * np.clip(yy2 - yy1, 0, None)
        area = lambda b: (b[..., 2] - b[..., 0]) * (b[..., 3] - b[..., 1])
        iou = inter / (area(boxes[i]) + area(boxes[rest]) - inter + 1e-9)
        order = rest[iou <= iou_thr]
    return keep


def decode(out, scale, px, py, conf=0.25, iou=0.45, n_kpt=0, classes=None):
    """-> (boxes (k,4) xyxy original px, scores (k,), class ids (k,), keypoints (k,n_kpt,3) or None)."""
    pred = np.asarray(out)[0].T                      # (N, 4+nc) or (N, 4+1+3*n_kpt)
    if n_kpt:
        scores, cls = pred[:, 4], np.zeros(len(pred), np.int64)
    else:
        sc = pred[:, 4:]
        scores = sc.max(1)
        # the class argmax (80 classes x 2100 anchors) runs only on the rows that survive the threshold, below
    m = scores > conf
    pred, scores = pred[m], scores[m]
    cls = np.zeros(len(pred), np.int64) if n_kpt else pred[:, 4:].argmax(1)
    if classes is not None:
        k = np.isin(cls, classes)
        pred, scores, cls = pred[k], scores[k], cls[k]
    if not len(pred):
        return np.zeros((0, 4), np.float32), scores, cls, None
    cx, cy, w, h = pred[:, 0], pred[:, 1], pred[:, 2], pred[:, 3]
    boxes = np.stack([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], 1)
    keep = nms(boxes, scores, iou)
    boxes, scores, cls, pred = boxes[keep], scores[keep], cls[keep], pred[keep]
    boxes[:, [0, 2]] = (boxes[:, [0, 2]] - px) / scale
    boxes[:, [1, 3]] = (boxes[:, [1, 3]] - py) / scale
    kpts = None
    if n_kpt:
        kpts = pred[:, 5:5 + 3 * n_kpt].reshape(-1, n_kpt, 3).copy()
        kpts[:, :, 0] = (kpts[:, :, 0] - px) / scale
        kpts[:, :, 1] = (kpts[:, :, 1] - py) / scale
    return boxes.astype(np.float32), scores, cls, kpts
