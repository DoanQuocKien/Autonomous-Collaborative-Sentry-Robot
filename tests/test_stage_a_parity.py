import ast
import json
from pathlib import Path

import numpy as np
import pytest

from jetson import stage_a_parity_run as nano
from sentry.perception.obstacle import Detection
from tools import stage_a_parity as stage


def raw():
    result = np.zeros((84, 2100), np.float32)
    result[:4, :3] = np.array([[160, 160, 160], [160, 160, 160], [50, 50, 50], [80, 80, 80]])
    result[4+56, 0] = .9
    result[4+56, 1] = .8  # same-class duplicate must be suppressed
    result[4+57, 2] = .7  # overlapping different class must survive
    return result


def test_decode_class_aware_nms_and_coordinate_mapping():
    frame = dict(letterbox=[.5, 0, 40], size=[640, 480])
    settings = dict(confidence=.25, class_ids=[56, 57], nms_iou=.7)
    detections = stage.decode(raw(), frame, settings)
    assert [d.class_id for d in detections] == [56, 57]
    assert detections[0].xyxy == (270, 160, 370, 320)
    settings['class_ids'] = [57]
    assert [d.class_id for d in stage.decode(raw(), frame, settings)] == [57]


def test_decode_agrees_with_ultralytics_nms_for_fixed_canvas():
    import torch
    from ultralytics.utils.nms import non_max_suppression
    settings = dict(confidence=.25, class_ids=[56, 57], nms_iou=.7)
    expected = non_max_suppression(torch.from_numpy(raw()[None]), conf_thres=.25, iou_thres=.7,
                                   classes=[56, 57], nc=80)[0].numpy()
    actual = stage.decode(raw(), dict(letterbox=[1, 0, 0], size=[320, 320]), settings)
    np.testing.assert_allclose([d.xyxy for d in actual], expected[:, :4])
    assert [d.class_id for d in actual] == list(expected[:, 5])


def test_matching_requires_class_and_counts_extra_detections():
    chair = Detection(56, .9, (0, 0, 10, 10))
    couch = Detection(57, .9, chair.xyxy)
    assert stage.box_stats([chair], [couch])['matched'] == 0
    result = stage.box_stats([chair], [chair, couch])
    assert result == dict(reference=1, candidate=2, matched=1, same_count=False)


@pytest.mark.parametrize('change', ['shape', 'nan', 'zero'])
def test_invalid_or_uninformative_raw_output_cannot_pass(change):
    ref = raw()[None]
    candidate = ref.copy()
    if change == 'shape':
        candidate = candidate[:, :, :-1]
    elif change == 'nan':
        candidate[0, 4, 4] = np.nan
    else:
        candidate.fill(0)
    if change == 'zero':
        assert stage.raw_stats(ref, candidate)['frames_below_0999'] == 1
    else:
        with pytest.raises(ValueError):
            stage.raw_stats(ref, candidate)


def errors(values):
    return {str(i): dict(median_relative_error=v) for i, v in enumerate(values)}


def test_distance_no_estimates_or_missing_ids_never_silently_pass():
    none = errors([None, None])
    result = stage.distance_stats(none, none)
    assert result['passed'] is None
    assert result['diagnostic_within_2_percentage_points'] is None
    assert result['candidate_missing_ids'] == ['0', '1']
    ref, candidate = errors([.1]*20), errors([.11]*19+[None])
    result = stage.distance_stats(ref, candidate)
    assert result['diagnostic_within_2_percentage_points'] is True
    assert result['passed'] is None and result['paired_distance_ids'] == 19


def test_distance_uses_percentage_points_id_first_and_reports_regression():
    good = stage.distance_stats(errors([.10]*20), errors([.115]*20))
    assert good['passed'] is True
    assert good['candidate_minus_reference_percentage_points'] == pytest.approx(1.5)
    bad = stage.distance_stats(errors([.10]*20), errors([.14]*20))
    assert bad['passed'] is False
    with pytest.raises(ValueError, match='ID sets'):
        stage.distance_stats(errors([.1]), errors([]))


@pytest.fixture
def bundle(tmp_path):
    folder = tmp_path/'bundle'
    folder.mkdir()
    np.savez_compressed(folder/'inputs.npz', canvases=np.zeros((2, 320, 320, 3), np.uint8))
    onnx, engine = tmp_path/'model.onnx', tmp_path/'model.engine'
    onnx.write_bytes(b'synthetic ONNX build source for T0')
    engine.write_bytes(b'synthetic engine for T0')
    manifest = dict(schema=nano.SCHEMA, frames=[dict(id='frame-1'), dict(id='frame-2')],
                    inputs_sha256=nano.sha256(folder/'inputs.npz'), onnx_sha256=nano.sha256(onnx))
    stage.write_json(folder/'manifest.json', manifest)
    return folder, onnx, engine


class FakeEngine:
    input_shape = (1, 3, 320, 320)

    def __init__(self, path):
        pass

    def infer(self, x):
        assert x.shape == self.input_shape and x.dtype == np.float32
        return [raw()[None]]


def test_nano_runner_exports_all_frames_and_marks_test_double(bundle, tmp_path):
    folder, onnx, engine = bundle
    output = tmp_path/'result'
    result = nano.run(folder, onnx, engine, output, engine_factory=FakeEngine)
    assert result['frame_ids'] == ['frame-1', 'frame-2']
    assert result['backend'] == 'test-double' and result['motor_commands_sent'] == 0
    with np.load(output/'raw.npz') as data:
        assert data['raw'].shape == (2, 84, 2100)
    with pytest.raises(FileExistsError):
        nano.run(folder, onnx, engine, output, engine_factory=FakeEngine)
    with pytest.raises(ValueError, match='provenance'):
        stage.compare(folder, output, '.', stage.DEFAULT_PATH, 'pose.json', tmp_path/'public.json')


