from dataclasses import replace
import hashlib
import json
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from sentry.app.phase2_live import DoorMonitor, DoorSettings
from sentry.app.phase2_pipeline import Phase2Pipeline
from sentry.app.state_machine import State
from sentry.perception.face import FaceVerifier, InsightFaceEncoder
from sentry.perception.tracker import PersonTrack
from sentry.net.frame import VideoFrame
from tools import monitor_door


def vector(index):
    value = np.zeros(512, np.float32)
    value[index] = 1
    return value


def face(index=1, box=(20, 10, 70, 70), confidence=.9, frontal=True):
    return dict(bbox=box, confidence=confidence, embedding=vector(index),
                kps=np.array([[30, 25], [60, 25], [45 if frontal else 65, 40], [35, 55], [55, 55]]))


class Tracker:
    def __init__(self):
        self.epoch = 0
        self.people = [PersonTrack(1, 0, (0, 0, 100, 160), .9, vector(2))]
        self.calls = 0

    def reset(self):
        self.epoch += 1

    def __call__(self, image, t):
        self.calls += 1
        tracks = tuple(replace(p, epoch=self.epoch) for p in self.people)
        return SimpleNamespace(tracks=tracks, epoch=self.epoch)


class Faces:
    def __init__(self):
        self.faces = [face()]

    def extract(self, image):
        return self.faces


class Appearance:
    model_id = "test-only-osnet-interface"

    def extract(self, crop):
        assert crop.dtype == np.uint8 and crop.shape[0] > 0
        return vector(2)


@pytest.fixture
def setup():
    pipeline = Phase2Pipeline(FaceVerifier({"known": [vector(0)]}), Appearance())
    rows = []
    monitor = DoorMonitor(Tracker(), Faces(), pipeline, DoorSettings(min_sharpness=0), rows.append)
    return monitor, rows, np.random.default_rng(2).integers(0, 255, (180, 240, 3), np.uint8)


def frames(monitor, image, times):
    for t in times:
        monitor.process(image, t, int(round(t * 1000)))


def finish(monitor, image, start=.6):
    monitor.face_encoder.faces = []
    frames(monitor, image, [start, start + .2, start + .4])


def test_unknown_entry_handoff_once_and_real_decision_time(setup):
    monitor, rows, image = setup
    monitor.decision_clock = lambda: 1.1
    frames(monitor, image, [0, .2, .4])
    finish(monitor, image)
    queued = rows[0]
    assert queued["decision"] == "queued" and queued["event"] == "INTRUDER_QUEUED"
    assert queued["latency_s"] == pytest.approx(1.1)
    record = monitor.pipeline.target_queue.active
    assert record.enqueued_at == 1.1 and record.timestamp == 0
    assert record.metadata["appearance_simulated"] is False
    assert record.metadata["crop_scope"] == "visible_body"
    assert monitor.pipeline.state_machine.t == 1.1
    monitor.face_encoder.faces = [face()]
    frames(monitor, image, [1.2, 1.4, 1.6, 1.8])
    assert len(monitor.pipeline.target_queue.all_history()) == 1
    assert len(rows) == 1
    assert monitor.evidence_counts["accepted_face_samples"] == 3


def test_known_requires_majority_same_identity_and_does_not_queue(setup):
    monitor, rows, image = setup
    monitor.face_encoder.faces = [face(0)]
    frames(monitor, image, [0, .2])
    monitor.face_encoder.faces = [face(1)]
    frames(monitor, image, [.4])
    finish(monitor, image)
    assert rows[0]["decision"] == "authorized" and rows[0]["authorized_id"] == "known"
    assert not monitor.pipeline.target_queue.all_history()
    assert monitor.pipeline.state_machine.state == State.STANDBY


def test_face_rule_rejects_votes_spread_across_different_people():
    verifier = FaceVerifier({"a": [vector(0)], "b": [vector(1)]})
    assert verifier.verify_many([vector(0), vector(1), vector(2)], 2)[2] is False
    with pytest.raises(ValueError, match="majority"):
        verifier.verify_many([vector(0), vector(1)], 1)


