"""Audit the shared D2 cafe session and measure a same-session entry-held-out pilot.

Uses every supplied walker-face row (no sharpness filtering). Gallery is the
earliest entry per member, queries are all other entries. Face boxes associate
YOLO person proposals to the presumed walker; ambiguous/missing boxes abstain.
Automatic walker/entry labels are provisional, not manually verified truth.
This one-camera, three-person session cannot pass independent re-ID T1.
Raw images, person boxes, embeddings and identity names stay in ignored data/.
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

from sentry.config import DEFAULT_PATH, load
from sentry.perception.reid import ARCHITECTURES, OSNetEncoder, crop_person, normalize
from tools.evaluate_reid import operating_point, retrieval_scores


def associate_person(face, detections, confidence, min_overlap=0.8):
    """Require exactly one class-0 proposal containing >=80% of the face area."""
    if not 0 < min_overlap <= 1:
        raise ValueError('face overlap must be in (0,1]')
    x1, y1, x2, y2 = map(float, face)
    if not np.isfinite(face).all() or x2 <= x1 or y2 <= y1:
        raise ValueError('finite positive face box required')
    candidates = []
    for d in detections:
        if d.class_id != 0 or not np.isfinite(d.confidence) or d.confidence < confidence:
            continue
        a, b, c, e = d.xyxy
        if not np.isfinite(d.xyxy).all() or c <= a or e <= b:
            continue
        overlap = max(0, min(c, x2) - max(a, x1)) * max(0, min(e, y2) - max(b, y1))
        if overlap / ((x2 - x1) * (y2 - y1)) >= min_overlap:
            candidates.append(d.xyxy)
    return ((candidates[0], None) if len(candidates) == 1 else
            (None, 'ambiguous_person' if candidates else 'no_associated_person'))


def read_session(root):
    root = Path(root).resolve()
    table = root / 'd2_faces.csv'
    with table.open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError('nonempty walker table required')
    seen, digests, grouped = set(), set(), defaultdict(list)
    for row in rows:
        image = (root / row['member'] / row['clip'] / row['frame_file']).resolve()
        if not image.is_relative_to(root):
            raise ValueError('D2 image path escapes session')
        key = (row['member'], row['clip'], int(row['entry']))
        sample = (key[0], key[1], row['frame_file'])
        digest = hashlib.sha256(image.read_bytes()).hexdigest()
        if sample in seen or digest in digests:
            raise ValueError('duplicate D2 walker sample/image')
        seen.add(sample)
        digests.add(digest)
        row['_path'], row['_entry'] = image, key
        row['_face'] = tuple(float(row[k]) for k in ('x1', 'y1', 'x2', 'y2'))
        grouped[key].append(row)
    # Entry numbering is clip-local; a member with several clips requires an
    # explicitly reviewed chronological order rather than an arbitrary filename.
    identities = {k[0] for k in grouped}
    if len(identities) < 2:
        raise ValueError('at least two identities required for ROC')
    if any(len({k[1] for k in grouped if k[0] == who}) != 1 for who in identities):
        raise ValueError('pilot requires one clip per member; review multi-clip ordering')
    gallery = {who: min((k for k in grouped if k[0] == who), key=lambda k: k[2]) for who in identities}
    if any(sum(k[0] == who for k in grouped) < 2 for who in identities):
        raise ValueError('each member needs independent gallery and query entries')
    return rows, grouped, gallery


def entry_metrics(grouped, gallery, vectors):
    """Average normalized frame vectors within entries; never split an entry."""
    rows, encoded, missing_gallery, missing_query = [], [], 0, 0
    for key, group in sorted(grouped.items()):
        values = [vectors[r['_path']] for r in group if r['_path'] in vectors]
        is_gallery = key == gallery[key[0]]
        if not values:
            missing_gallery += int(is_gallery)
            missing_query += int(not is_gallery)
            continue
        rows.append(dict(identity=key[0], session='1028', entry_id='/'.join(map(str, key)),
                         camera='esp32', partition='pilot', role='gallery' if is_gallery else 'query'))
        encoded.append(normalize(np.mean(values, axis=0)))
    total_queries = sum(k != gallery[k[0]] for k in grouped)
    if missing_gallery or missing_query == total_queries:
        return dict(scored=False, missing_gallery_entries=missing_gallery,
                    missing_query_entries=missing_query, total_query_entries=total_queries)
    scores = retrieval_scores(rows, encoded, 'pilot')
    curve = [operating_point(scores, t) for t in sorted(set(scores['genuine'] + scores['impostor'] + [float(np.nextafter(1., 2.))]))]
    return dict(scored=True, **{k: v for k, v in scores.items() if k not in ('genuine', 'impostor')},
                missing_gallery_entries=0, missing_query_entries=missing_query,
                total_query_entries=total_queries,
                rank1_including_missing=scores['rank1'] * scores['known_queries'] / total_queries,
                descriptive_roc=curve, recommended_threshold=None)


def face_metrics(rows, gallery, vectors, threshold):
    """Three leave-one-member-out folds; enrollment uses first entry only."""
    genuine, impostor = [], []
    for stranger in sorted(gallery):
        refs = {who: [vectors[r['_path']] for r in rows if r['_entry'] == key]
                for who, key in gallery.items() if who != stranger}
        for row in rows:
            who = row['member']
            if who != stranger and row['_entry'] == gallery[who]:
                continue
            score = max(float(vectors[row['_path']] @ ref) for group in refs.values() for ref in group)
            (impostor if who == stranger else genuine).append(score)
    scores = dict(genuine=genuine, impostor=impostor)
    return dict(genuine_queries=len(genuine), impostor_queries=len(impostor), folds=len(gallery),
                fixed_config_threshold=operating_point(scores, threshold),
                descriptive_roc=[operating_point(scores, t) for t in sorted(set(genuine + impostor + [float(np.nextafter(1., 2.))]))],
                recommended_threshold=None, t1_passed=False,
                note='DQK-supplied buffalo_s vectors, not recomputed locally; within-session frame-level leave-one-member-out, queries correlated')


def run(root, out, config_path=DEFAULT_PATH):
    root = Path(root).resolve()
    rows, grouped, gallery = read_session(root)
    config = load(config_path)
    settings = config['reid']
    faces, crops, rejected = {}, {}, Counter()
    npz_hashes = []
    for member, clip in sorted({(r['member'], r['clip']) for r in rows}):
        path = root / member / clip / 'faces.npz'
        npz_hashes.append(hashlib.sha256(path.read_bytes()).hexdigest())
        with np.load(path, allow_pickle=False) as values:
            if len(values['frame_files']) != len(values['embeddings']):
                raise ValueError('face NPZ count mismatch')
            for file, vector in zip(values['frame_files'], values['embeddings']):
                key = (root / member / clip / str(file)).resolve()
                if key in faces:
                    raise ValueError('duplicate face vector filename')
                faces[key] = normalize(vector)
    if set(faces) != {r['_path'] for r in rows}:
        raise ValueError('face NPZ must match walker rows exactly')
    from sentry.perception.obstacle import YOLOPredictor
    detector_path = Path(config_path).resolve().parent / settings['person_weights']
    detector = YOLOPredictor(detector_path, dict(config['obstacle'], class_ids=[0],
                             confidence=settings['person_confidence'], imgsz=settings['person_imgsz'],
                             device=settings['person_device']))
    for row in rows:
        image = cv2.imread(str(row['_path']))
        if image is None:
            raise ValueError('unreadable D2 image')
        box, reason = associate_person(row['_face'], detector(image), settings['person_confidence'],
                                       settings['pilot_face_overlap_min'])
        crop = crop_person(image, box, settings['min_crop_height'], settings['min_crop_width']) if box else None
        if crop is None:
            rejected[reason or 'crop_too_small'] += 1
        else:
            crops[row['_path']] = crop
    models = {}
    for arch in ARCHITECTURES:
        encoder = OSNetEncoder.from_config(arch, config_path)
        paths = list(crops)
        vectors = {}
        for start in range(0, len(paths), 16):
            batch = paths[start:start + 16]
            vectors.update(zip(batch, encoder.encode([crops[p] for p in batch])))
        models[arch] = dict(model_id=encoder.model_id, **entry_metrics(grouped, gallery, vectors))
    report = dict(status='REAL_D2_SAME_SESSION_PILOT_NOT_T1', session='1028',
                  identities=len(gallery), entries=len(grouped), walker_frames=len(rows),
                  entry_counts=sorted(Counter(k[0] for k in grouped).values()),
                  person_crops=len(crops), rejections=dict(rejected), models=models,
                  face=face_metrics(rows, gallery, faces, config['thresholds']['whitelist_cosine']),
                  gallery_rule='first entry per member; all remaining entries are queries',
                  t1_passed=False, recommended_model=None, motor_commands_sent=0,
                  provenance=dict(walker_csv_sha256=hashlib.sha256((root / 'd2_faces.csv').read_bytes()).hexdigest(),
                                  face_npz_sha256=sorted(npz_hashes),
                                  frame_hashes_sha256=hashlib.sha256(''.join(sorted(hashlib.sha256(r['_path'].read_bytes()).hexdigest() for r in rows)).encode()).hexdigest(),
                                  detector_sha256=hashlib.sha256(detector_path.read_bytes()).hexdigest(),
                                  config_sha256=hashlib.sha256(Path(config_path).read_bytes()).hexdigest()),
                  limitations=['one session, one ESP32 camera, three identities; no D3/robot handoff',
                               'automatic largest-face walker and gap-based entries need manual identity review',
                               'person boxes associated to face, not manually labeled full-body ground truth',
                               'same clothing/background and adjacent entries can inflate scores',
                               'three identities cannot satisfy the five-identity re-ID gate',
                               'no threshold/model selection on this pilot; ROC is descriptive only'])
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', default='data/D2/1028')
    ap.add_argument('--out', required=True)
    ap.add_argument('--config', default=str(DEFAULT_PATH))
    args = ap.parse_args()
    report = run(args.root, args.out, args.config)
    print(json.dumps({k: report[k] for k in ('status', 'walker_frames', 'entries', 'person_crops', 't1_passed')}))


if __name__ == '__main__':
    main()
