"""Offline YOLO-World with full-frame + overlapping floor crops and merged NMS."""
import math
from pathlib import Path

import numpy as np


def box_iou(a, b):
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - intersection
    return intersection / union if union > 0 else 0.0


def merge_proposals(detections, iou):
    if not math.isfinite(iou) or not 0 < iou <= 1:
        raise ValueError("NMS IoU must be in (0,1]")
    kept = []
    for detection in sorted(detections, key=lambda d: d.confidence, reverse=True):
        if not any(box_iou(detection.xyxy, other.xyxy) >= iou for other in kept):
            kept.append(detection)
    return tuple(kept)


class WorldPredictor:
    def __init__(self, weights, settings):
        if not Path(weights).is_file():
            raise FileNotFoundError("prepare offline vocabulary: python -m tools.fetch_floor_model --world")
        from ultralytics import YOLOWorld
        from ultralytics.cfg import DEFAULT_CFG_DICT
        self.model = YOLOWorld(str(weights))
        self.settings = settings
        self.precision = {"quantize": 32} if "quantize" in DEFAULT_CFG_DICT else {"half": False}
        names = self.model.names
        names = list(names.values()) if isinstance(names, dict) else list(names)
        if names != settings["prompts"]:
            raise ValueError("offline model vocabulary differs from config; rebuild it")
        if (type(settings["tiles"]) is not int or not 1 <= settings["tiles"] <= 8
                or not 0 < settings["floor_crop_fraction"] < 1
                or not 0 <= settings["tile_overlap"] < 1
                or not 0 < settings["confidence"] <= 1):
            raise ValueError("invalid floor crop/vocabulary settings")

    def __call__(self, image):
        from .obstacle import Detection
        s = self.settings
        h, w = image.shape[:2]
        top = int(h * s["floor_crop_fraction"])
        width = min(w, int(math.ceil(w / s["tiles"] * (1 + s["tile_overlap"]))))
        origins = np.linspace(0, w - width, s["tiles"]).round().astype(int)
        crops = [(0, 0, image)] + [(int(x), top, image[top:, x:x + width]) for x in origins]
        detections = []
        for x, y, crop in crops:
            result = self.model.predict(crop, imgsz=s["imgsz"], conf=s["confidence"],
                                        device=s["device"], verbose=False, **self.precision)[0]
            if result.boxes is None:
                continue
            for b, confidence, label in zip(result.boxes.xyxy.cpu().numpy(), result.boxes.conf.cpu().numpy(),
                                            result.boxes.cls.cpu().numpy()):
                # A cut object at an artificial tile boundary must be supplied
                # by an overlapping tile/full frame, never a false ground foot.
                if y and (b[0] <= 1 or b[1] <= 1 or b[2] >= crop.shape[1] - 1 or b[3] >= crop.shape[0] - 1):
                    continue
                box = tuple(map(float, b + np.array([x, y, x, y])))
                detections.append(Detection(-2, float(confidence), box, source="open_vocabulary",
                                            label=result.names[int(label)]))
        return merge_proposals(detections, s["nms_iou"])
