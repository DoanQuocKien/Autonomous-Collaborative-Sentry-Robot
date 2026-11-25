import math

import numpy as np
import pytest

from sentry.perception.pose import LungeDetector, LungeSettings


def box(area):
    return (10, 10, 10 + area / 100, 110)


@pytest.mark.parametrize('dt,hit', [(.025, True), (.10, True), (.10001, False), (.2, False)])
def test_strict_area_growth_is_timestamp_based(dt, hit):
    d = LungeDetector()
    assert not d.update(5., box(1000)).strike
    assert d.update(5. + dt, box(1401)).strike is hit


def test_threshold_equality_shrink_and_normal_growth_do_not_trigger():
    for area in (800, 1000, 1399, 1400):
        d = LungeDetector()
        d.update(0., box(1000))
        assert not d.update(.05, box(area)).strike


def test_irregular_samples_use_the_whole_window_and_slow_walking_stays_negative():
    d = LungeDetector()
    assert not d.update(0., box(1000)).strike
    assert not d.update(.03, box(1100)).strike
    assert d.update(.09, box(1410)).strike
    d.reset()
    assert not any(d.update(i*.05, box(1000*1.01**i)).strike for i in range(40))


@pytest.mark.parametrize('change', ['target', 'epoch', 'resize', 'missing', 'duplicate', 'rollback'])
def test_stream_discontinuities_do_not_compare_unrelated_boxes(change):
    d = LungeDetector()
    d.update(1., box(1000), frame_size=(640, 480))
    kwargs = dict(frame_size=(640, 480))
    t = 1.05
    if change == 'target':
        kwargs['track_id'] = 1
    elif change == 'epoch':
        kwargs['epoch'] = 1
    elif change == 'resize':
        kwargs['frame_size'] = (800, 600)
    elif change == 'missing':
        d.update(1.02, None, **kwargs)
    elif change == 'duplicate':
        assert d.update(1., box(1401), **kwargs).reason == 'duplicate_timestamp'
    else:
        t = .05
    assert not d.update(t, box(1401), **kwargs).strike


@pytest.mark.parametrize('bad', [None, (0, 0, 0, 5), (0, 0, math.inf, 5), (10, 10, 11, 11)])
def test_invalid_and_tiny_boxes_break_history(bad):
    d = LungeDetector()
    d.update(0., box(1000))
    assert not d.update(.025, bad).strike
    assert not d.update(.05, box(2000)).strike


def test_capture_clock_wins_over_receive_jitter_and_border_boxes_abstain():
    d = LungeDetector()
    assert not d(100., {'t_cap': 1., 'bbox': box(1000)})
    assert not d(100.05, {'t_cap': 1.2, 'bbox': box(2000)})
    assert not d.update(2., (0, 20, 200, 400), frame_size=(640, 480)).strike
    assert d.last_result.reason == 'edge_cut'


def test_ankle_rise_is_optional_confidence_gated_and_relative_to_hips():
    points = np.zeros((17, 2))
    points[11:13, 1], points[15:17, 1] = 40, 100
    conf = np.ones(17)
    d = LungeDetector(LungeSettings(ankle_rise_fraction=.15))
    d.update(0., box(1000), keypoints_xy=points, keypoints_conf=conf)
    shifted = points.copy(); shifted[:, 1] -= 20
    assert not d.update(.03, box(1000), keypoints_xy=shifted, keypoints_conf=conf).strike
    shifted[15:17, 1] -= 20
    assert d.update(.06, box(1000), keypoints_xy=shifted, keypoints_conf=conf).reason == 'ankle_rise'
    d.reset()
    d.update(1., box(1000), keypoints_xy=points, keypoints_conf=conf)
    conf[15:17] = .1
    assert not d.update(1.05, box(1000), keypoints_xy=shifted, keypoints_conf=conf).strike


@pytest.mark.parametrize('t', [math.nan, math.inf, True])
def test_invalid_timestamps_raise_and_clear_history(t):
    d = LungeDetector(); d.update(0., box(1000))
    with pytest.raises(ValueError):
        d.update(t, box(2000))
    assert not d.update(.05, box(2000)).strike


@pytest.mark.parametrize('kwargs', [dict(window_s=0), dict(area_growth=math.nan), dict(min_bbox_area_px2=-1), dict(ankle_rise_fraction=math.inf)])
def test_settings_are_finite_and_valid(kwargs):
    with pytest.raises(ValueError):
        LungeSettings(**kwargs)
