"""Target FIFO queue for managing intruder records across Phases 2 and 3.

Owner: kouun-rokku (KR).
Spec §4.4: "A full-body crop is passed to OSNet to generate an appearance feature
vector (a_target). The intruder is pushed to a First-In, First-Out (FIFO) queue Q.
The JetBot is signaled to engage."
Spec §4.6: "If the path ends without a match, T2 is removed from Q (the event is
logged with timestamp and snapshot) and the JetBot continues with the next target in Q,
or returns to standby if Q is empty."
Implementation Plan §4.3 & §5 (Week 4):
"app/target_queue.py: FIFO of intruder records (id, face embedding, appearance vector,
sector, snapshot path, timestamps)."
"""
from collections import deque
from dataclasses import dataclass, field
import json
import math
from pathlib import Path
import threading
import time
from typing import Any, Deque, Dict, List, Optional, Sequence, Union

import numpy as np

from sentry.app.state_machine import Event
from sentry.perception.sector import DepartureSector, normalize_sector


def _normalize_vector_512(vec: Any, name: str) -> Optional[np.ndarray]:
    """Validate and normalize a 512-dimensional feature embedding."""
    if vec is None:
        return None
    arr = np.asarray(vec, dtype=np.float32).reshape(-1)
    if arr.size != 512:
        raise ValueError(f"{name} must have 512 dimensions, got {arr.size}")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} contains non-finite values (NaN/inf)")
    norm = float(np.linalg.norm(arr))
    if norm < 1e-12:
        raise ValueError(f"{name} norm is near-zero (< 1e-12)")
    return arr / norm


