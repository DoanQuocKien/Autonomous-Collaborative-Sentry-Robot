from copy import deepcopy

import pytest

from tools.evaluate_tracking import evaluate


def data():
    truth = dict(kind='D3_TRACKING', reviewed=True, camera='jetbot', frames=[])
    pred = dict(frames=[])
    for t in (0., 30., 60.):
        boxes = [(0, 0, 20, 50), (50, 0, 70, 50)]
        truth['frames'].append(dict(t=t, objects=[dict(id=str(i), xyxy=b) for i, b in enumerate(boxes)]))
        pred['frames'].append(dict(t=t, tracks=[dict(track_id=i + 1, epoch=0, xyxy=b) for i, b in enumerate(boxes)]))
    return truth, pred


def test_perfect_tracks_and_one_switch_per_minute():
    truth, pred = data()
    assert evaluate(truth, pred)['t1_passed']
    pred['frames'][-1]['tracks'][0]['track_id'] = 3
    r = evaluate(truth, pred)
    assert r['id_switches'] == 1 and r['id_switches_per_minute'] == 1 and r['switch_limit_met']
    pred['frames'][-1]['tracks'][1]['track_id'] = 4
    assert not evaluate(truth, pred)['switch_limit_met']


def test_empty_predictions_do_not_pass_and_missing_frames_cannot_hide_errors():
    truth, pred = data()
    for f in pred['frames']:
        f['tracks'] = []
    r = evaluate(truth, pred)
    assert r['id_switches'] == 0 and r['missed_instances'] == 6 and not r['t1_passed']
    pred['frames'].pop()
    with pytest.raises(ValueError, match='frames'):
        evaluate(truth, pred)


def test_switch_across_occlusion_and_recycled_id_in_new_epoch():
    truth, pred = data()
    truth['frames'][1]['objects'] = []
    pred['frames'][1]['tracks'] = []
    pred['frames'][-1]['tracks'][0]['epoch'] = 1
    assert evaluate(truth, pred)['id_switches'] == 1
    pred['frames'][0]['t'] = .1
    with pytest.raises(ValueError, match='timestamps'):
        evaluate(truth, pred)


def test_synthetic_or_short_or_unreviewed_inputs_do_not_create_t1_pass():
    truth, pred = data()
    for patch in [dict(kind='SYNTHETIC'), dict(reviewed=False), dict(camera='esp32')]:
        copy = deepcopy(truth)
        copy.update(patch)
        assert not evaluate(copy, pred)['t1_passed']
    truth['frames'][-1]['t'] = pred['frames'][-1]['t'] = 40.
    assert not evaluate(truth, pred)['protocol_complete']


def test_duplicate_or_invalid_boxes_are_rejected_and_false_positives_count():
    truth, pred = data()
    pred['frames'][0]['tracks'].append(dict(track_id=3, epoch=0, xyxy=(100, 0, 120, 50)))
    assert evaluate(truth, pred)['false_positive_instances'] == 1
    pred['frames'][0]['tracks'][0]['xyxy'] = (0, 0, float('nan'), 50)
    with pytest.raises(ValueError, match='xyxy'):
        evaluate(truth, pred)
