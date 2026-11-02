"""YOLO + Ultralytics ByteTrack, with OSNet-gated target lock and reacquisition.

One instance owns one stream. Only currently observed tracks are emitted. A
ByteTrack ID alone is never identity evidence; every lock decision needs a fresh
appearance vector from the same model/hash as the target. No motor/network I/O.
"""
from dataclasses import dataclass
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from sentry.config import DEFAULT_PATH, load
from sentry.perception.reid import OSNetEncoder, crop_person, normalize, validate_image


@dataclass(frozen=True)
class PersonTrack:
    track_id: int
    epoch: int
    xyxy: tuple
    confidence: float
    embedding: np.ndarray | None

    @property
    def key(self):
        return self.epoch, self.track_id


@dataclass(frozen=True)
class TrackingResult:
    t: float
    tracks: tuple[PersonTrack, ...]
    target: PersonTrack | None
    lock_state: str
    model_id: str
    epoch: int


class TargetLock:
    def __init__(self, model_id, settings):
        self.model_id, self.s = model_id, dict(settings)
        if not -1 <= self.s['lock_similarity'] <= 1 or not 0 <= self.s['lock_margin'] <= 2:
            raise ValueError('valid cosine threshold and margin required')
        if type(self.s['confirm_frames']) is not int or self.s['confirm_frames'] < 1:
            raise ValueError('positive integer lock confirmation required')
        if not math.isfinite(self.s['lost_timeout_s']) or self.s['lost_timeout_s'] <= 0:
            raise ValueError('positive finite lost timeout required')
        self.reference = None
        self.reset_tracking()

    def reset_tracking(self):
        self.key = self.pending = None
        self.count, self.last_seen = 0, None

    def set_target(self, embedding, model_id):
        if model_id != self.model_id:
            raise ValueError('target embedding model/hash differs from tracker')
        self.reference = normalize(embedding).copy()
        self.reset_tracking()

    def clear(self):
        self.reference = None
        self.reset_tracking()

    def update(self, tracks, t):
        if self.reference is None:
            return None, 'UNSET'
        scored = sorted(((float(np.clip(self.reference @ normalize(p.embedding), -1, 1)), p)
                         for p in tracks if p.embedding is not None), key=lambda pair: pair[0], reverse=True)
        good = bool(scored and scored[0][0] >= self.s['lock_similarity'] and
                    (len(scored) < 2 or (scored[0][0] - scored[1][0] >= self.s['lock_margin']
                                        and scored[0][0] - scored[1][0] > 1e-7)))
        if not good:
            self.key = None
            self.pending, self.count = None, 0
            state = 'LOST' if self.last_seen is not None and t - self.last_seen <= self.s['lost_timeout_s'] else 'SEARCHING'
            return None, state
        candidate = scored[0][1]
        if candidate.key != self.key:
            self.count = self.count + 1 if candidate.key == self.pending else 1
            self.pending = candidate.key
            if self.count < self.s['confirm_frames']:
                return None, 'CONFIRMING'
        self.key, self.pending, self.count, self.last_seen = candidate.key, None, 0, t
        return candidate, 'LOCKED'


class ByteTrackBackend:
    """Use upstream BYTETracker directly; do not invoke YOLO.track's implicit setup."""
    def __init__(self, settings):
        # Ensure the declared dependency is installed before Ultralytics imports
        # its optional assignment helper (which otherwise tries a pip install).
        import lap  # noqa: F401
        from ultralytics.trackers.byte_tracker import BYTETracker
        self.s = {k: settings[k] for k in ('track_high_thresh', 'track_low_thresh', 'new_track_thresh',
                                         'track_buffer', 'match_thresh', 'fuse_score')}
        self.tracker = BYTETracker(SimpleNamespace(**self.s))

    def reset(self):
        self.tracker.reset()

    def update(self, rows, shape):
        from ultralytics.engine.results import Boxes
        data = np.asarray(rows, np.float32).reshape(-1, 6)
        return self.tracker.update(Boxes(data, orig_shape=shape))


