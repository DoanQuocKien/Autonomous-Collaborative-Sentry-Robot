"""Unit tests for TargetQueue and IntruderRecord (Week 4, kouun-rokku)."""
import json
import threading
import numpy as np
import pytest

from sentry.app.state_machine import Event
from sentry.app.target_queue import IntruderRecord, TargetQueue
from sentry.perception.sector import DepartureSector


def test_intruder_record_valid():
    face_emb = np.random.randn(512).astype(np.float32)
    face_emb /= np.linalg.norm(face_emb)
    app_vec = np.random.randn(512).astype(np.float32)
    app_vec /= np.linalg.norm(app_vec)

    rec = IntruderRecord(
        id="intruder_01",
        face_embedding=face_emb,
        appearance_vector=app_vec,
        sector="L",
        snapshot_path="/tmp/snap.jpg",
        timestamp=10.5,
        enqueued_at=10.5,
        metadata={"score": 0.32},
    )

    assert rec.id == "intruder_01"
    assert rec.sector == DepartureSector.LEFT.value
    assert rec.face_embedding.shape == (512,)
    assert rec.appearance_vector.shape == (512,)
    assert abs(np.linalg.norm(rec.face_embedding) - 1.0) < 1e-5
    assert abs(np.linalg.norm(rec.appearance_vector) - 1.0) < 1e-5
    assert rec.status == "queued"


def test_intruder_record_validation_errors():
    # Empty id
    with pytest.raises(ValueError, match="non-empty string"):
        IntruderRecord(id="")

    # Invalid embedding dimension
    with pytest.raises(ValueError, match="512 dimensions"):
        IntruderRecord(id="i1", face_embedding=np.zeros(128))

    # Non-finite values
    bad_vec = np.ones(512, dtype=np.float32)
    bad_vec[5] = np.nan
    with pytest.raises(ValueError, match="non-finite"):
        IntruderRecord(id="i1", appearance_vector=bad_vec)

    # Near-zero norm
    with pytest.raises(ValueError, match="near-zero"):
        IntruderRecord(id="i1", face_embedding=np.zeros(512))


def test_intruder_record_dict_roundtrip():
    face_emb = np.random.randn(512).astype(np.float32)
    face_emb /= np.linalg.norm(face_emb)

    rec = IntruderRecord(
        id="target_99",
        face_embedding=face_emb,
        sector="right",
        timestamp=123.456,
        enqueued_at=123.456,
        metadata={"note": "test"},
    )
    d = rec.to_dict()
    assert d["id"] == "target_99"
    assert d["sector"] == "right"
    assert len(d["face_embedding"]) == 512

    reconstructed = IntruderRecord.from_dict(d)
    assert reconstructed.id == rec.id
    assert reconstructed.sector == rec.sector
    assert np.allclose(reconstructed.face_embedding, rec.face_embedding)
    assert reconstructed.metadata == {"note": "test"}


def test_target_queue_fifo_push_pop():
    tq = TargetQueue()
    assert len(tq) == 0
    assert tq.is_empty()

    r1 = tq.push({"id": "target_1", "sector": "L"}, t=1.0)
    r2 = tq.push({"id": "target_2", "sector": "C"}, t=2.0)
    r3 = tq.push({"id": "target_3", "sector": "R"}, t=3.0)

    assert len(tq) == 3
    assert not tq.is_empty()
    assert tq.peek().id == "target_1"

    # FIFO order: target_1, then target_2, then target_3
    p1 = tq.pop(t=4.0)
    assert p1.id == "target_1"
    assert p1.status == "active"
    assert p1.dequeued_at == 4.0
    assert tq.active.id == "target_1"
    assert len(tq) == 2

    p2 = tq.pop(t=5.0)
    assert p2.id == "target_2"
    assert tq.active.id == "target_2"
    assert len(tq) == 1

    p3 = tq.pop(t=6.0)
    assert p3.id == "target_3"
    assert tq.active.id == "target_3"
    assert len(tq) == 0
    assert tq.pop() is None


def test_target_queue_active_completion_and_drop():
    tq = TargetQueue()
    tq.push({"id": "target_a", "sector": "left"}, t=10.0)
    tq.push({"id": "target_b", "sector": "right"}, t=11.0)

    # Pop active
    active = tq.pop(t=12.0)
    assert active.id == "target_a"

    # Complete active
    completed = tq.complete_active(reason="intercept_complete", t=15.0)
    assert completed.id == "target_a"
    assert completed.status == "completed"
    assert completed.metadata["completion_reason"] == "intercept_complete"
    assert tq.active is None
    assert len(tq.all_completed()) == 1

    # Next target
    tq.pop(t=16.0)
    assert tq.active.id == "target_b"

    # Drop active (e.g. search exhausted, Spec §4.6)
    dropped = tq.drop_active(reason="search_exhausted", t=25.0)
    assert dropped.id == "target_b"
    assert dropped.status == "dropped"
    assert dropped.metadata["drop_reason"] == "search_exhausted"
    assert tq.active is None
    assert len(tq.all_dropped()) == 1


def test_target_queue_get_by_id():
    tq = TargetQueue()
    tq.push({"id": "t1", "sector": "L"}, t=1.0)
    tq.push({"id": "t2", "sector": "C"}, t=2.0)
    tq.pop(t=3.0)  # t1 active
    tq.complete_active(t=4.0)  # t1 completed

    assert tq.get_by_id("t1").status == "completed"
    assert tq.get_by_id("t2").status == "queued"
    assert tq.get_by_id("nonexistent") is None


def test_target_queue_to_state_machine_event():
    tq = TargetQueue()
    r = tq.push({"id": "intruder_alpha", "sector": "R"}, t=42.0)
    ev = tq.to_state_machine_event()

    assert isinstance(ev, Event)
    assert ev.name == "INTRUDER_QUEUED"
    assert ev.t == 42.0
    assert ev.data["id"] == "intruder_alpha"
    assert ev.data["sector"] == "right"


def test_target_queue_save_load(tmp_path):
    tq = TargetQueue()
    tq.push({"id": "t1", "sector": "L"}, t=10.0)
    tq.push({"id": "t2", "sector": "R"}, t=11.0)
    tq.pop(t=12.0)  # t1 is active
    tq.push({"id": "t3", "sector": "C"}, t=13.0)

    save_file = tmp_path / "queue.json"
    tq.save(save_file)
    assert save_file.exists()

    loaded = TargetQueue.load(save_file)
    assert loaded.active.id == "t1"
    assert len(loaded) == 2
    assert loaded.pop().id == "t2"
    assert loaded.pop().id == "t3"


def test_target_queue_thread_safety():
    tq = TargetQueue()
    num_threads = 8
    items_per_thread = 50

    def pusher(tid):
        for i in range(items_per_thread):
            tq.push({"id": f"th_{tid}_{i}"})

    threads = [threading.Thread(target=pusher, args=(t,)) for t in range(num_threads)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()

    assert len(tq) == num_threads * items_per_thread

    popped = []

    def popper():
        while True:
            item = tq.pop()
            if item is None:
                break
            popped.append(item.id)

    pop_threads = [threading.Thread(target=popper) for _ in range(4)]
    for th in pop_threads:
        th.start()
    for th in pop_threads:
        th.join()

    assert len(popped) == num_threads * items_per_thread
    assert len(tq) == 0
