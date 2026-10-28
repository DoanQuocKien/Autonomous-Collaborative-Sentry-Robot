import csv
from pathlib import Path

import numpy as np
import pytest

from sentry.config import load
from tools.evaluate_reid import evaluate_vectors, read_manifest, retrieval_scores, select_threshold


def fixture_rows():
    rows, vectors = [], []
    for partition in ('calibration', 'test'):
        for role in ('gallery', 'query'):
            for i in range(5):
                rows.append(dict(sample_id=f'{partition}{role}{i}', identity=str(i), partition=partition,
                                 role=role, session=partition, entry_id=f'{role}{i}', camera=role))
                vectors.append(np.eye(512)[i])
    return rows, vectors


def test_rank1_roc_and_frozen_calibration_threshold():
    rows, vectors = fixture_rows()
    report = evaluate_vectors(rows, vectors, load()['reid'])
    assert report['test']['rank1'] == 1 and report['acceptance_pass']
    assert report['test']['cmc_by_identity'] == {'1': 1., '3': 1., '5': 1.}
    assert report['test']['cross_camera_queries'] == 5
    assert report['test_at_frozen_threshold']['far'] == 0
    assert report['test_at_frozen_threshold']['threshold'] == report['threshold_selected_on_calibration']['threshold']


def test_tied_identities_do_not_get_arbitrary_rank1_credit():
    rows, vectors = fixture_rows()
    vectors = [np.eye(512)[0]] * len(vectors)
    assert retrieval_scores(rows, vectors, 'test')['rank1'] == 0
    assert retrieval_scores(rows, vectors, 'test')['cmc_by_identity']['1'] == 0
    point, _ = select_threshold(dict(genuine=[.8], impostor=[.9]), .01)
    assert point['threshold'] > .9 and point['tar'] == 0


def write_manifest(tmp_path):
    rows, _ = fixture_rows()
    for i, row in enumerate(rows):
        p = tmp_path / f'{i}.jpg'
        p.write_bytes(str(i).encode())
        row['image'] = p.name
    path = tmp_path / 'manifest.csv'
    def save():
        with path.open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    return path, rows, save


@pytest.mark.parametrize('kind', ['entry_leak', 'session_leak', 'duplicate_image', 'duplicate_id', 'partial_box'])
def test_manifest_leakage_guards(tmp_path, kind):
    path, rows, save = write_manifest(tmp_path)
    if kind == 'entry_leak':
        rows[5]['entry_id'] = rows[0]['entry_id']
    elif kind == 'session_leak':
        rows[10]['session'] = 'calibration'
    elif kind == 'duplicate_image':
        rows[1]['image'] = rows[0]['image']
    elif kind == 'duplicate_id':
        rows[1]['sample_id'] = rows[0]['sample_id']
    else:
        for row in rows:
            row['x1'] = '0'
    save()
    with pytest.raises(ValueError):
        read_manifest(path)


def test_valid_manifest_and_identity_count_gate(tmp_path):
    path, _, save = write_manifest(tmp_path)
    save()
    assert len(read_manifest(path)) == 20
    rows, vectors = fixture_rows()
    settings = dict(load()['reid'], min_eval_identities=6)
    assert not evaluate_vectors(rows, vectors, settings)['acceptance_pass']


def test_reject_all_threshold_cannot_be_recommended():
    rows, vectors = fixture_rows()
    for i, row in enumerate(rows):
        if row['partition'] == 'calibration':
            vectors[i] = np.eye(512)[0]
    report = evaluate_vectors(rows, vectors, load()['reid'])
    assert report['threshold_selected_on_calibration']['threshold'] > 1
    assert not report['acceptance_pass']
