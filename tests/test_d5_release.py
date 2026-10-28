import csv
import json
from pathlib import Path

import pytest

from tools.evaluate_d5_holdout import audit
from tools.freeze_d5 import sha256
from tools.check_d5_onnx import decoded_agreement
import numpy as np


def test_decoded_parity_requires_same_classes_and_one_to_one_boxes():
    ref = (np.array([[0, 0, 10, 10], [0, 0, 10, 10]]), None, np.array([0, 0]), None)
    candidate = (np.array([[0, 0, 10, 10]]), None, np.array([0]), None)
    score = decoded_agreement(ref, candidate)
    assert score['matched'] == 1 and score['fraction'] == .5 and not score['same_count']
    wrong_class = (candidate[0], None, np.array([1]), None)
    assert decoded_agreement(ref, wrong_class)['matched'] == 0


def fixture(tmp_path):
    images, labels = tmp_path / 'images', tmp_path / 'labels'
    images.mkdir()
    labels.mkdir()
    image = images / 'sample.jpg'
    image.write_bytes(b'held out image fixture')
    label = labels / 'sample.txt'
    label.write_text('4 0.5 0.5 0.2 0.1\n')
    frozen = tmp_path / 'release.json'
    frozen.write_text(json.dumps(dict(classes=['leg','footwear','backpack','bag','wire','chair','table','plant'],
        provenance=dict(capture_sessions=['1024'], image_sha256=['train_sha']))))
    row = dict(image='images/sample.jpg', label='labels/sample.txt', session='1028', floor='glossy')
    manifest = tmp_path / 'manifest.csv'
    def save():
        with manifest.open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(row))
            writer.writeheader()
            writer.writerow(row)
    return manifest, frozen, row, save


def test_holdout_audit_reports_missing_matte_instead_of_pass(tmp_path):
    manifest, frozen, row, save = fixture(tmp_path)
    save()
    rows, result = audit(manifest, frozen)
    assert len(rows) == 1 and not result['floor_comparison_complete']


@pytest.mark.parametrize('kind', ['same_session', 'same_image', 'invalid_floor', 'missing_label', 'wrong_layout'])
def test_independent_holdout_guards(tmp_path, kind):
    manifest, frozen, row, save = fixture(tmp_path)
    if kind == 'same_session':
        row['session'] = '1024'
    elif kind == 'same_image':
        state = json.loads(frozen.read_text())
        state['provenance']['image_sha256'] = [sha256(tmp_path / row['image'])]
        frozen.write_text(json.dumps(state))
    elif kind == 'invalid_floor':
        row['floor'] = 'unknown'
    elif kind == 'missing_label':
        (tmp_path / row['label']).unlink()
    else:
        row['label'] = 'wrong.txt'
    save()
    with pytest.raises((ValueError, FileNotFoundError)):
        audit(manifest, frozen)
