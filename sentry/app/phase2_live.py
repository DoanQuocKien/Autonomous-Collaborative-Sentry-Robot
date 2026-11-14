"""Incremental door entries using shared face, tracking and Phase 2 contracts."""
from dataclasses import dataclass, field
import math
from types import SimpleNamespace
import uuid

import numpy as np

from sentry.perception.face import face_sharpness, face_yaw_ratio, normalize_embedding
from sentry.perception.reid import associate_person, crop_person, validate_image
from sentry.app.phase2_pipeline import MockAppearanceExtractor


@dataclass(frozen=True)
class DoorSettings:
    inference_hz: float = 5.0
    start_frames: int = 3
    end_frames: int = 3
    top_k: int = 3
    minimum_votes: int = 2
    min_face_width: float = 40.0
    min_face_confidence: float = 0.6
    min_sharpness: float = 25.0
    frontal_yaw: float = 0.15
    face_overlap: float = 0.8
    max_gap_s: float = 1.0
    max_entry_s: float = 15.0
    max_people: int = 16
    crop_scope: str = "visible_body"

    def __post_init__(self):
        positive = (self.inference_hz, self.min_face_width, self.max_gap_s, self.max_entry_s)
        if any(not math.isfinite(v) or v <= 0 for v in positive):
            raise ValueError("positive finite rate, width and time limits required")
        integers = (self.start_frames, self.end_frames, self.top_k, self.minimum_votes, self.max_people)
        if any(type(v) is not int or v < 1 for v in integers):
            raise ValueError("positive integer counts required")
        if not self.top_k / 2 < self.minimum_votes <= self.top_k:
            raise ValueError("minimum_votes must be a strict majority of top_k")
        if (not 0 < self.face_overlap <= 1 or not 0 <= self.min_face_confidence <= 1
                or not math.isfinite(self.min_sharpness) or self.min_sharpness < 0
                or not math.isfinite(self.frontal_yaw) or self.frontal_yaw < 0):
            raise ValueError("valid face quality limits required")
        if self.max_gap_s <= 1 / self.inference_hz:
            raise ValueError("max_gap_s must exceed the scheduled interval")
        if self.crop_scope not in ("visible_body", "full_body"):
            raise ValueError("declare visible_body or full_body crop scope")


@dataclass
class Entry:
    key: tuple
    entry_id: str
    first_seen: float
    start: float | None = None
    last_face: float | None = None
    observations: list = field(default_factory=list)
    candidates: list = field(default_factory=list)
    hits: int = 0
    consecutive: int = 0
    misses: int = 0
    absent: int = 0
    confirmed: bool = False
    completed: bool = False


