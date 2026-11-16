"""T0 contract only: fake model vectors, real queue/machine/runner/target lock."""
from types import SimpleNamespace

import numpy as np
import pytest

from sentry.app.phase2_pipeline import Phase2Pipeline
from sentry.app.phase3_runner import Phase3Runner
from sentry.app.state_machine import State, StateMachine
from sentry.app.target_queue import IntruderRecord, TargetQueue
from sentry.config import load
from sentry.perception.face import FaceVerifier
from sentry.perception.tracker import PersonTracker


def vector(index):
    value = np.zeros(512, np.float32)
    value[index] = 1
    return value


class Appearance:
    model_id = "unit-test-osnet:hash"

    def extract(self, crop):
        return vector(int(crop[0, 0, 0]))


def tracker():
    cfg = load()
    return PersonTracker(lambda image: [], SimpleNamespace(model_id=Appearance.model_id),
                         cfg["tracking"], cfg["reid"], backend=SimpleNamespace(reset=lambda: None))


def test_shared_phase2_fifo_handoff_installs_matching_real_contract_and_clears_on_standby():
    queue, sm, target_tracker = TargetQueue(), StateMachine(initial_state=State.STANDBY), tracker()
    pipeline = Phase2Pipeline(FaceVerifier({"known": [vector(0)]}), Appearance(), queue, sm)
    runner = Phase3Runner(sm=sm, queue=queue, target_tracker=target_tracker)
    first = pipeline.process_entry("A", [], vector(1), np.full((128, 64, 3), 2, np.uint8),
                                   timestamp=0., decision_timestamp=.5)
    assert first.record.timestamp == 0. and first.record.enqueued_at == .5
    assert runner.step(.5, (0, 0, 0)) == (0, 0)
    assert np.array_equal(target_tracker.lock.reference, vector(2))
    pipeline.process_entry("B", [], vector(1), np.full((128, 64, 3), 3, np.uint8),
                           timestamp=.6, decision_timestamp=1.)
    runner.step(1., (0, 0, 0), (3, 0))
    assert runner.queue.active.id == "A" and len(queue.all_history()) == 2
    runner.notify_target_exited(1.1)
    assert runner.active_target == queue.active.id == "B"
    assert np.array_equal(target_tracker.lock.reference, vector(3))
    assert runner._last_target_obs is None
    sm.handle_event("TARGET_FOUND", t=1.2)
    assert runner.step(1.2, (0, 0, 0), (4, 0))[0] > 0
    runner.notify_target_exited(1.3)
    assert runner.state == State.STANDBY and queue.active is None
    assert target_tracker.lock.reference is None
    assert [r.id for r in queue.all_completed()] == ["A", "B"]
    assert not queue.all_dropped()


@pytest.mark.parametrize("metadata", [
    dict(appearance_simulated=True, appearance_model_id=Appearance.model_id),
    dict(appearance_simulated=False, appearance_model_id="different-model:hash"),
])
def test_invalid_target_provenance_cannot_install_a_tracker_reference(metadata):
    queue, sm, target_tracker = TargetQueue(), StateMachine(initial_state=State.STANDBY), tracker()
    queue.push(IntruderRecord(id="A", appearance_vector=vector(2), metadata=metadata), t=0.)
    sm.handle_event("INTRUDER_QUEUED", {"id": "A"}, t=0.)
    with pytest.raises(ValueError):
        Phase3Runner(sm=sm, queue=queue, target_tracker=target_tracker)
    assert target_tracker.lock.reference is None


def test_active_machine_without_matching_record_rejects_tracker_handoff():
    sm, target_tracker = StateMachine(initial_state=State.STANDBY), tracker()
    sm.handle_event("INTRUDER_QUEUED", {"id": "missing"}, t=0.)
    with pytest.raises(ValueError, match="matching queue record"):
        Phase3Runner(sm=sm, queue=TargetQueue(), target_tracker=target_tracker)
    assert target_tracker.lock.reference is None