@pytest.mark.parametrize('change', ['input_hash', 'duplicate_id', 'onnx_hash'])
def test_nano_rejects_mismatched_bundle_before_engine_runs(bundle, tmp_path, change):
    folder, onnx, engine = bundle
    manifest_path = folder/'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    if change == 'input_hash':
        manifest['inputs_sha256'] = '0'*64
    elif change == 'duplicate_id':
        manifest['frames'][1] = manifest['frames'][0]
    else:
        onnx.write_bytes(b'wrong export')
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        nano.run(folder, onnx, engine, tmp_path/'output', engine_factory=lambda path: pytest.fail('engine instantiated'))


@pytest.mark.parametrize('bad', ['shape', 'nan'])
def test_nano_does_not_publish_partial_success(bundle, tmp_path, bad):
    class Broken(FakeEngine):
        def infer(self, x):
            values = raw()[None]
            if bad == 'shape':
                values = values[:, :, :1]
            else:
                values[0, 1, 1] = np.nan
            return [values]
    with pytest.raises(ValueError, match='finite raw'):
        nano.run(*bundle, tmp_path/'bad', engine_factory=Broken)
    assert not (tmp_path/'bad'/'result.json').exists()


@pytest.mark.parametrize('change', ['order', 'raw_hash', 'count', 'backend'])
def test_laptop_rejects_wrong_candidate_provenance(bundle, tmp_path, change):
    folder, onnx, engine = bundle
    output = tmp_path/'candidate'
    info = nano.run(folder, onnx, engine, output, engine_factory=FakeEngine)
    info.update(backend='tensorrt', runtime={'tensorrt': 'synthetic T0'})
    if change == 'order':
        info['frame_ids'].reverse()
    elif change == 'raw_hash':
        info['raw_sha256'] = '0'*64
    elif change == 'count':
        info['frame_ids'].pop()
    else:
        info['backend'] = 'onnxruntime'
    (output/'result.json').write_text(json.dumps(info))
    with pytest.raises(ValueError, match='provenance'):
        stage.compare(folder, output, '.', stage.DEFAULT_PATH, 'pose.json', tmp_path/'report.json')


def test_nano_runner_remains_python36():
    ast.parse(Path(nano.__file__).read_text(encoding='utf-8'), feature_version=(3, 6))


def test_successful_comparison_keeps_missing_distances_unassessable(bundle, tmp_path):
    """Synthetic raw outputs exercise the full import/decoder/contact/report path."""
    import cv2
    folder, onnx, engine = bundle
    output = tmp_path/'candidate'
    manifest = json.loads((folder/'manifest.json').read_text())
    pose = Path('assets/d1/obstacles_2026-10-15/camera_pose_classroom_1015.json')
    config = stage.DEFAULT_PATH
    camera = config.parent/'calib/camera.json'
    manifest.update(labels={'21': dict(obstacle_id='21', clip='chairs_a',
        xyxy=[270, 160, 370, 320], tape_forward_m=1.0)},
        source_sha256={str(config): nano.sha256(config)},
        adapter_sha256=dict(config=nano.sha256(config), pose=nano.sha256(pose), camera=nano.sha256(camera)),
        postprocess=dict(confidence=.25, class_ids=[56, 57], nms_iou=.7))
    for index, frame in enumerate(manifest['frames']):
        path = tmp_path/('frame-%d.jpg' % index)
        cv2.imwrite(str(path), np.zeros((480, 640, 3), np.uint8))
        frame.update(id=path.name, clip='chairs_a', letterbox=[.5, 0, 40], size=[640, 480], sha256=nano.sha256(path))
    np.savez_compressed(folder/'reference.npz', raw=np.stack([raw(), raw()]))
    manifest['reference_sha256'] = nano.sha256(folder/'reference.npz')
    stage.write_json(folder/'laptop.json', {'21': dict(median_relative_error=None)})
    manifest['laptop_sha256'] = nano.sha256(folder/'laptop.json')
    (folder/'manifest.json').write_text(json.dumps(manifest))
    info = nano.run(folder, onnx, engine, output, engine_factory=FakeEngine)
    # Unit-test metadata only. The actual runner always labels FakeEngine as a
    # test double; no report from this fixture is retained as runtime evidence.
    info.update(backend='tensorrt', runtime={'tensorrt': 'synthetic T0'})
    (output/'result.json').write_text(json.dumps(info))
    report = stage.compare(folder, output, tmp_path, config, pose, tmp_path/'report.json')
    assert report['raw']['min_cosine'] == pytest.approx(1)
    assert report['boxes']['matched_fraction'] == 1
    assert report['conversion_parity_passed'] is False  # only two synthetic frames
    assert report['distance']['passed'] is None
    assert report['distance_against_laptop_640']['passed'] is None
    assert report['stage_a_g2_accepted'] is False
    # A changed local camera session must not silently replace the prepared one.
    with pytest.raises(ValueError, match='adapter'):
        stage.compare(folder, output, tmp_path, config, config.parent/'calib/camera_pose_nowedge.json', tmp_path/'other.json')