class PersonTracker:
    def __init__(self, detector, encoder, settings, reid_settings, backend=None):
        self.detector, self.encoder = detector, encoder
        self.s, self.rs = dict(settings), dict(reid_settings)
        if not 0 <= self.s['track_low_thresh'] <= self.s['track_high_thresh'] <= 1:
            raise ValueError('ordered low/high confidence thresholds required')
        if not self.s['track_high_thresh'] <= self.s['new_track_thresh'] <= 1:
            raise ValueError('new track threshold must be at least high threshold')
        if type(self.s['track_buffer']) is not int or self.s['track_buffer'] < 1:
            raise ValueError('positive track buffer required')
        if not 0 < self.s['match_thresh'] <= 1 or type(self.s['fuse_score']) is not bool:
            raise ValueError('valid ByteTrack match threshold and boolean fuse_score required')
        if not math.isfinite(self.s['max_frame_gap_s']) or self.s['max_frame_gap_s'] <= 0:
            raise ValueError('positive finite maximum frame gap required')
        self.lock = TargetLock(encoder.model_id, self.s)
        self.backend = backend if backend is not None else ByteTrackBackend(self.s)
        self.epoch, self.last_t = 0, None

    @classmethod
    def from_config(cls, config_path=DEFAULT_PATH, architecture=None):
        from sentry.perception.obstacle import YOLOPredictor
        cfg = load(config_path)
        rs, s = cfg['reid'], cfg['tracking']
        detector = YOLOPredictor(Path(config_path).resolve().parent / rs['person_weights'],
                                dict(cfg['obstacle'], class_ids=[0], confidence=s['track_low_thresh'],
                                     imgsz=rs['person_imgsz'], device=rs['person_device']))
        return cls(detector, OSNetEncoder.from_config(architecture, config_path), s, rs)

    def set_target(self, embedding, model_id):
        self.lock.set_target(embedding, model_id)

    def set_target_record(self, record):
        """Consume a real Phase2 IntruderRecord; simulation vectors cannot lock a person."""
        if record.metadata.get('appearance_simulated') is not False:
            raise ValueError('a real Phase2 appearance record is required')
        self.set_target(record.appearance_vector, record.metadata.get('appearance_model_id'))

    def clear_target(self):
        self.lock.clear()

    def reset(self):
        """New stream/sequence: clear motion history, retain the target reference."""
        self.backend.reset()
        self.lock.reset_tracking()
        self.epoch += 1
        self.last_t = None

    def __call__(self, frame_bgr, t):
        validate_image(frame_bgr)
        if not math.isfinite(t) or (self.last_t is not None and t <= self.last_t):
            raise ValueError('strictly increasing finite frame timestamps required; reset on replay/stream restart')
        if self.last_t is not None and t - self.last_t > self.s['max_frame_gap_s']:
            self.reset()
        self.last_t = t
        rows = []
        for d in self.detector(frame_bgr):
            if d.class_id != 0 or not math.isfinite(d.confidence) or not self.s['track_low_thresh'] <= d.confidence <= 1:
                continue
            try:
                crop = crop_person(frame_bgr, d.xyxy, self.rs['min_crop_height'], self.rs['min_crop_width'])
            except (ValueError, TypeError):
                continue
            if crop is None:
                continue
            x1, y1, x2, y2 = d.xyxy
            h, w = frame_bgr.shape[:2]
            rows.append([max(0., x1), max(0., y1), min(float(w), x2), min(float(h), y2), d.confidence, 0])
        observed = self.backend.update(rows, frame_bgr.shape[:2])
        tracks, crops, indices = [], [], []
        for row in observed:
            # Upstream returns [xyxy, id, score, class, original detection index].
            # Only observed rows are returned; lost Kalman predictions stay internal.
            if len(row) != 8 or not np.isfinite(row).all():
                raise ValueError('invalid ByteTrack output')
            crop = crop_person(frame_bgr, row[:4], self.rs['min_crop_height'], self.rs['min_crop_width'])
            tracks.append(PersonTrack(int(row[4]), self.epoch, tuple(map(float, row[:4])), float(row[5]), None))
            if crop is not None:
                crops.append(crop)
                indices.append(len(tracks) - 1)
        vectors = self.encoder.encode(crops) if crops else []
        if len(vectors) != len(crops):
            raise ValueError('encoder output count differs from observed tracks')
        for index, vector in zip(indices, vectors):
            p = tracks[index]
            tracks[index] = PersonTrack(p.track_id, p.epoch, p.xyxy, p.confidence, normalize(vector))
        target, state = self.lock.update(tracks, t)
        return TrackingResult(float(t), tuple(tracks), target, state, self.encoder.model_id, self.epoch)
