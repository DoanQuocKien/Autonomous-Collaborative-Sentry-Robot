"""End-to-end integration tests for Phase 2 replay on D2 dataset (Week 4, kouun-rokku)."""
import numpy as np
import pytest

from sentry.app.phase2_pipeline import MockAppearanceExtractor, Phase2Pipeline
from sentry.app.state_machine import State, StateMachine
from sentry.app.target_queue import TargetQueue
from sentry.perception.face import FaceVerifier, normalize_embedding
from sentry.perception.sector import DepartureSector
from tools.replay_phase2 import generate_d2_replay_entries, run_phase2_replay


def test_phase2_pipeline_authorized_entrant_stays_in_standby():
    # Setup enrolled member
    ref_emb = normalize_embedding(np.random.randn(512))
    whitelist = {"member_alice": [ref_emb]}
    verifier = FaceVerifier(whitelist=whitelist, threshold=0.45)

    queue = TargetQueue()
    sm = StateMachine(initial_state=State.STANDBY, t0=0.0)
    pipeline = Phase2Pipeline(face_verifier=verifier, target_queue=queue, state_machine=sm)

    # Alice walks in
    query_emb = normalize_embedding(ref_emb + np.random.randn(512) * 0.01)
    observations = [
        (0.0, (270.0, 100.0, 370.0, 300.0)),
        (1.0, (270.0, 150.0, 370.0, 350.0)),
        (2.0, (270.0, 200.0, 370.0, 400.0)),
    ]

    res = pipeline.process_entry("entry_alice_01", observations, face_embedding=query_emb, timestamp=0.0)

    assert not res.is_intruder
    assert res.authorized_id == "member_alice"
    assert res.similarity_score > 0.70
    assert len(queue) == 0
    assert sm.state == State.STANDBY


def test_phase2_pipeline_intruder_engages_pursuit_and_queues():
    ref_emb = normalize_embedding(np.random.randn(512))
    whitelist = {"member_alice": [ref_emb]}
    verifier = FaceVerifier(whitelist=whitelist, threshold=0.45)

    queue = TargetQueue()
    sm = StateMachine(initial_state=State.STANDBY, t0=0.0)
    pipeline = Phase2Pipeline(face_verifier=verifier, target_queue=queue, state_machine=sm)

    # Stranger walks in drifting to the right
    stranger_emb = normalize_embedding(np.random.randn(512))
    obs1 = [
        (10.0, (270.0, 100.0, 370.0, 300.0)),
        (11.0, (350.0, 100.0, 450.0, 300.0)),
        (12.0, (430.0, 100.0, 530.0, 300.0)),
    ]

    res1 = pipeline.process_entry("intruder_01", obs1, face_embedding=stranger_emb, timestamp=10.0)

    assert res1.is_intruder
    assert res1.authorized_id is None
    assert res1.sector == DepartureSector.RIGHT.value
    assert res1.record is not None
    assert res1.record.appearance_vector.shape == (512,)

    # State machine should have transitioned from STANDBY -> PURSUE
    assert sm.state == State.PURSUE
    assert sm.active_target == "intruder_01"
    assert res1.command_emitted.play == "intruder_detected"
    assert "engage_target" in res1.command_emitted.actions

    # A second stranger walks in while robot is pursuing intruder_01
    stranger2_emb = normalize_embedding(np.random.randn(512))
    obs2 = [
        (15.0, (270.0, 100.0, 370.0, 300.0)),
        (16.0, (200.0, 100.0, 300.0, 300.0)),
        (17.0, (130.0, 100.0, 230.0, 300.0)),
    ]

    res2 = pipeline.process_entry("intruder_02", obs2, face_embedding=stranger2_emb, timestamp=15.0)

    assert res2.is_intruder
    assert res2.sector == DepartureSector.LEFT.value
    # TargetQueue should now have 2 records in total (1 active, 1 queued)
    assert len(queue) == 2
    # Robot continues active pursuit of intruder_01, intruder_02 queued
    assert sm.state == State.PURSUE
    assert sm.active_target == "intruder_01"
    assert "queue_target" in res2.command_emitted.actions


def test_phase2_pipeline_target_handoff_and_next_target_acquisition():
    # Demonstrates Spec §4.6 multi-intruder handoff:
    # T1 exits -> SEARCH -> search completes or exhausted -> Q pops T2 -> engage T2
    tq = TargetQueue()
    sm = StateMachine(initial_state=State.STANDBY, t0=0.0)
    pipeline = Phase2Pipeline(target_queue=tq, state_machine=sm)

    # 1. Enqueue two intruders
    obs_t1 = [(1.0, (300, 100, 400, 300)), (2.0, (300, 150, 400, 350)), (3.0, (300, 200, 400, 400))]
    obs_t2 = [(5.0, (300, 100, 400, 300)), (6.0, (200, 100, 300, 300)), (7.0, (100, 100, 200, 300))]

    pipeline.process_entry("T1", obs_t1, timestamp=1.0)
    pipeline.process_entry("T2", obs_t2, timestamp=5.0)

    assert sm.active_target == "T1"
    assert sm.state == State.PURSUE

    # 2. T1 exits through door -> transitions to SEARCH for next queued target T2
    sm.handle_event("TARGET_EXITED", t=10.0)
    assert sm.state == State.SEARCH
    assert sm.search_step == "PLAN"
    assert sm.active_target == "T2"

    # 3. Follow coverage path & scan -> T2 re-identified (Spec §4.6 step 4)
    sm.handle_event("PLAN_READY", t=11.0)
    sm.handle_event("VIEWPOINT_REACHED", t=15.0)
    sm.handle_event("TARGET_FOUND", data={"target_id": "T2"}, t=16.0)

    # State machine engages pursuit of T2!
    assert sm.state == State.PURSUE
    assert sm.active_target == "T2"

    # 4. If T2 exits and search exhausts without finding T2 (Spec §4.6 step 5)
    sm.handle_event("TARGET_EXITED", t=25.0)
    assert sm.state == State.STANDBY  # queue is now empty, returns to standby


def test_phase2_pipeline_search_exhausted_drops_unfound_target():
    tq = TargetQueue()
    sm = StateMachine(initial_state=State.STANDBY, t0=0.0)
    pipeline = Phase2Pipeline(target_queue=tq, state_machine=sm)

    obs = [(1.0, (300, 100, 400, 300)), (2.0, (300, 150, 400, 350))]
    pipeline.process_entry("T1", obs, timestamp=1.0)
    pipeline.process_entry("T2", obs, timestamp=5.0)

    # T1 exits -> SEARCH for T2
    sm.handle_event("TARGET_EXITED", t=10.0)
    assert sm.state == State.SEARCH
    assert sm.active_target == "T2"

    # Search finishes without match -> SEARCH_EXHAUSTED
    sm.handle_event("SEARCH_EXHAUSTED", t=30.0)
    # T2 dropped, queue empty -> returns to STANDBY
    assert sm.state == State.STANDBY
    assert sm.active_target is None
    assert len(sm.dropped_targets) == 1
    assert sm.dropped_targets[0][1] == "T2"


def test_phase2_replay_d2_full_acceptance():
    whitelist, entries = generate_d2_replay_entries()
    results = run_phase2_replay(entries, whitelist, cosine_threshold=0.45)

    assert results["status"] == "PASS"
    assert results["total_entries"] == 30
    assert results["authorized_count"] == 20
    assert results["intruder_count"] == 10
    assert results["false_accepts"] == 0
    assert results["false_rejects"] == 0
    assert results["sector_evaluation"]["accuracy"] >= 0.90
    assert results["sector_evaluation"]["passed"] is True
