"""CPU contracts for semantic hazards; no models, downloads or motors."""
from types import SimpleNamespace

import numpy as np
import pytest

from sentry.config import load
from sentry.perception.floor import FloorEvidence, SemanticFloorAnalyzer
from sentry.perception.obstacle import Detection, ObstacleDetector
from sentry.perception.world import merge_proposals
from tools.bench_obstacles import match_boxes, summarize_id
from tools.fetch_floor_model import fetch


def scene(unknown=False):
    image = np.full((80, 120, 3), 150, np.uint8)
    image[30:50, 45:65] = 30
    floor = np.full((80, 120), .95, np.float32)
    labels = np.full((80, 120), 3, np.int32)
    confidence = np.full((80, 120), .95, np.float32)
    # Semantic seed undersegments the foot by 3 px; image evidence refines it.
    floor[30:47, 45:65] = .05
    labels[30:47, 45:65] = 115
    if unknown:
        confidence[:] = .1
    return image, FloorEvidence(floor, labels, confidence)


def analyzer(evidence):
    return SemanticFloorAnalyzer(lambda image: evidence, load()['floor_segmentation'])


def test_semantic_seed_plus_edge_recovers_undersegmented_contact():
    image, evidence = scene()
    a = analyzer(evidence)
    evidence = a(image)
    result = a.contact(image, (45, 30, 65, 53), evidence, np.ones((80, 120), bool))
    assert result and abs(result.v - 50) <= 2 and result.method == 'semantic_floor_edge'


@pytest.mark.parametrize('kind', ['unknown', 'flat_image', 'no_floor', 'invalid_pixels'])
def test_no_contact_without_semantic_and_image_support(kind):
    image, evidence = scene(unknown=kind == 'unknown')
    valid = np.ones((80, 120), bool)
    if kind == 'flat_image':
        image[:] = 150
    elif kind == 'no_floor':
        evidence.floor_probability[:] = .1
    elif kind == 'invalid_pixels':
        valid[:] = False
    a = analyzer(evidence)
    assert a.contact(image, (45, 30, 65, 53), a(image), valid) is None


def test_non_coco_component_generates_proposal_and_deduplicates_yolo():
    image, evidence = scene()
    a = analyzer(evidence)
    evidence = a(image)
    valid = np.ones((80, 120), bool)
    proposals = a.proposals(image, evidence, valid, [])
    assert len(proposals) == 1 and proposals[0][1] is not None and proposals[0][2] == 115
    assert a.proposals(image, evidence, valid, [(44, 29, 66, 53)]) == []


@pytest.mark.parametrize('bad', ['nan', 'negative', 'wrong_shape', 'float_labels'])
def test_reject_invalid_model_output(bad):
    image, evidence = scene()
    if bad == 'nan':
        evidence.floor_probability[0, 0] = np.nan
    elif bad == 'negative':
        evidence.confidence[0, 0] = -.1
    elif bad == 'wrong_shape':
        evidence = FloorEvidence(evidence.floor_probability[:1], evidence.labels, evidence.confidence)
    else:
        evidence = FloorEvidence(evidence.floor_probability, evidence.labels.astype(float), evidence.confidence)
    with pytest.raises(ValueError):
        analyzer(evidence)(image)


def test_semantic_hazard_flows_through_detector_without_coco_filter():
    image = np.full((480, 640, 3), 150, np.uint8)
    image[280:300, 290:310] = 30
    floor = np.full((480, 640), .95, np.float32)
    labels = np.full((480, 640), 3, np.int32)
    confidence = np.full((480, 640), .95, np.float32)
    floor[280:297, 290:310] = .05
    labels[280:297, 290:310] = 115
    evidence = FloorEvidence(floor, labels, confidence)
    detector = ObstacleDetector.from_config(predictor=lambda im: (), floor_type='glossy',
                                            floor_predictor=lambda im: evidence)
    detector.geometry.undistort = lambda im: im
    detector.geometry.valid[:] = True
    result = detector(image, 1)
    assert len(result.obstacles) == 1
    assert result.obstacles[0].detection.class_id == -1
    assert result.obstacles[0].detection.semantic_label == 115
    assert result.obstacles[0].detection.source == 'semantic_nonfloor'
    assert result.obstacles[0].ground is not None
    # A semantic floor prediction must never imply a clear command or map FREE.
    unknown = detector(image, 2, floor_type='unknown')
    assert unknown.unresolved and not unknown.ground_points


def test_world_nms_merges_overlapping_crops_class_agnostically():
    a = Detection(-2, .8, (10, 10, 30, 30), source='open_vocabulary', label='bag')
    b = Detection(-2, .5, (11, 11, 31, 31), source='open_vocabulary', label='shoe')
    c = Detection(-2, .7, (50, 10, 60, 20), source='open_vocabulary')
    assert merge_proposals([b, c, a], .5) == (a, c)


def test_benchmark_matching_never_uses_tape_or_predicted_distance():
    labels = [dict(xyxy=(10, 10, 30, 30), obstacle_id=1), dict(xyxy=(50, 50, 60, 60), obstacle_id=2)]
    obs = [SimpleNamespace(detection=Detection(56, .8, (10, 10, 30, 30)))]
    assert match_boxes(labels, obs, .3) == {0: 0}
    missing = summarize_id([dict(matched=False, forward_m=None, rejection='missed', source=None)], 1)
    assert missing['distance_frames'] == 0 and missing['median_relative_error'] is None


def test_fetch_refuses_existing_hash_mismatch_without_network(tmp_path):
    artifact = tmp_path / 'model'
    artifact.write_bytes(b'bad')
    with pytest.raises(ValueError, match='hash mismatch'):
        fetch('https://example.invalid/unused', artifact, '0'*64)