@dataclass
class IntruderRecord:
    """Structured record of an unauthorized individual detected at the entrance doorway."""
    id: str
    face_embedding: Optional[np.ndarray] = None
    appearance_vector: Optional[np.ndarray] = None
    sector: str = DepartureSector.UNKNOWN.value
    snapshot_path: Optional[str] = None
    timestamp: float = 0.0
    enqueued_at: float = 0.0
    dequeued_at: Optional[float] = None
    status: str = "queued"  # "queued", "active", "completed", "dropped"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id or not isinstance(self.id, str):
            raise ValueError(f"Intruder id must be a non-empty string, got {self.id!r}")
        self.sector = normalize_sector(self.sector)
        if self.face_embedding is not None:
            self.face_embedding = _normalize_vector_512(self.face_embedding, "face_embedding")
        if self.appearance_vector is not None:
            self.appearance_vector = _normalize_vector_512(self.appearance_vector, "appearance_vector")
        if not math.isfinite(self.timestamp):
            raise ValueError(f"timestamp must be finite, got {self.timestamp}")
        if not math.isfinite(self.enqueued_at):
            raise ValueError(f"enqueued_at must be finite, got {self.enqueued_at}")
        if self.dequeued_at is not None and not math.isfinite(self.dequeued_at):
            raise ValueError(f"dequeued_at must be finite, got {self.dequeued_at}")

    def to_dict(self) -> Dict[str, Any]:
        """Convert record to a JSON-serializable dictionary."""
        return {
            "id": self.id,
            "face_embedding": self.face_embedding.tolist() if self.face_embedding is not None else None,
            "appearance_vector": self.appearance_vector.tolist() if self.appearance_vector is not None else None,
            "sector": self.sector,
            "snapshot_path": str(self.snapshot_path) if self.snapshot_path is not None else None,
            "timestamp": float(self.timestamp),
            "enqueued_at": float(self.enqueued_at),
            "dequeued_at": float(self.dequeued_at) if self.dequeued_at is not None else None,
            "status": self.status,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "IntruderRecord":
        """Reconstruct IntruderRecord from a dictionary."""
        face_emb = np.asarray(d["face_embedding"], dtype=np.float32) if d.get("face_embedding") is not None else None
        app_vec = np.asarray(d["appearance_vector"], dtype=np.float32) if d.get("appearance_vector") is not None else None
        return cls(
            id=str(d["id"]),
            face_embedding=face_emb,
            appearance_vector=app_vec,
            sector=d.get("sector", DepartureSector.UNKNOWN.value),
            snapshot_path=d.get("snapshot_path"),
            timestamp=float(d.get("timestamp", 0.0)),
            enqueued_at=float(d.get("enqueued_at", 0.0)),
            dequeued_at=float(d["dequeued_at"]) if d.get("dequeued_at") is not None else None,
            status=str(d.get("status", "queued")),
            metadata=dict(d.get("metadata", {})),
        )


class TargetQueue:
    """Thread-safe First-In, First-Out (FIFO) queue for Phase 2/3 target management."""

    def __init__(self, initial_records: Sequence[Union[IntruderRecord, Dict[str, Any]]] = ()):
        self._lock = threading.RLock()
        self._queue: Deque[IntruderRecord] = deque()
        self._active_target: Optional[IntruderRecord] = None
        self._history: List[IntruderRecord] = []
        self._completed: List[IntruderRecord] = []
        self._dropped: List[IntruderRecord] = []

        for item in initial_records:
            self.push(item)

    def push(
        self,
        record: Union[IntruderRecord, Dict[str, Any]],
        t: Optional[float] = None,
    ) -> IntruderRecord:
        """Push a new intruder to the back of the FIFO queue."""
        with self._lock:
            now = float(time.time() if t is None else t)
            if isinstance(record, dict):
                rec_dict = dict(record)
                if "timestamp" not in rec_dict or rec_dict["timestamp"] == 0.0:
                    rec_dict["timestamp"] = now
                if "enqueued_at" not in rec_dict or rec_dict["enqueued_at"] == 0.0:
                    rec_dict["enqueued_at"] = now
                rec = IntruderRecord.from_dict(rec_dict)
            elif isinstance(record, IntruderRecord):
                rec = record
                if rec.enqueued_at == 0.0:
                    rec.enqueued_at = now
                if rec.timestamp == 0.0:
                    rec.timestamp = now
            else:
                raise TypeError(f"Expected IntruderRecord or dict, got {type(record)}")

            rec.status = "queued"
            self._queue.append(rec)
            self._history.append(rec)
            return rec

    def pop(self, t: Optional[float] = None) -> Optional[IntruderRecord]:
        """Pop the oldest intruder from the front of the FIFO queue and mark as active."""
        with self._lock:
            if not self._queue:
                return None
            now = float(time.time() if t is None else t)
            rec = self._queue.popleft()
            rec.dequeued_at = now
            rec.status = "active"
            self._active_target = rec
            return rec

    def peek(self) -> Optional[IntruderRecord]:
        """View the next intruder in the queue without removing it."""
        with self._lock:
            return self._queue[0] if self._queue else None

    @property
    def active_target(self) -> Optional[IntruderRecord]:
        """Currently active intruder being pursued or searched."""
        with self._lock:
            return self._active_target

    @property
    def active(self) -> Optional[IntruderRecord]:
        """Convenient alias for active_target."""
        return self.active_target

    def complete_active(
        self,
        reason: str = "intercept_complete",
        t: Optional[float] = None,
    ) -> Optional[IntruderRecord]:
        """Mark active target as successfully intercepted or handled."""
        with self._lock:
            if self._active_target is None:
                return None
            now = float(time.time() if t is None else t)
            target = self._active_target
            target.status = "completed"
            target.metadata["completion_reason"] = reason
            target.metadata["completed_at"] = now
            self._completed.append(target)
            self._active_target = None
            return target

    def drop_active(
        self,
        reason: str = "search_exhausted",
        t: Optional[float] = None,
    ) -> Optional[IntruderRecord]:
        """Drop active target (e.g. coverage search exhausted without re-acquisition, Spec §4.6)."""
        with self._lock:
            if self._active_target is None:
                return None
            now = float(time.time() if t is None else t)
            target = self._active_target
            target.status = "dropped"
            target.metadata["drop_reason"] = reason
            target.metadata["dropped_at"] = now
            self._dropped.append(target)
            self._active_target = None
            return target

    def get_by_id(self, target_id: str) -> Optional[IntruderRecord]:
        """Find intruder record by ID across active, queued, and historical targets."""
        with self._lock:
            if self._active_target and self._active_target.id == target_id:
                return self._active_target
            for r in self._queue:
                if r.id == target_id:
                    return r
            for r in self._history:
                if r.id == target_id:
                    return r
            return None

    def __len__(self) -> int:
        with self._lock:
            return len(self._queue)

    def __bool__(self) -> bool:
        return len(self) > 0

    def is_empty(self) -> bool:
        return len(self) == 0

    def clear(self) -> None:
        """Clear queued targets."""
        with self._lock:
            self._queue.clear()
            self._active_target = None

    def all_queued(self) -> List[IntruderRecord]:
        with self._lock:
            return list(self._queue)

    def all_completed(self) -> List[IntruderRecord]:
        with self._lock:
            return list(self._completed)

    def all_dropped(self) -> List[IntruderRecord]:
        with self._lock:
            return list(self._dropped)

    def all_history(self) -> List[IntruderRecord]:
        with self._lock:
            return list(self._history)

    def to_state_machine_event(
        self,
        record: Optional[IntruderRecord] = None,
        t: Optional[float] = None,
    ) -> Event:
        """Construct an INTRUDER_QUEUED event ready for the state machine."""
        with self._lock:
            target = record or (self._queue[-1] if self._queue else self._active_target)
            if target is None:
                raise ValueError("No record provided and queue is empty")
            ev_t = target.timestamp if t is None else float(t)
            return Event(
                name="INTRUDER_QUEUED",
                data=target.to_dict(),
                t=ev_t,
            )

    def save(self, path: Union[str, Path]) -> None:
        """Save queue state and history to a JSON file."""
        with self._lock:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "active_target": self._active_target.to_dict() if self._active_target else None,
                "queued": [r.to_dict() for r in self._queue],
                "completed": [r.to_dict() for r in self._completed],
                "dropped": [r.to_dict() for r in self._dropped],
                "history": [r.to_dict() for r in self._history],
            }
            with open(p, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)

    @classmethod
    def load(cls, path: Union[str, Path]) -> "TargetQueue":
        """Load queue state from a JSON file."""
        p = Path(path)
        with open(p, "r", encoding="utf-8") as f:
            payload = json.load(f)

        tq = cls()
        if payload.get("active_target"):
            tq._active_target = IntruderRecord.from_dict(payload["active_target"])
        for item in payload.get("queued", []):
            tq._queue.append(IntruderRecord.from_dict(item))
        for item in payload.get("completed", []):
            tq._completed.append(IntruderRecord.from_dict(item))
        for item in payload.get("dropped", []):
            tq._dropped.append(IntruderRecord.from_dict(item))
        for item in payload.get("history", []):
            tq._history.append(IntruderRecord.from_dict(item))
        return tq
