import pytest

from tools.build_midterm_hnhl_nov11 import judge_summary,temporal_scopes


def test_good_conditional_error_does_not_hide_missed_objects():
    rows={str(i):dict(label='chair',tape_m=1,found_fraction=1 if i==0 else 0,
        median_error_m=.01 if i==0 else None) for i in range(3)}
    doc=dict(sets={'set':dict(objects=rows)},summary=dict(objects=3,
        found_in_half_the_frames=1,median_abs_error_m_of_found=.01,
        gates=dict(forward_m=.5,left_m=.4)))
    result=judge_summary(doc)
    assert result['median_abs_error_m_of_found']==.01
    assert result['found']==1 and result['missed']==2 and not result['acceptance']


def test_full_window_metric_is_not_full_series_metric():
    result=temporal_scopes(dict(tape=1,smoothed=[2]*9+[1]))
    assert result['all_smoothed']['frame_fraction_within_15cm']==pytest.approx(.1)
    assert result['full_window']['frame_fraction_within_15cm']==1
    assert result['full_window']['samples']==1
