"""Phase 2 Monitoring & Access Control Replay Pipeline (Spec §4.4, §4.6, Implementation Plan §5).

Owner: kouun-rokku (KR).
Connects the Phase 2 monitoring pipeline end to end on replayed ESP32-CAM doorway data (D2):
  1. Ingests timestamped entrance frames / crops from the ESP32-CAM stream.
  2. Runs Face Verification against the enrolled whitelist (InsightFace / FaceVerifier, cosine threshold 0.45).
  3. If authorized: logs authorized entry, stays in STANDBY.
  4. If unauthorized (intruder):
     - Extracts OSNet re-ID appearance vector (a_target) from full-body crop.
     - Logs horizontal bounding-box drift over 2 s as departure sector (Left / Center / Right).
     - Saves snapshot image.
     - Pushes IntruderRecord to FIFO TargetQueue.
     - Dispatches INTRUDER_QUEUED event to StateMachine -> transitions STANDBY to PURSUE,
       or queues FIFO if robot is already deployed in Phase 3.
"""
from dataclasses import dataclass, field
import logging
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

from sentry.app.state_machine import Command, State, StateMachine, TransitionResult
from sentry.app.target_queue import IntruderRecord, TargetQueue
from sentry.perception.face import FaceVerifier
from sentry.perception.sector import DepartureSector, SectorConfig, classify_sector

logger = logging.getLogger("sentry.phase2")


class BaseAppearanceExtractor:
    """Abstract interface for extracting 512D person appearance vectors."""

    def extract(self, person_crop_bgr: np.ndarray) -> np.ndarray:
        raise NotImplementedError


class OSNetAppearanceExtractor(BaseAppearanceExtractor):
    """Phase 2 adapter to HNHL's validated, local-only OSNet encoder."""

    def __init__(
        self,
        weights_path: Optional[Union[str, Path]] = None,
        arch: str = "osnet_ain_x1_0",
        device: str = "cpu",
        config_path=None,
    ):
        from sentry.config import DEFAULT_PATH, load
        from sentry.perception.reid import OSNetEncoder
        config_path = DEFAULT_PATH if config_path is None else config_path
        self.encoder = (OSNetEncoder(arch, weights_path, load(config_path)['reid'], device)
                        if weights_path is not None else
                        OSNetEncoder.from_config(arch, config_path, device))
        self.model_id = self.encoder.model_id

    def extract(self, person_crop_bgr: np.ndarray) -> np.ndarray:
        return self.encoder.encode([person_crop_bgr])[0]


class MockAppearanceExtractor(BaseAppearanceExtractor):
    """Deterministic CPU appearance extractor for testing, offline replays, and CI."""

    def __init__(self, seed: int = 532):
        self.rng = np.random.RandomState(seed)
        self.model_id = "simulation:mock-appearance-v1"

    def extract(self, person_crop_bgr: np.ndarray) -> np.ndarray:
        if person_crop_bgr is None or not isinstance(person_crop_bgr, np.ndarray) or person_crop_bgr.size == 0:
            raise ValueError("person_crop_bgr must be a non-empty BGR numpy array")

        # Generate a deterministic 512D unit vector based on image hash/statistics
        h, w = person_crop_bgr.shape[:2]
        mean_colors = person_crop_bgr.mean(axis=(0, 1)) if person_crop_bgr.size > 0 else np.array([128, 128, 128])
        seed_val = int(abs(mean_colors.sum() * 1000 + h * 31 + w)) % (2**31 - 1)
        local_rng = np.random.RandomState(seed_val)
        raw = local_rng.randn(512).astype(np.float32)
        return raw / float(np.linalg.norm(raw))


@dataclass
class Phase2EventResult:
    """Outcome of processing a single entrance entry."""
    entry_id: str
    timestamp: float
    is_intruder: bool
    authorized_id: Optional[str] = None
    similarity_score: float = -1.0
    record: Optional[IntruderRecord] = None
    sector: str = DepartureSector.UNKNOWN.value
    sector_drift: float = 0.0
    state_machine_transition: Optional[TransitionResult] = None
    command_emitted: Optional[Command] = None


@dataclass
class Phase2PipelineSummary:
    """Summary of Phase 2 replay on an entire dataset."""
    total_entries: int = 0
    authorized_count: int = 0
    intruder_count: int = 0
    sector_counts: Dict[str, int] = field(default_factory=lambda: {"left": 0, "center": 0, "right": 0, "unknown": 0})
    event_results: List[Phase2EventResult] = field(default_factory=list)
    state_machine_history: List[TransitionResult] = field(default_factory=list)
    final_queue_length: int = 0
    active_target_id: Optional[str] = None


