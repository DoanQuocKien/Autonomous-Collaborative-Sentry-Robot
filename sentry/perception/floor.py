"""Optional semantic floor evidence, contact refinement and class-agnostic hazards.

ADE labels are not COCO IDs. No floor prediction automatically clears the map.
Both image semantics and a local foreground-to-floor image edge are required for
distance. Shadows, reflections and objects smaller than the model's resolution
remain limitations; this is evidence for evaluation, not a free-space guarantee.
"""
from dataclasses import dataclass, replace
import math
from pathlib import Path

import cv2
import numpy as np

from .contact import ContactEstimate


@dataclass(frozen=True)
class FloorEvidence:
    floor_probability: np.ndarray
    labels: np.ndarray
    confidence: np.ndarray
    edge_strength: np.ndarray | None = None

    def validate(self, shape):
        for value in (self.floor_probability, self.labels, self.confidence):
            if not isinstance(value, np.ndarray) or value.shape != shape:
                raise ValueError("semantic evidence must match the rectified image")
        for value in (self.floor_probability, self.confidence):
            if not np.isfinite(value).all() or (value < 0).any() or (value > 1).any():
                raise ValueError("semantic probabilities must be finite in [0,1]")
        if not np.issubdtype(self.labels.dtype, np.integer) or (self.labels < 0).any():
            raise ValueError("nonnegative integer semantic labels required")


class SegformerFloorPredictor:
    """Local safetensors only; no torch.hub, remote code or implicit download."""
    def __init__(self, model_path, settings):
        path = Path(model_path)
        for name in ("model.safetensors", "config.json", "preprocessor_config.json"):
            if not (path / name).is_file():
                raise FileNotFoundError("fetch semantic weights: python -m tools.fetch_floor_model")
        try:
            import torch
            from transformers import SegformerForSemanticSegmentation, SegformerImageProcessor
        except ImportError as e:
            raise ImportError("install optional requirements-floor.txt") from e
        self.torch, self.device = torch, settings["device"]
        self.model = SegformerForSemanticSegmentation.from_pretrained(
            str(path), local_files_only=True, use_safetensors=True).to(self.device).eval()
        # Old checkpoint metadata calls these feature_extractor_type/reduce_labels.
        # They affect label training, not input RGB preprocessing; avoid version warnings.
        import json
        processor_config = json.loads((path / "preprocessor_config.json").read_text())
        processor_config.pop("feature_extractor_type", None)
        processor_config["do_reduce_labels"] = processor_config.pop("reduce_labels", False)
        self.processor = SegformerImageProcessor(**processor_config)
        self.floor_ids = tuple(settings["floor_ids"])
        if not self.floor_ids or any(i < 0 or i >= self.model.config.num_labels for i in self.floor_ids):
            raise ValueError("floor label IDs outside semantic model")
        self.label_names = self.model.config.id2label

    def __call__(self, rectified_bgr):
        torch = self.torch
        inputs = self.processor(images=cv2.cvtColor(rectified_bgr, cv2.COLOR_BGR2RGB),
                                return_tensors="pt").to(self.device)
        with torch.inference_mode():
            logits = self.model(**inputs).logits
            probabilities = torch.nn.functional.interpolate(
                logits, size=rectified_bgr.shape[:2], mode="bilinear", align_corners=False).softmax(1)[0]
            confidence, labels = probabilities.max(0)
            floor = probabilities[list(self.floor_ids)].sum(0)
        return FloorEvidence(floor.cpu().numpy(), labels.cpu().numpy(), confidence.cpu().numpy())


