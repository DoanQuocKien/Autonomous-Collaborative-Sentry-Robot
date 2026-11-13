import pytest

from tools.build_midterm_hnhl_team_update import summarize_rows


def row(t, distance='1.2', event=''):
    return dict(t=t, forward_m=distance, event=event)


def test_sparse_processed_gaps_and_trigger_time_are_not_dwell_or_acceptance():
    report = summarize_rows([row('0'), row('.1'), row('.6', '1.4', 'TARGET_STATIONARY')])
    assert report['rows'] == 3 and report['median_forward_m'] == 1.2
    assert report['processed_gaps_over_300ms'] == 1
    assert report['max_processed_gap_s'] == .5
    assert report['events'] == [dict(t=.6, event='TARGET_STATIONARY')]
    assert not report['acceptance'] and 'not camera capture' in report['timestamps_scope']


@pytest.mark.parametrize('rows', [[], [row('0'), row('0')], [row('1'), row('0')],
                                  [row('nan')], [row('0', '')], [row('0', 'nan')]])
def test_invalid_numeric_evidence_is_rejected(rows):
    with pytest.raises(ValueError): summarize_rows(rows)
