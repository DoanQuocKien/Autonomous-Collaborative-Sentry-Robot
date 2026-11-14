import json

import cv2
import numpy as np
import pytest

from tools.prepare_d3_recording import prepare


def fixture(tmp_path, entries):
    data = tmp_path / 'data'
    recording = data / 'session'
    images = recording / 'jetbot'
    images.mkdir(parents=True)
    rows = []
    for i, (seq, t) in enumerate(entries):
        name = '%06d.jpg' % i
        assert cv2.imwrite(str(images/name), np.zeros((12, 16, 3), np.uint8))
        rows.append(dict(file=name, seq=seq, t_cap=t, w=16, h=12))
    meta = recording/'jetbot_meta.jsonl'
    meta.write_text('\n'.join(json.dumps(row) for row in rows)+'\n', encoding='utf-8')
    return data, recording, rows, meta


def test_real_capture_timestamps_and_all_frames_preserved_and_resets_split(tmp_path):
    data, recording, _, meta = fixture(tmp_path, [(40, 100.1), (43, 100.37), (0, 2.1), (1, 2.19)])
    before = meta.read_bytes()
    result = prepare(recording, recording/'prepared', data)
    assert result['frames'] == 4 and len(result['epochs']) == 2
    assert result['epochs'][0]['sequence_gaps'] == 2 and not result['t1_passed']
    assert result['epochs'][0]['duration_s'] == pytest.approx(.27)
    for i, expected in enumerate([[100.1, 100.37], [2.1, 2.19]]):
        folder = recording/'prepared'/('epoch-%03d' % i)
        manifest = json.loads((folder/'frames.json').read_text())
        truth = json.loads((folder/'truth-template.json').read_text())
        assert [f['t'] for f in manifest['frames']] == expected
        assert [f['t'] for f in truth['frames']] == expected
        assert all((folder/f['image']).exists() for f in manifest['frames'])
        assert not truth['reviewed'] and truth['annotation_template']
    assert meta.read_bytes() == before and (recording/'prepared/READY.json').exists()
    with pytest.raises(FileExistsError):
        prepare(recording, recording/'prepared', data)


@pytest.mark.parametrize('kind', ['timestamp_nan', 'duplicate_timestamp', 'duplicate_seq', 'traversal',
                                 'reused_image', 'dimensions', 'missing_image', 'boolean_timestamp'])
def test_invalid_capture_is_rejected_before_output_is_created(tmp_path, kind):
    data, recording, rows, meta = fixture(tmp_path, [(0, 10.), (1, 10.2)])
    if kind == 'timestamp_nan': rows[1]['t_cap'] = float('nan')
    if kind == 'duplicate_timestamp': rows[1]['t_cap'] = 10.
    if kind == 'duplicate_seq': rows[1]['seq'] = 0
    if kind == 'traversal': rows[1]['file'] = '../outside.jpg'
    if kind == 'reused_image': rows[1]['file'] = rows[0]['file']
    if kind == 'dimensions': rows[1]['w'] = 20
    if kind == 'missing_image': rows[1]['file'] = 'missing.jpg'
    if kind == 'boolean_timestamp': rows[1]['t_cap'] = True
    meta.write_text('\n'.join(json.dumps(row) for row in rows), encoding='utf-8')
    output = recording/'prepared'
    with pytest.raises(ValueError): prepare(recording, output, data)
    assert not output.exists()


def test_private_paths_and_no_raw_output(tmp_path):
    data, recording, _, _ = fixture(tmp_path, [(0, 0.)])
    with pytest.raises(ValueError, match='private manifests'):
        prepare(recording, tmp_path/'public', data)
    with pytest.raises(ValueError, match='raw images'):
        prepare(recording, recording/'jetbot/prepared', data)


def test_monotonic_sequence_can_still_have_clock_restart(tmp_path):
    data, recording, _, _ = fixture(tmp_path, [(30, 100.), (31, 2.)])
    assert len(prepare(recording, recording/'prepared', data)['epochs']) == 2


def test_clock_restart_with_one_frame_seq_zero_is_still_a_new_epoch(tmp_path):
    data, recording, _, _ = fixture(tmp_path, [(0, 100.), (0, 2.)])
    assert len(prepare(recording, recording/'prepared', data)['epochs']) == 2