def test_no_face_then_later_frontal_face_can_start_entry(setup):
    monitor, rows, image = setup
    monitor.face_encoder.faces = []
    frames(monitor, image, [0, .2, .4, .6])
    assert not rows
    monitor.face_encoder.faces = [face()]
    frames(monitor, image, [.8, 1., 1.2])
    finish(monitor, image, 1.4)
    assert rows[0]["entry_start_t"] == .8 and rows[0]["decision"] == "queued"


def test_missing_face_and_short_burst_are_unresolved_on_departure(setup):
    monitor, rows, image = setup
    frames(monitor, image, [0])
    monitor.tracker.people = []
    frames(monitor, image, [.2, .4, .6])
    assert rows[0]["decision"] == "unresolved"
    assert not monitor.pipeline.target_queue.all_history()


def test_confirmed_but_insufficient_top_k_is_logged_unresolved(setup):
    monitor, rows, image = setup
    monitor.s = replace(monitor.s, start_frames=1)
    frames(monitor, image, [0])
    finish(monitor, image, .2)
    assert rows[0]["confirmed"] is True and rows[0]["decision"] == "unresolved"
    assert not monitor.pipeline.target_queue.all_history()


def test_consistently_seen_person_without_face_is_counted_for_audit(setup):
    monitor, rows, image = setup
    monitor.face_encoder.faces = []
    frames(monitor, image, [0, .2, .4])
    monitor.tracker.people = []
    frames(monitor, image, [.6, .8, 1.])
    assert rows[0]["person_confirmed"] is True and rows[0]["confirmed"] is False
    assert rows[0]["decision"] == "unresolved"
    assert not monitor.pipeline.target_queue.all_history()


def test_frontal_quality_selection_keeps_bounded_top_k(setup):
    monitor, rows, image = setup
    for i in range(8):
        monitor.face_encoder.faces = [face(confidence=.7 if i < 3 else .99, frontal=i < 3)]
        monitor.process(image, i * .2, i)
    assert len(next(iter(monitor.entries.values())).candidates) == 3
    finish(monitor, image, 1.6)
    assert [row["seq"] for row in rows[0]["selected_faces"]] == [0, 1, 2]


def test_two_people_are_segmented_independently_and_ambiguous_faces_abstain(setup):
    monitor, rows, image = setup
    monitor.tracker.people.append(PersonTrack(2, 0, (120, 0, 220, 160), .9, vector(3)))
    monitor.face_encoder.faces = [face(0), face(1, (140, 10, 190, 70))]
    frames(monitor, image, [0, .2, .4])
    finish(monitor, image)
    assert sorted(r["decision"] for r in rows) == ["authorized", "queued"]
    assert len(monitor.pipeline.target_queue.all_history()) == 1


def test_overlapping_people_do_not_share_one_face(setup):
    monitor, rows, image = setup
    monitor.tracker.people.append(PersonTrack(2, 0, (0, 0, 110, 160), .9, vector(3)))
    frames(monitor, image, [0, .2, .4])
    monitor.tracker.people = []
    frames(monitor, image, [.6, .8, 1.])
    assert all(r["decision"] == "unresolved" for r in rows)
    assert not monitor.pipeline.target_queue.all_history()


@pytest.mark.parametrize("change", ["gap", "reconnect", "sequence", "size"])
def test_stream_discontinuities_abort_incomplete_evidence(setup, change):
    monitor, rows, image = setup
    frames(monitor, image, [0, .2, .4])
    t, seq, reconnects = (2., 2000, 0) if change == "gap" else (.6, 600, 0)
    if change == "sequence":
        seq = 0
    if change == "reconnect":
        reconnects = 1
    if change == "size":
        image = cv2.resize(image, (260, 200))
    monitor.process(image, t, seq, reconnects)
    assert rows[0]["decision"] == "interrupted"
    assert not monitor.pipeline.target_queue.all_history()


