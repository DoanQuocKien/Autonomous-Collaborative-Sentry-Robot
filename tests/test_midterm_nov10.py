import pytest

from tools.build_midterm_hnhl_nov10 import chair_availability,range_stats


def test_no_range_is_not_zero_error():
    doc = dict(rows=[[],[dict(distance_m=None)]],frames=2,
        frames_with_detection=1,frames_with_distance=0,tape_m=1.2,error_m=0)
    result = chair_availability(doc)
    assert result['ranged']==0 and result['median_error_m'] is None
    assert not result['acceptance']
    doc['frames_with_distance']=1
    with pytest.raises(ValueError):
        chair_availability(doc)


def test_median_bias_does_not_mean_all_frames_pass():
    result = range_stats([.9,1.02,1.4],1.0)
    assert result['median_signed_error_m']==pytest.approx(.02)
    assert result['frame_fraction_within_15cm']==pytest.approx(2/3)


@pytest.mark.parametrize('values',[[],[float('nan')],[float('inf')],[-1],[0]])
def test_invalid_range_samples_are_rejected(values):
    with pytest.raises(ValueError):
        range_stats(values,1)
