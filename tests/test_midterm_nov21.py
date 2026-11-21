"""Guard the diagnostic report against CSV drift and false acceptance claims."""
import csv
import io
import json
import subprocess

import pytest

from tools import build_midterm_hnhl_nov21 as builder


def source(relative):
    return subprocess.check_output(['git', 'show', builder.SOURCE + ':' + builder.FOLDER + relative], cwd=builder.ROOT)


def rows(relative):
    return list(csv.DictReader(io.StringIO(source(relative).decode('utf-8'))))


def test_saved_snapshot_reproduces_and_does_not_promote_diagnostics_to_acceptance():
    result = builder.collect()
    assert result == json.loads(builder.OUT.read_text(encoding='utf-8'))
    assert len(result['sources']) == 38
    assert not any(result['acceptance'].values())
    assert result['deployment']['runner_success']
    assert not result['deployment']['automatic_map_vantage']
    assert {p['number'] for p in result['github_snapshot']['pull_requests'] if p['merged']} == {113, 132, 133}
    assert not result['scope']['workflow_closure_is_acceptance']
    latency = result['existing_f7_latency']['video_latency_1111']
    assert latency['frames'] == 2351
    assert not latency['fps_20_met'] and not latency['decoded_p95_50ms_met']


def test_pursuit_summary_drift_is_rejected():
    summary = json.loads(source('pursuit_take3_b_1/summary.json'))
    summary['time_fraction_distance_in_band_of_run'] = .8
    with pytest.raises(ValueError, match='summary differs from CSV'):
        builder.pursuit_snapshot(summary, rows('pursuit_take3_b_1/log.csv'))


@pytest.mark.parametrize('fault', ['state', 'handshake', 'frames', 'timestamp', 'tape', 'success'])
def test_deployment_evidence_mismatch_is_rejected(fault):
    summary = json.loads(source('stage1_take3_a_1/summary.json'))
    log = rows('stage1_take3_a_1/log.csv')
    handshake = rows('stage1_take3_a_1/handshake.csv')
    frames = rows('stage1_take3_a_1/frames.csv')
    tape = json.loads(source('stage1_take3_a_1/tape_note.json'))
    if fault == 'state':
        summary['state_changes'][-1][0] += 1
    elif fault == 'handshake':
        handshake.pop()
    elif fault == 'frames':
        frames.pop()
    elif fault == 'timestamp':
        log[1]['t'] = 'nan'
    elif fault == 'tape':
        tape['runner_final_range_estimate_m'] += .1
    else:
        summary['success'] = False
    with pytest.raises(ValueError):
        builder.deployment_snapshot(summary, log, handshake, frames, tape)


def test_mutable_source_ref_is_rejected_before_reading_git():
    with pytest.raises(ValueError, match='immutable Git SHA'):
        builder.collect('origin/main')


def test_latency_is_recomputed_from_raw_clocks_before_trusting_saved_metrics():
    prefix = 'reports/DoanQuocKien/week-06/latency_1111/video_latency_1111'
    summary = json.loads(subprocess.check_output(['git', 'show', builder.SOURCE + ':' + prefix + '.json'], cwd=builder.ROOT))
    raw = subprocess.check_output(['git', 'show', builder.SOURCE + ':' + prefix + '.csv'], cwd=builder.ROOT).decode('utf-8')
    log = list(csv.DictReader(io.StringIO(raw)))
    log[0]['t_cap_jetson_s'] = str(float(log[0]['t_cap_jetson_s']) + .1)
    with pytest.raises(ValueError, match='corrected raw timestamps'):
        builder.latency_snapshot(summary, log)
