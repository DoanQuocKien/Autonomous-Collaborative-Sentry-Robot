import numpy as np
import pytest

from tools.org_seg import components, to_tensor, contact_error_stats, ratio_or_none, require_new_outputs
from tools.org_seg_judge import judge_set


def test_components_keep_only_blobs_above_the_minimum_area_with_their_boxes():
    m = np.zeros((100, 200), dtype=np.uint8)
    m[10:20, 30:60] = 1                    # 10 x 30 = 300 px
    m[70:72, 150:152] = 1                  # 4 px: too small
    comps = components(m, 30)
    assert comps == [(30, 10, 30, 10, 300)]


def test_to_tensor_is_channel_first_and_normalised():
    t = to_tensor(np.full((8, 16, 3), 124, dtype=np.uint8))
    assert tuple(t.shape) == (3, 8, 16) and abs(float(t.mean())) < 0.2


def test_the_judge_matches_components_within_the_gates_one_to_one_and_counts_the_false_ones():
    objs = [dict(id=1, label="a", tape=1.0, lateral=0.0), dict(id=2, label="b", tape=2.0, lateral=0.3)]
    frames = [0, 1, 2]
    comps = {0: [(1.1, 0.05), (2.05, 0.3), (3.5, 0.0)], 1: [(1.1, 0.05)], 2: []}      # frame 0: both found + one false; frame 1: only a; frame 2: nothing
    per, fp = judge_set(frames, objs, lambda f: comps[f])
    assert per[1] == [0.10000000000000009, 0.10000000000000009, None] and per[2][0] is not None and per[2][1:] == [None, None]
    assert fp == [1, 0, 0]
    near, _ = judge_set([0], [dict(id=1, label="a", tape=1.0, lateral=0.0)], lambda f: [(1.2, 0.0), (1.1, 0.0)])
    assert near[1] == [0.10000000000000009]                                               # the nearer component is the match, the other stays false


def test_missing_contact_error_is_unknown_and_serializes_without_fake_zero():
    import json
    result = contact_error_stats([])
    assert result == dict(median_abs=None, p90_abs=None, median_signed=None, n=0)
    assert 'null' in json.dumps(result, allow_nan=False)
    assert contact_error_stats([-2, 2])['median_abs'] == 2


def test_undefined_precision_is_not_perfect_or_nan():
    assert ratio_or_none(0, 0) is None
    assert ratio_or_none(0, 5) == 0


def test_existing_experiment_outputs_are_preserved(tmp_path):
    checkpoint = tmp_path/'segformer_org.pt'
    checkpoint.write_bytes(b'original baseline')
    with pytest.raises(FileExistsError):
        require_new_outputs(checkpoint, tmp_path/'train_log.json')
    assert checkpoint.read_bytes() == b'original baseline'
