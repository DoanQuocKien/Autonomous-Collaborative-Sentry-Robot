import pytest

from tools.profile_pipeline import summarize


def test_budget_report_distinguishes_measured_workload_from_target_acceptance():
    settings = dict(min_fps=15, max_vram_bytes=5500000000)
    r = summarize([.05, .06], [2 * 2**30, 3 * 2**30], settings, True)
    assert r['measured_workload_budget_met'] and r['full_model_mix']
    assert not r['t1_accepted'] and not r['target_rtx4050_verified']
    assert not summarize([.1], [6 * 2**30], settings, False)['measured_workload_budget_met']
    assert not summarize([.05], [5.3 * 2**30], settings, True)['vram_limit_met']  # GB != GiB
    with pytest.raises(ValueError):
        summarize([], [], settings, True)