def test_schedule_and_timeout_never_turn_missing_stream_into_unknown_person(setup):
    monitor, rows, image = setup
    frames(monitor, image, [0, .01, .1, .2, .3, .4])
    assert monitor.tracker.calls == 3
    monitor.tick(2)
    monitor.tick(3)
    assert len(rows) == 1 and rows[0]["decision"] == "interrupted"
    assert not monitor.pipeline.target_queue.all_history()


def test_invalid_decision_clock_fails_before_queue_mutation(setup):
    monitor, rows, image = setup
    monitor.decision_clock = lambda: float("nan")
    frames(monitor, image, [0, .2, .4])
    with pytest.raises(ValueError, match="timestamp"):
        finish(monitor, image)
    assert not monitor.pipeline.target_queue.all_history()


def test_latency_clock_is_sampled_after_appearance_inference(setup):
    monitor, rows, image = setup
    now = [1.0]
    monitor.decision_clock = lambda: now[0]
    def extract(crop):
        now[0] += .15
        return vector(2)
    monitor.pipeline.appearance_extractor.extract = extract
    frames(monitor, image, [0, .2, .4])
    finish(monitor, image)
    assert rows[0]["decision_t"] == pytest.approx(1.15)
    assert monitor.pipeline.target_queue.active.enqueued_at == pytest.approx(1.15)


def test_face_landmarks_are_available_and_optional():
    backend = SimpleNamespace(get=lambda image: [SimpleNamespace(
        bbox=[1, 1, 50, 60], det_score=.9, embedding=vector(0), kps=np.ones((5, 2)))])
    detected = InsightFaceEncoder(app=backend).extract(np.zeros((80, 80, 3), np.uint8))
    assert detected[0]["kps"].shape == (5, 2)


def test_fake_receiver_closes_on_success_and_inference_failure(setup):
    monitor, rows, image = setup
    class Source:
        reconnects = 0
        closed = False
        t = 0

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.closed = True

        def read(self, timeout):
            self.t += .2
            return VideoFrame(int(self.t * 100), self.t, self.t, self.t, image, b"")

    source = Source()
    monitor_door.run_receiver(source, monitor, .9, lambda f: True, clock=lambda: source.t)
    assert source.closed and rows[-1]["reason"] == "shutdown"
    source = Source()
    def broken(image):
        raise RuntimeError("inference failed")
    monitor.face_encoder.extract = broken
    monitor.last_t = None
    with pytest.raises(RuntimeError, match="inference failed"):
        monitor_door.run_receiver(source, monitor, .9, lambda f: True, clock=lambda: source.t)
    assert source.closed


def test_esp32_down_logs_source_status_and_produces_no_intruder(setup):
    monitor, rows, image = setup
    class Down:
        reconnects = 1
        closed = False
        t = 0

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.closed = True

        def read(self, timeout):
            self.t += .2
            return None
    source = Down()
    events = []
    monitor_door.run_receiver(source, monitor, 2., lambda f: True,
                              clock=lambda: source.t, source_event=events.append)
    assert source.closed and [e["state"] for e in events] == ["waiting", "unavailable"]
    assert not rows and not monitor.pipeline.target_queue.all_history()


def test_manifest_requires_private_hashes_unique_frames_and_real_time_provenance(tmp_path, monkeypatch):
    monkeypatch.setattr(monitor_door, "ROOT", tmp_path)
    folder = tmp_path / "data"
    folder.mkdir()
    image = folder / "f.jpg"
    cv2.imwrite(str(image), np.ones((80, 80, 3), np.uint8))
    manifest = dict(camera="esp32", timestamp_source="recorded receive clock",
                    frames=[dict(t=0., seq=0, image="f.jpg", image_sha256=hashlib.sha256(image.read_bytes()).hexdigest())])
    path = folder / "frames.json"
    path.write_text(json.dumps(manifest))
    assert monitor_door.read_manifest(path)["frames"][0]["t"] == 0
    manifest["frames"].append(dict(manifest["frames"][0], t=1., seq=1))
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="duplicate"):
        monitor_door.read_manifest(path)
    with pytest.raises(ValueError, match="under data"):
        monitor_door.private_path(tmp_path / "public.jpg")


