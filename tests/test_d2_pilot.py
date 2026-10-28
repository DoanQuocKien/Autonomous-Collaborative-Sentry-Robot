import csv
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from tools.evaluate_d2_pilot import associate_person, entry_metrics, face_metrics, read_session


def test_face_person_association_rejects_ambiguous_or_missing():
    face = (10, 10, 20, 20)
    person = SimpleNamespace(class_id=0, confidence=.9, xyxy=(0, 0, 30, 80))
    other = SimpleNamespace(class_id=0, confidence=.9, xyxy=(40, 0, 60, 80))
    assert associate_person(face, [person, other], .25) == (person.xyxy, None)
    assert associate_person(face, [person, person], .25)[1] == 'ambiguous_person'
    assert associate_person(face, [other], .25)[1] == 'no_associated_person'
    with pytest.raises(ValueError):
        associate_person((10, 10, float('nan'), 20), [], .25)


def fixture_entries():
    groups, gallery, vectors, rows = {}, {}, {}, []
    for identity in range(3):
        for entry in range(2):
            key = (str(identity), 'c01', entry)
            path = Path(f'{identity}_{entry}.jpg')
            row = dict(member=str(identity), _entry=key, _path=path)
            rows.append(row)
            groups[key] = [row]
            if entry == 0:
                gallery[str(identity)] = key
            vector = np.zeros(512, np.float32)
            vector[identity] = 1
            vectors[path] = vector
    return rows, groups, gallery, vectors


def test_entry_pilot_counts_missing_queries_as_failures():
    _, groups, gallery, vectors = fixture_entries()
    del vectors[Path('0_1.jpg')]
    report = entry_metrics(groups, gallery, vectors)
    assert report['rank1'] == 1
    assert report['rank1_including_missing'] == pytest.approx(2 / 3)
    assert report['missing_query_entries'] == 1
    assert report['cross_camera_queries'] == 0
    assert report['recommended_threshold'] is None
    del vectors[Path('1_0.jpg')]
    report = entry_metrics(groups, gallery, vectors)
    assert not report['scored'] and report['missing_gallery_entries'] == 1


def test_face_pilot_uses_disjoint_entry_enrollment_and_fixed_threshold():
    rows, _, gallery, vectors = fixture_entries()
    report = face_metrics(rows, gallery, vectors, .45)
    assert report['genuine_queries'] == 6
    assert report['impostor_queries'] == 6
    assert report['fixed_config_threshold']['tar'] == 1
    assert report['fixed_config_threshold']['far'] == 0
    assert not report['t1_passed']
    assert report['recommended_threshold'] is None


def test_session_rejects_duplicate_bytes_and_path_escape(tmp_path):
    table = tmp_path / 'd2_faces.csv'
    fields = ['member', 'clip', 'frame_file', 'entry', 'x1', 'y1', 'x2', 'y2']
    folder = tmp_path / 'a' / 'c01'
    folder.mkdir(parents=True)
    for file in ('f1.jpg', 'f2.jpg'):
        (folder / file).write_bytes(b'duplicate')
    rows = [dict(zip(fields, ['a', 'c01', f'f{i}.jpg', i, 1, 1, 2, 2])) for i in (1, 2)]
    def write():
        with table.open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    write()
    with pytest.raises(ValueError, match='duplicate'):
        read_session(tmp_path)
    rows[0]['frame_file'] = '../../../outside.jpg'
    write()
    with pytest.raises(ValueError, match='escapes'):
        read_session(tmp_path)