class Phase2Pipeline:
    """End-to-end Phase 2 Monitoring and Intruder Handoff Pipeline."""

    def __init__(
        self,
        face_verifier: Optional[FaceVerifier] = None,
        appearance_extractor: Optional[BaseAppearanceExtractor] = None,
        target_queue: Optional[TargetQueue] = None,
        state_machine: Optional[StateMachine] = None,
        sector_config: Optional[SectorConfig] = None,
        snapshot_dir: Optional[Union[str, Path]] = None,
        frame_width: float = 640.0,
    ):
        self.face_verifier = FaceVerifier() if face_verifier is None else face_verifier
        # Simulations must opt into MockAppearanceExtractor explicitly. A missing
        # real model/crop must never silently create a synthetic pursuit target.
        self.appearance_extractor = appearance_extractor
        self.target_queue = TargetQueue() if target_queue is None else target_queue
        self.state_machine = StateMachine(initial_state=State.STANDBY) if state_machine is None else state_machine
        self.sector_config = SectorConfig.from_toml() if sector_config is None else sector_config
        self.frame_width = float(frame_width)
        self.snapshot_dir = Path(snapshot_dir) if snapshot_dir else None
        if self.snapshot_dir:
            self.snapshot_dir.mkdir(parents=True, exist_ok=True)

    def process_entry(
        self,
        entry_id: str,
        observations: Sequence[Tuple[float, Tuple[float, float, float, float]]],
        face_embedding: Optional[np.ndarray] = None,
        person_crop_bgr: Optional[np.ndarray] = None,
        timestamp: Optional[float] = None,
    ) -> Phase2EventResult:
        """Process one entrance sequence.

        Args:
            entry_id: identifier for the entry instance (e.g. "entry_001")
            observations: list of (t, bbox) observations over time (x1, y1, x2, y2)
            face_embedding: 512D face embedding from InsightFace (or None)
            person_crop_bgr: full body crop BGR image for OSNet appearance extraction
            timestamp: time of first detection crossing doorway threshold
        """
        t0 = float(observations[0][0]) if observations else float(time.time() if timestamp is None else timestamp)

        # 1. Face verification
        authorized_id = None
        best_score = -1.0
        authorized = False

        if face_embedding is not None:
            authorized_id, best_score, authorized = self.face_verifier.verify(face_embedding)
            best_score = float(best_score) if best_score is not None else -1.0

        # 2. Sector tracking from bounding box horizontal drift over 2 s
        sector_name, drift = classify_sector(
            observations,
            config=self.sector_config,
            frame_width=self.frame_width,
        )

        if authorized:
            logger.info(
                "Authorized entrant %r (member: %s, cosine: %.4f >= %.2f)",
                entry_id,
                authorized_id,
                best_score,
                self.face_verifier.threshold,
            )
            return Phase2EventResult(
                entry_id=entry_id,
                timestamp=t0,
                is_intruder=False,
                authorized_id=authorized_id,
                similarity_score=best_score,
                sector=sector_name,
                sector_drift=drift,
            )

        # 3. Unauthorized -> Intruder detected!
        logger.warning(
            "Intruder detected %r (max cosine: %.4f < %.2f)",
            entry_id,
            best_score,
            self.face_verifier.threshold,
        )

        # 4. Appearance feature extraction (OSNet re-ID vector)
        if self.appearance_extractor is None:
            raise RuntimeError("provide OSNetAppearanceExtractor, or an explicit mock for simulation")
        if person_crop_bgr is None and isinstance(self.appearance_extractor, MockAppearanceExtractor):
            dummy_crop = np.zeros((256, 128, 3), dtype=np.uint8)
            app_vector = self.appearance_extractor.extract(dummy_crop)
        else:
            from sentry.perception.reid import validate_image
            validate_image(person_crop_bgr)
            app_vector = self.appearance_extractor.extract(person_crop_bgr)
        from sentry.perception.reid import normalize
        app_vector = normalize(app_vector)

        # 5. Save snapshot if requested
        snapshot_path = None
        if self.snapshot_dir and person_crop_bgr is not None and person_crop_bgr.size > 0:
            try:
                import cv2
                snap_file = self.snapshot_dir / f"{entry_id}_snapshot.jpg"
                cv2.imwrite(str(snap_file), person_crop_bgr)
                snapshot_path = str(snap_file)
            except Exception as e:
                logger.warning("Failed saving intruder snapshot: %s", e)

        # 6. Create IntruderRecord and push to FIFO queue
        record = IntruderRecord(
            id=entry_id,
            face_embedding=face_embedding,
            appearance_vector=app_vector,
            sector=sector_name,
            snapshot_path=snapshot_path,
            timestamp=t0,
            enqueued_at=t0,
            metadata={
                "similarity_score": best_score,
                "sector_drift": drift,
                "appearance_model_id": getattr(self.appearance_extractor, "model_id", "unidentified-extractor"),
                "appearance_simulated": isinstance(self.appearance_extractor, MockAppearanceExtractor),
            },
        )
        self.target_queue.push(record, t=t0)

        # 7. Notify StateMachine
        sm_transition = self.state_machine.handle_event(
            "INTRUDER_QUEUED",
            data=record.to_dict(),
            t=t0,
        )

        # If StateMachine transitioned from STANDBY to PURSUE, promote intruder to active in TargetQueue
        if sm_transition.prev_state == State.STANDBY and sm_transition.state == State.PURSUE:
            self.target_queue.pop(t=t0)

        return Phase2EventResult(
            entry_id=entry_id,
            timestamp=t0,
            is_intruder=True,
            authorized_id=None,
            similarity_score=best_score,
            record=record,
            sector=sector_name,
            sector_drift=drift,
            state_machine_transition=sm_transition,
            command_emitted=sm_transition.command,
        )

    def replay_dataset(
        self,
        entries: Sequence[Dict[str, Any]],
    ) -> Phase2PipelineSummary:
        """Run Phase 2 replay across a dataset of entry sequences."""
        summary = Phase2PipelineSummary()

        for entry in entries:
            res = self.process_entry(
                entry_id=entry["id"],
                observations=entry["observations"],
                face_embedding=entry.get("face_embedding"),
                person_crop_bgr=entry.get("person_crop_bgr"),
                timestamp=entry.get("timestamp"),
            )
            summary.total_entries += 1
            summary.event_results.append(res)
            sec = res.sector if res.sector in summary.sector_counts else "unknown"
            summary.sector_counts[sec] += 1

            if res.is_intruder:
                summary.intruder_count += 1
            else:
                summary.authorized_count += 1

            if res.state_machine_transition:
                summary.state_machine_history.append(res.state_machine_transition)

        summary.final_queue_length = len(self.target_queue)
        summary.active_target_id = self.state_machine.active_target
        return summary