@pytest.mark.parametrize("patch", [{"inference_hz": float("nan")}, {"minimum_votes": 1},
                                   {"max_gap_s": .1}, {"top_k": 0}, {"crop_scope": "unknown"}])
def test_bad_config_rejected_before_start(patch):
    with pytest.raises(ValueError):
        DoorSettings(**patch)


def test_scorer_retains_missing_unresolved_and_wrong_identity():
    from tools.evaluate_door_entries import evaluate
    truth = dict(camera="esp32", reviewed=True, entries=[
        dict(entry_id="a", enrolled=True, identity="known"),
        dict(entry_id="b", enrolled=False), dict(entry_id="c", enrolled=False),
        dict(entry_id="d", enrolled=True, identity="known")])
    rows = [dict(entry_id="a", decision="authorized", authorized_id="other"),
            dict(entry_id="b", decision="authorized"), dict(entry_id="c", decision="unresolved")]
    result = evaluate(rows, truth)
    assert result["wrong_identity_authorizations"] == 1
    assert result["tar"] == 0 and result["far"] == 1
    assert result["far_all_attempts"] == .5 and result["decision_coverage"] == .5
    assert result["missing_entries"] == 1 and result["unresolved_entries"] == 1
    result = evaluate([], truth)
    assert result["far"] is None and result["missing_entries"] == 4
    assert result["t1_passed"] is False
    with pytest.raises(ValueError, match="reviewed"):
        evaluate(rows, dict(truth, reviewed=False))
    complete = evaluate([dict(entry_id="a", decision="authorized", authorized_id="known"),
                         dict(entry_id="b", decision="queued", latency_s=1.2)],
                        dict(truth, entries=truth["entries"][:2]))
    assert complete["observed_entry_checks_pass"] is True


