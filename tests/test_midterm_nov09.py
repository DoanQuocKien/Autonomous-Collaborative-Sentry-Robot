import pytest
from tools.build_midterm_hnhl_nov09 import summarize_link


def trial(n, seconds, held):
    return dict(trial=str(n),stop_seen_after_s=str(seconds),r1_still_held=str(held))


def test_video_proxy_never_certifies_motor_stop_and_flags_r1_confound():
    result=summarize_link([trial(1,.524,1),trial(2,.516,1),trial(3,.503,1),trial(4,.521,0),trial(5,.481,1)])
    assert result['median_video_proxy_ms']==516
    assert result['r1_not_held_at_end_trials']==[4]
    assert not result['limit_350ms_proven'] and not result['violation_proven']
    assert not result['mechanical_stop_measured']


@pytest.mark.parametrize('rows',[[],[trial(1,'nan',1)],[trial(1,-.1,1)],[trial(1,.2,2)]])
def test_invalid_proxy_evidence_is_rejected(rows):
    with pytest.raises(ValueError): summarize_link(rows)
