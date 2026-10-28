"""Person crops -> OSNet re-ID embeddings, usable with live or replay frames.

Loads local re-ID-trained checkpoints with pretrained=False. No model downloads,
tracking, queue mutation or motor I/O. AIN and x0.25 embeddings have identical
dimensions but different spaces: never compare vectors across model hashes.
"""
from dataclasses import dataclass
import hashlib
import math
from pathlib import Path

import cv2
import numpy as np

from sentry.config import DEFAULT_PATH, load

ARCHITECTURES = ('osnet_ain_x1_0', 'osnet_x0_25')


def normalize(vector):
    value = np.asarray(vector, dtype=np.float32)
    if value.shape != (512,) or not np.isfinite(value).all():
        raise ValueError('finite 512-dimensional re-ID vector required')
    norm = float(np.linalg.norm(value.astype(np.float64)))
    if norm <= 1e-12:
        raise ValueError('nonzero re-ID vector required')
    return value / norm


def match_gallery(query, gallery, threshold):
    """Max cosine over references per identity. Empty/tied identity matches abstain."""
    q = normalize(query)
    if not math.isfinite(threshold) or not -1 <= threshold <= 1:
        raise ValueError('finite cosine threshold in [-1,1] required')
    scores = []
    for identity, references in gallery.items():
        if not isinstance(identity, str) or not identity:
            raise ValueError('nonempty string identity required')
        if len(references):
            scores.append((identity, max(float(np.clip(q @ normalize(r), -1, 1)) for r in references)))
    if not scores:
        return None, None
    scores.sort(key=lambda row: row[1], reverse=True)
    best, score = scores[0]
    tied = len(scores) > 1 and math.isclose(score, scores[1][1], rel_tol=0, abs_tol=1e-7)
    return (best if score >= threshold and not tied else None), score


def validate_image(image):
    if (not isinstance(image, np.ndarray) or image.dtype != np.uint8
            or image.ndim != 3 or image.shape[2] != 3 or min(image.shape[:2]) < 1):
        raise ValueError('nonempty uint8 BGR image required')


def crop_person(image, xyxy, min_height=32, min_width=12):
    validate_image(image)
    if len(xyxy) != 4 or not all(math.isfinite(v) for v in xyxy):
        raise ValueError('finite xyxy box required')
    x1, y1, x2, y2 = xyxy
    if x2 <= x1 or y2 <= y1:
        raise ValueError('positive box extent required')
    h, w = image.shape[:2]
    x1, y1 = max(0, int(math.floor(x1))), max(0, int(math.floor(y1)))
    x2, y2 = min(w, int(math.ceil(x2))), min(h, int(math.ceil(y2)))
    if y2 - y1 < min_height or x2 - x1 < min_width:
        return None
    return image[y1:y2, x1:x2].copy()


def preprocess(crops, settings):
    height, width = settings['input_height'], settings['input_width']
    if any(type(v) is not int or v < 1 for v in (height, width)):
        raise ValueError('positive integer OSNet input size required')
    mean, std = np.asarray(settings['mean'], np.float32), np.asarray(settings['std'], np.float32)
    if (mean.shape != (3,) or std.shape != (3,) or not np.isfinite(mean).all()
            or not np.isfinite(std).all() or (std <= 0).any()):
        raise ValueError('finite RGB mean and positive std required')
    batch = []
    for crop in crops:
        validate_image(crop)
        rgb = cv2.cvtColor(cv2.resize(crop, (width, height), interpolation=cv2.INTER_LINEAR), cv2.COLOR_BGR2RGB)
        batch.append(((rgb.astype(np.float32) / 255 - mean) / std).transpose(2, 0, 1))
    return np.ascontiguousarray(np.stack(batch)) if batch else np.empty((0, 3, height, width), np.float32)


def load_reid_state(path):
    """Restricted torch deserialization, including legacy NumPy metric scalars.

    AIN's official checkpoint contains optimizer metrics. Only known NumPy scalar
    constructors are allowlisted; arbitrary checkpoint classes are never executed.
    """
    import torch
    core = np._core if hasattr(np, '_core') else np.core
    safe = [(core.multiarray.scalar, 'numpy.core.multiarray.scalar'),
            (core.multiarray.scalar, 'numpy._core.multiarray.scalar'), np.dtype,
            type(np.dtype('float64')), type(np.dtype('float32')), type(np.dtype('int64'))]
    with torch.serialization.safe_globals(safe):
        saved = torch.load(str(path), map_location='cpu', weights_only=True)
    if not isinstance(saved, dict):
        raise ValueError('expected OSNet state mapping')
    saved = saved.get('state_dict', saved)
    if not isinstance(saved, dict):
        raise ValueError('expected OSNet tensor state mapping')
    return {k.removeprefix('module.'): v for k, v in saved.items() if isinstance(k, str)}