class SemanticFloorAnalyzer:
    def __init__(self, predictor, settings):
        self.predictor, self.settings = predictor, dict(settings)
        for key in ("min_component_px", "contact_search_px", "contact_above_px", "contact_strip_px",
                    "contact_min_columns", "contact_cluster_px", "contact_background_px"):
            if type(settings[key]) is not int or settings[key] < 1:
                raise ValueError("positive integer semantic windows required")
        for key in ("floor_confidence", "object_confidence", "max_component_fraction",
                    "candidate_overlap", "contact_floor_fraction"):
            if not math.isfinite(settings[key]) or not 0 < settings[key] <= 1:
                raise ValueError("semantic thresholds must be in (0,1]")
        if not math.isfinite(settings["contact_min_contrast"]) or settings["contact_min_contrast"] <= 0:
            raise ValueError("positive contact contrast required")

    def __call__(self, image):
        evidence = self.predictor(image)
        evidence.validate(image.shape[:2])
        return replace(evidence, edge_strength=self._edges(image, evidence))

    def _edges(self, image, evidence):
        s = self.settings
        strip = s["contact_strip_px"]
        flank = s["contact_background_px"]
        rgb = image.astype(np.float32)
        mask = (evidence.floor_probability >= s["floor_confidence"]).astype(np.float32)
        count = cv2.boxFilter(mask, -1, (2 * flank + 1, strip), anchor=(flank, 0), normalize=False)
        background = cv2.boxFilter(rgb * mask[..., None], -1, (2 * flank + 1, strip), anchor=(flank, 0), normalize=False)
        background /= np.maximum(count, 1)[..., None]
        kernel = np.zeros((strip * 2, 3), np.float32)
        kernel[:strip] = 1 / (strip * 3)
        above = cv2.filter2D(rgb, -1, kernel, anchor=(1, strip))
        below = cv2.filter2D(rgb, -1, kernel[::-1].copy(), anchor=(1, strip))
        strength = np.linalg.norm(above - background, axis=2) - np.linalg.norm(below - background, axis=2)
        fraction = cv2.boxFilter(mask, -1, (3, strip), anchor=(1, 0))
        strength[(fraction < s["contact_floor_fraction"]) | (count < strip)] = -np.inf
        return strength

    def object_mask(self, evidence):
        s = self.settings
        return ((evidence.confidence >= s["object_confidence"])
                & ~np.isin(evidence.labels, s["floor_ids"])
                & ~np.isin(evidence.labels, s["ignore_label_ids"])
                & (evidence.floor_probability < 1 - s["floor_confidence"]))

    def contact(self, image, box, evidence, valid):
        """Follow semantic object seeds to a supported local image edge.

        Sparse chair legs need column evidence: taking a median over a whole
        chair box erases them. The image edge can refine an undersegmented leg,
        but an edge without an object seed and floor underneath is insufficient.
        """
        s = self.settings
        h, w = image.shape[:2]
        x1, y1, x2, bottom = box
        left, right = max(1, int(math.ceil(x1))), min(w - 1, int(math.floor(x2)))
        lo, hi = max(0, int(bottom) - s["contact_above_px"]), min(h, int(bottom) + s["contact_search_px"])
        if right - left < s["contact_min_columns"] or hi - lo < 3:
            return None
        objects = self.object_mask(evidence)
        edges = evidence.edge_strength if evidence.edge_strength is not None else self._edges(image, evidence)
        strip = s["contact_strip_px"]
        peaks = []
        for x in range(left, right):
            seed_rows = np.flatnonzero(objects[max(lo, int(y1)):min(hi, int(bottom) + 1), x])
            if not len(seed_rows):
                continue
            seed = int(seed_rows[-1] + max(lo, int(y1)))
            start, end = max(strip, seed - strip), min(h - strip, seed + s["contact_search_px"] + 1)
            best = None
            for y in range(start, end):
                if not valid[y - strip:y + strip, x - 1:x + 2].all():
                    continue
                contrast = float(edges[y, x])
                if contrast >= s["contact_min_contrast"] and (best is None or contrast > best[0]):
                    best = (contrast, x, y)
            if best is not None:
                peaks.append(best)
        if not peaks:
            return None
        # Require horizontal support at a consistent row; isolated highlights
        # cannot set the nearest range for an entire chair.
        groups = []
        for peak in peaks:
            neighbours = [p for p in peaks if abs(p[1] - peak[1]) <= s["contact_cluster_px"]
                          and abs(p[2] - peak[2]) <= strip]
            if len(neighbours) >= s["contact_min_columns"]:
                groups.append(neighbours)
        if not groups:
            return None
        group = max(groups, key=lambda g: float(np.median([p[2] for p in g])))
        u, v = float(np.median([p[1] for p in group])), float(np.median([p[2] for p in group]))
        confidence = float(np.mean(evidence.floor_probability[int(v):int(v) + strip, int(u)]))
        return ContactEstimate(u, v, "semantic_floor_edge", confidence)

    def proposals(self, image, evidence, valid, existing_boxes):
        """Non-floor components on the lower image, including non-COCO objects.

        Returns bbox/contact/label/confidence. Unknown components may remain
        unresolved: not every wall, reflection or component lies on the floor.
        """
        s = self.settings
        h, w = image.shape[:2]
        mask = (self.object_mask(evidence) & valid).astype(np.uint8)
        count, components, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
        proposals = []
        for i in range(1, count):
            x, y, width, height, area = map(int, stats[i])
            if area < s["min_component_px"] or area > h * w * s["max_component_fraction"]:
                continue
            if x <= 1 or y <= 1 or x + width >= w - 1 or y + height >= h - 1:
                continue
            box = (x, y, x + width, y + height)
            if any(max(0, min(box[2], b[2]) - max(x, b[0]))
                   * max(0, min(box[3], b[3]) - max(y, b[1])) / (width * height) >= s["candidate_overlap"]
                   for b in existing_boxes):
                continue
            component = components == i
            label = int(np.bincount(evidence.labels[component].astype(int)).argmax())
            confidence = float(np.mean(evidence.confidence[component]))
            contact = self.contact(image, box, evidence, valid)
            proposals.append((box, contact, label, confidence))
        return proposals