@pytest.mark.parametrize("no_usable_face", [False, True])
def test_cli_uses_validated_replay_and_preserves_existing_outputs(tmp_path, monkeypatch, setup, no_usable_face):
    monitor, rows, image = setup
    monkeypatch.setattr(monitor_door, "ROOT", tmp_path)
    folder = tmp_path / "data"
    folder.mkdir()
    manifest = dict(camera="esp32", timestamp_source="test receive timestamps", frames=[])
    for i in range(6):
        path = folder / ("f%d.jpg" % i)
        cv2.imwrite(str(path), image)
        manifest["frames"].append(dict(t=i * .2, seq=i, image=path.name,
            image_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    path = folder / "frames.json"
    path.write_text(json.dumps(manifest))
    config = tmp_path / "config.toml"
    config.write_text("[door_live]\nmin_sharpness=0\n")
    monitor.tracker.encoder = SimpleNamespace(model_id="test-only-osnet-interface")
    def build(config, whitelist, settings, emit, *, live):
        assert live is False
        monitor.emit = emit
        if no_usable_face:
            calls = [0]
            def no_face(image):
                calls[0] += 1
                if calls[0] == 3:
                    monitor.tracker.people = []
                return []
            monitor.face_encoder.extract = no_face
        return monitor
    monkeypatch.setattr(monitor_door, "build_monitor", build)
    args = ["--replay-manifest", str(path), "--out-dir", str(folder / "run"), "--config", str(config), "--diagnostics"]
    monitor_door.main(args)
    result = json.loads((folder / "run/summary.json").read_text())
    assert result["status"] == "completed"
    assert result["decisions"]["interrupted"] == int(not no_usable_face)
    assert result["decisions"]["unresolved"] == int(no_usable_face)
    assert result["confirmed_unresolved"] == int(no_usable_face)
    diagnostics = [json.loads(line) for line in (folder / "run/frames.jsonl").read_text().splitlines()]
    assert len(diagnostics) == 6 and all(row["timings_ms"]["process"] >= 0 for row in diagnostics)
    original = (folder / "run/summary.json").read_bytes()
    with pytest.raises(FileExistsError):
        monitor_door.main(args)
    assert (folder / "run/summary.json").read_bytes() == original


def test_deadline_phase_preserves_five_hz_on_twelve_hz_source(setup):
    monitor, rows, image = setup
    for i in range(120):
        monitor.process(image, i / 12, i)
    assert monitor.processed == 50
    assert monitor.skipped == 70


def test_late_frame_skips_old_slots_without_moving_future_deadlines(setup):
    monitor, rows, image = setup
    monitor.s = replace(monitor.s, max_gap_s=20)
    results = [monitor.process(image, t, i) for i, t in enumerate([0, .58, .6, .79, .8, 2.35, 2.36, 2.4])]
    assert results == [True, True, True, False, True, True, False, True]


@pytest.mark.parametrize("kind", ["confidence", "width", "border", "blur"])
def test_rejection_diagnostics_preserve_decision_policy(setup, kind):
    monitor, rows, image = setup
    if kind == "confidence":
        monitor.face_encoder.faces = [face(confidence=.5)]
        reason = "low_face_confidence"
    elif kind == "width":
        monitor.face_encoder.faces = [face(box=(20, 10, 30, 70))]
        reason = "small_face"
    elif kind == "border":
        monitor.face_encoder.faces = [face(box=(-5, 10, 70, 70))]
        reason = "truncated_face"
    else:
        monitor.s = replace(monitor.s, min_sharpness=25)
        image = np.zeros_like(image)
        reason = "blurred_face"
    frames(monitor, image, [0, .2, .4])
    monitor.tracker.people = []
    frames(monitor, image, [.6, .8, 1.])
    assert rows[0]["decision"] == "unresolved"
    assert rows[0]["sample_rejections"][reason] == 3
    # The three preceding rejected faces already exhausted the face-gap budget.
    assert rows[0]["sample_rejections"]["person_not_observed"] == 1
    assert rows[0]["end_trigger"] == "person_gap"
    assert all(np.isfinite(v) and v >= 0 for v in monitor.last_diagnostic["timings_ms"].values())


def test_confirmation_resets_do_not_erase_diagnostic_sample_totals(setup):
    monitor, rows, image = setup
    frames(monitor, image, [0])
    monitor.face_encoder.faces = [face(confidence=.5)]
    frames(monitor, image, [.2])
    monitor.face_encoder.faces = [face()]
    frames(monitor, image, [.4, .6, .8])
    finish(monitor, image, 1.)
    assert rows[0]["total_accepted_face_samples"] == 4
    assert rows[0]["face_samples"] == 3 and rows[0]["confirmation_resets"] == 1


def test_model_warmup_resets_tracker_and_keeps_entries_empty(setup):
    monitor, rows, image = setup
    body_calls = []
    face_calls = []
    monitor.tracker.encoder = SimpleNamespace(encode=lambda crops: body_calls.append(crops))
    monitor.face_encoder.app = SimpleNamespace(models={"recognition": SimpleNamespace(
        get_feat=lambda crop: face_calls.append(crop))})
    info = monitor_door.warmup_models(monitor, 2)
    assert len(body_calls) == len(face_calls) == 2
    assert monitor.tracker.epoch == 1
    assert info["excluded_from_entries"] and info["synthetic_input"]
    assert monitor.processed == 0 and not rows and not monitor.entries
    assert not monitor.pipeline.target_queue.all_history()
    disabled = monitor_door.warmup_models(monitor, 0)
    assert disabled["iterations"] == 0 and len(body_calls) == len(face_calls) == 2