class OSNetEncoder:
    def __init__(self, architecture, weights, settings, device=None):
        if architecture not in ARCHITECTURES:
            raise ValueError('unsupported OSNet architecture')
        weights = Path(weights)
        if not weights.is_file():
            raise FileNotFoundError('fetch re-ID-trained weights with tools.fetch_models: ' + str(weights))
        import torch
        import torchreid
        self.torch, self.settings = torch, dict(settings)
        self.device = device or settings['device']
        self.model = torchreid.models.build_model(name=architecture, num_classes=1000, pretrained=False)
        have, state = self.model.state_dict(), load_reid_state(weights)
        needed = {k for k in have if not k.startswith('classifier.') and not k.endswith('num_batches_tracked')}
        missing = [k for k in needed if k not in state or not torch.is_tensor(state[k]) or state[k].shape != have[k].shape]
        extra = [k for k in state if k not in have and not k.startswith('classifier.')]
        if missing or extra:
            raise ValueError('OSNet backbone checkpoint mismatch: missing=%s extra=%s' % (missing[:5], extra[:5]))
        self.model.load_state_dict({k: v for k, v in state.items() if k in have and not k.startswith('classifier.')}, strict=False)
        self.model.to(self.device).eval()
        self.architecture = architecture
        self.weights_sha256 = hashlib.sha256(weights.read_bytes()).hexdigest()
        self.model_id = architecture + ':' + self.weights_sha256

    @classmethod
    def from_config(cls, architecture=None, config_path=DEFAULT_PATH, device=None):
        settings = load(config_path)['reid']
        architecture = architecture or settings['model']
        key = 'ain_weights' if architecture == 'osnet_ain_x1_0' else 'small_weights'
        return cls(architecture, Path(config_path).resolve().parent / settings[key], settings, device)

    def encode(self, crops):
        inputs = preprocess(crops, self.settings)
        if not len(inputs):
            return np.empty((0, 512), np.float32)
        with self.torch.inference_mode():
            values = self.model(self.torch.from_numpy(inputs).to(self.device)).float().cpu().numpy()
        return np.stack([normalize(value) for value in values])


@dataclass(frozen=True)
class PersonAppearance:
    xyxy: tuple
    confidence: float
    embedding: np.ndarray | None
    rejection: str | None = None


@dataclass(frozen=True)
class ReIDResult:
    t: float
    people: tuple[PersonAppearance, ...]
    model_id: str


class PersonReID:
    def __init__(self, detector, encoder, settings):
        self.detector, self.encoder, self.settings = detector, encoder, dict(settings)

    @classmethod
    def from_config(cls, config_path=DEFAULT_PATH, architecture=None):
        from .obstacle import YOLOPredictor
        config = load(config_path)
        settings = config['reid']
        yolo = dict(config['obstacle'], class_ids=[0], confidence=settings['person_confidence'],
                    imgsz=settings['person_imgsz'], device=settings['person_device'])
        detector = YOLOPredictor(Path(config_path).resolve().parent / settings['person_weights'], yolo)
        return cls(detector, OSNetEncoder.from_config(architecture, config_path), settings)

    def __call__(self, frame_bgr, t):
        validate_image(frame_bgr)
        if not math.isfinite(t):
            raise ValueError('finite frame timestamp required')
        rows, crops, accepted = [], [], []
        for detection in self.detector(frame_bgr):
            if detection.class_id != 0 or not math.isfinite(detection.confidence) or not self.settings['person_confidence'] <= detection.confidence <= 1:
                continue
            try:
                crop = crop_person(frame_bgr, detection.xyxy, self.settings['min_crop_height'], self.settings['min_crop_width'])
                reason = None if crop is not None else 'crop_too_small_or_outside'
            except ValueError:
                crop, reason = None, 'invalid_person_box'
            rows.append(PersonAppearance(tuple(detection.xyxy), float(detection.confidence), None, reason))
            if crop is not None:
                accepted.append(len(rows) - 1)
                crops.append(crop)
        vectors = self.encoder.encode(crops) if crops else []
        if len(vectors) != len(crops):
            raise ValueError('encoder output count differs from person crops')
        for index, vector in zip(accepted, vectors):
            row = rows[index]
            rows[index] = PersonAppearance(row.xyxy, row.confidence, normalize(vector))
        return ReIDResult(float(t), tuple(rows), self.encoder.model_id)