class DoorMonitor:
    """Single processing-thread owner; share pipeline queue/state machine with KR.

    Only scheduled, genuinely new frames count toward N/M. Interrupted entries
    are logged and discarded. Completed tracks stay suppressed until departure.
    """

    def __init__(self, tracker, face_encoder, pipeline, settings, emit, *, decision_clock=None):
        if isinstance(pipeline.appearance_extractor, MockAppearanceExtractor):
            raise ValueError("live monitoring requires a real appearance extractor")
        self.tracker, self.face_encoder, self.pipeline = tracker, face_encoder, pipeline
        self.s, self.emit, self.decision_clock = settings, emit, decision_clock
        self.session_id = uuid.uuid4().hex
        self.entries = {}
        self.last_t = self.last_seq = self.shape = self.reconnects = None
        self.next_due = -math.inf
        self.epoch = self.counter = self.processed = self.skipped = 0
        self.last_tracks = ()
        self.last_faces = ()
        self.evidence_counts = dict(person_observations=0, detected_faces=0, associated_faces=0,
                                    accepted_face_samples=0)

    def interrupt(self, t, reason):
        """Abort incomplete entries, without classifying a stream outage as an exit."""
        for entry in self.entries.values():
            if not entry.completed:
                self._log(entry, t, "interrupted", reason)
        self.entries.clear()
        self.tracker.reset()
        self.last_tracks = ()
        self.last_faces = ()
        self.epoch += 1
        self.next_due = -math.inf

    def tick(self, t):
        if not math.isfinite(t):
            raise ValueError("finite tick timestamp required")
        if self.last_t is not None and t - self.last_t > self.s.max_gap_s and self.entries:
            self.interrupt(t, "stream_timeout")

    def process(self, image, t, seq, reconnects=0):
        validate_image(image)
        if not math.isfinite(t) or type(seq) is not int or seq < 0:
            raise ValueError("finite timestamp and nonnegative integer sequence required")
        if self.last_t is not None and t <= self.last_t:
            raise ValueError("frame timestamps must increase")
        reset = self.last_seq is not None and seq <= self.last_seq
        gap = self.last_t is not None and t - self.last_t > self.s.max_gap_s
        changed = self.shape is not None and self.shape != image.shape
        reconnected = self.reconnects is not None and reconnects != self.reconnects
        if reset or gap or changed or reconnected:
            self.interrupt(t, "stream_discontinuity")
        self.last_t, self.last_seq, self.shape, self.reconnects = t, seq, image.shape, reconnects
        if t + 1e-9 < self.next_due:
            self.skipped += 1
            return False
        self.next_due = t + 1 / self.s.inference_hz
        tracked = self.tracker(image, t)
        tracks = tracked.tracks
        if len(tracks) > self.s.max_people:
            self.interrupt(t, "too_many_people")
            return False
        # A tracker may independently reset on its own gap contract.
        if self.entries and any(key[0] != tracked.epoch for key in self.entries):
            self.interrupt(t, "tracker_epoch_changed")
            return False
        self.last_tracks = tracks
        faces = self.face_encoder.extract(image)
        self.last_faces = tuple(faces)
        self.evidence_counts["person_observations"] += len(tracks)
        self.evidence_counts["detected_faces"] += len(faces)
        detections = [SimpleNamespace(class_id=0, confidence=p.confidence, xyxy=p.xyxy) for p in tracks]
        associated = {p.key: [] for p in tracks}
        for face in faces:
            box, _ = associate_person(face["bbox"], detections, 0, self.s.face_overlap)
            if box is not None:
                self.evidence_counts["associated_faces"] += 1
                for person in tracks:
                    if person.xyxy == box:
                        associated[person.key].append(face)
        present = {p.key for p in tracks}
        for person in tracks:
            entry = self.entries.get(person.key)
            if entry is None:
                self.counter += 1
                entry = Entry(person.key, "door_%s_%04d_%06d" % (self.session_id, self.epoch, self.counter), t)
                self.entries[person.key] = entry
            entry.absent = 0
            if entry.completed:
                continue
            options = associated[person.key]
            candidate = self._candidate(image, person, options[0], t, seq) if len(options) == 1 else None
            if candidate is not None:
                self.evidence_counts["accepted_face_samples"] += 1
                if not entry.confirmed and entry.consecutive == 0:
                    entry.start = None
                    entry.hits = 0
                    entry.candidates.clear()
                    entry.observations.clear()
                if entry.start is None:
                    entry.start = t
                entry.last_face = t
                entry.hits += 1
                entry.consecutive += 1
                entry.misses = 0
                entry.confirmed |= entry.consecutive >= self.s.start_frames
                entry.candidates.append(candidate)
                entry.candidates.sort(key=lambda c: c["rank"], reverse=True)
                del entry.candidates[self.s.top_k:]
            else:
                entry.consecutive = 0
                entry.misses += 1
            if entry.start is not None and t <= entry.start + self.pipeline.sector_config.window_s:
                entry.observations.append((t, person.xyxy))
            if ((entry.confirmed and entry.misses >= self.s.end_frames)
                    or t - entry.first_seen >= self.s.max_entry_s):
                self._finish(entry, t)
        for key, entry in list(self.entries.items()):
            if key in present:
                continue
            entry.absent += 1
            entry.misses += 1
            entry.consecutive = 0
            if entry.misses >= self.s.end_frames and not entry.completed:
                self._finish(entry, t)
            if entry.absent >= self.s.end_frames:
                del self.entries[key]
        self.processed += 1
        return True

    def _candidate(self, image, person, face, t, seq):
        box = face["bbox"]
        x1, y1, x2, y2 = box
        h, w = image.shape[:2]
        width = x2 - x1
        confidence = float(face["confidence"])
        if (not math.isfinite(confidence) or not self.s.min_face_confidence <= confidence <= 1
                or width < self.s.min_face_width or x1 < 0 or y1 < 0 or x2 > w or y2 > h):
            return None
        sharp = face_sharpness(image, box)
        if sharp < self.s.min_sharpness:
            return None
        crop = crop_person(image, person.xyxy)
        if crop is None:
            return None
        yaw = face_yaw_ratio(face.get("kps"))
        frontal = yaw is not None and abs(yaw) <= self.s.frontal_yaw
        return dict(t=t, seq=seq, embedding=normalize_embedding(face["embedding"]), crop=crop,
                    rank=(frontal, confidence * width * sharp), confidence=confidence,
                    width_px=width, sharpness=sharp, yaw_ratio=yaw)

    def _finish(self, entry, t):
        entry.completed = True
        if not entry.confirmed or len(entry.candidates) < self.s.top_k:
            self._log(entry, t, "unresolved", "insufficient_face_evidence")
            entry.candidates.clear()
            return
        candidates = entry.candidates
        self.pipeline.frame_width = float(self.shape[1])
        result = self.pipeline.process_entry(
            entry.entry_id, entry.observations,
            person_crop_bgr=candidates[0]["crop"], timestamp=entry.start,
            face_embeddings=[c["embedding"] for c in candidates],
            minimum_face_votes=self.s.minimum_votes, decision_timestamp=t,
            decision_clock=self.decision_clock,
            entry_metadata=dict(crop_scope=self.s.crop_scope, source="esp32_door",
                                entry_start=entry.start, face_samples=entry.hits),
        )
        decision = "queued" if result.is_intruder else "authorized"
        self._log(entry, result.decision_timestamp, decision, "entry_complete", result)
        entry.candidates.clear()

    def _log(self, entry, t, decision, reason, result=None):
        scores = [self.pipeline.face_verifier.verify(c["embedding"])[1] for c in entry.candidates]
        selected = [{k: c[k] for k in ("t", "seq", "confidence", "width_px", "sharpness", "yaw_ratio")}
                    for c in entry.candidates]
        self.emit(dict(entry_id=entry.entry_id, track_key=list(entry.key),
                       first_seen_t=entry.first_seen, entry_start_t=entry.start,
                       last_face_t=entry.last_face, decision_t=t, decision=decision, reason=reason,
                       latency_s=None if entry.start is None else t - entry.start,
                       face_samples=entry.hits, selected_faces=selected, scores=scores,
                       threshold=self.pipeline.face_verifier.threshold,
                       threshold_calibrated=False, crop_scope=self.s.crop_scope,
                       authorized_id=None if result is None else result.authorized_id,
                       sector="unknown" if result is None else result.sector,
                       snapshot_path=None if result is None or result.record is None else result.record.snapshot_path,
                       queue_length=len(self.pipeline.target_queue),
                       active_target=self.pipeline.state_machine.active_target,
                       event="INTRUDER_QUEUED" if decision == "queued" else None))
