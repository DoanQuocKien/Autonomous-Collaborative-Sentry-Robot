"""Compare OSNet models on private labeled person crops, with session-held-out ROC.

CSV: sample_id,identity,image,session,entry_id,camera,partition,role[,x1,y1,x2,y2].
partition=calibration/test, role=gallery/query. Images are pre-cropped when xyxy
is absent. Each entry stays in one role/partition. Whole sessions are held out.
No vectors, identities, image paths or images are written to the public report.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import cv2
import numpy as np

from sentry.config import DEFAULT_PATH, load
from sentry.perception.reid import ARCHITECTURES, OSNetEncoder, crop_person, normalize


def read_manifest(path):
    path = Path(path)
    with path.open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError('nonempty re-ID manifest required')
    seen, entries, sessions, hashes = set(), {}, {}, set()
    for row in rows:
        if any(not row.get(k) for k in ('sample_id', 'identity', 'image', 'session', 'entry_id', 'camera', 'partition', 'role')):
            raise ValueError('missing re-ID manifest metadata')
        if row['sample_id'] in seen or row['partition'] not in ('calibration', 'test') or row['role'] not in ('query', 'gallery'):
            raise ValueError('duplicate sample or invalid role/partition')
        seen.add(row['sample_id'])
        entry = (row['session'], row['entry_id'])
        value = (row['partition'], row['role'], row['identity'])
        if entry in entries and entries[entry] != value:
            raise ValueError('one capture entry cannot leak across roles/identities/partitions')
        entries[entry] = value
        if row['session'] in sessions and sessions[row['session']] != row['partition']:
            raise ValueError('hold out whole sessions between calibration and test')
        sessions[row['session']] = row['partition']
        image_path = (path.parent / row['image']).resolve()
        digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
        # Reject duplicates even if renamed or reboxed. Near-duplicates still
        # require a reviewed session/entry split and are disclosed in the report.
        if digest in hashes:
            raise ValueError('duplicate image bytes in manifest')
        hashes.add(digest)
        row['_path'] = image_path
        box = [row.get(k, '') for k in ('x1', 'y1', 'x2', 'y2')]
        if any(box) and not all(box):
            raise ValueError('provide all xyxy fields or leave all empty')
        row['_box'] = tuple(map(float, box)) if all(box) else None
    for partition in ('calibration', 'test'):
        for role in ('gallery', 'query'):
            if not any(r['partition'] == partition and r['role'] == role for r in rows):
                raise ValueError('gallery and query required in calibration and test')
    return rows


def retrieval_scores(rows, embeddings, partition):
    vectors = np.stack([normalize(v) for v in embeddings])
    if len(rows) != len(vectors):
        raise ValueError('embedding count differs from manifest')
    gallery = [i for i, r in enumerate(rows) if r['partition'] == partition and r['role'] == 'gallery']
    queries = [i for i, r in enumerate(rows) if r['partition'] == partition and r['role'] == 'query']
    if not gallery or not queries:
        raise ValueError('nonempty gallery and query required')
    genuine, impostor, correct, known, unknown = [], [], 0, 0, 0
    cross_camera_queries, identity_ranks = 0, []
    for qi in queries:
        candidates = [gi for gi in gallery if (rows[gi]['session'], rows[gi]['entry_id']) != (rows[qi]['session'], rows[qi]['entry_id'])]
        if not candidates:
            raise ValueError('query has no independent gallery entry')
        scores = np.clip(vectors[candidates] @ vectors[qi], -1, 1)
        same = np.array([rows[gi]['identity'] == rows[qi]['identity'] for gi in candidates])
        if same.any():
            known += 1
            genuine.append(float(scores[same].max()))
            best = float(scores.max())
            # A different identity tied for first is a failure, not an arbitrary
            # success determined by annotation ordering.
            winners = scores >= best - 1e-7
            correct += int(same[winners].all())
            best_genuine = float(scores[same].max())
            wrong_ids = {rows[gi]['identity'] for k, gi in enumerate(candidates)
                         if not same[k] and scores[k] >= best_genuine - 1e-7}
            identity_ranks.append(1 + len(wrong_ids))
            cross_camera_queries += int(any(rows[gi]['camera'] != rows[qi]['camera'] and same[k]
                                            for k, gi in enumerate(candidates)))
        else:
            unknown += 1
        if (~same).any():
            # Max over all wrong IDs gives a query-level false-match score,
            # rather than making FAR small by counting many easy gallery pairs.
            impostor.append(float(scores[~same].max()))
    if not genuine or not impostor:
        raise ValueError('genuine and impostor comparisons required for ROC')
    return dict(genuine=genuine, impostor=impostor, rank1=correct / known,
                cmc_by_identity={str(k): float(np.mean(np.asarray(identity_ranks) <= k)) for k in (1, 3, 5)},
                known_queries=known, unknown_queries=unknown, cross_camera_queries=cross_camera_queries,
                gallery_identities=len({rows[i]['identity'] for i in gallery}))


def operating_point(scores, threshold):
    if not math.isfinite(threshold):
        raise ValueError('finite threshold required')
    genuine, impostor = scores['genuine'], scores['impostor']
    return dict(threshold=float(threshold), tar=float(np.mean(np.asarray(genuine) >= threshold)),
                far=float(np.mean(np.asarray(impostor) >= threshold)))


def select_threshold(scores, far_target):
    if not 0 <= far_target <= 1:
        raise ValueError('FAR target must be in [0,1]')
    thresholds = sorted(set(scores['genuine'] + scores['impostor'] + [float(np.nextafter(1., 2.))]))
    curve = [operating_point(scores, t) for t in thresholds]
    eligible = [p for p in curve if p['far'] <= far_target]
    return max(eligible, key=lambda p: (p['tar'], -p['far'], p['threshold'])), curve


def evaluate_vectors(rows, vectors, settings):
    calibration = retrieval_scores(rows, vectors, 'calibration')
    test = retrieval_scores(rows, vectors, 'test')
    selected, calibration_roc = select_threshold(calibration, settings['far_target'])
    test_point = operating_point(test, selected['threshold'])
    enough = test['gallery_identities'] >= settings['min_eval_identities']
    return dict(calibration={k: v for k, v in calibration.items() if k not in ('genuine', 'impostor')},
                test={k: v for k, v in test.items() if k not in ('genuine', 'impostor')},
                threshold_selected_on_calibration=selected, calibration_roc=calibration_roc,
                test_at_frozen_threshold=test_point,
                test_roc=[operating_point(test, t) for t in sorted(set(test['genuine'] + test['impostor'] + [float(np.nextafter(1., 2.))]))],
                enough_identities=enough, rank1_target_met=test['rank1'] >= settings['rank1_target'],
                acceptance_pass=(enough and test['rank1'] >= settings['rank1_target']
                                 and test_point['far'] <= settings['far_target']
                                 and test_point['tar'] >= settings['verification_tar_target']
                                 and selected['threshold'] <= 1),
                limitations=['identity/entry/session metadata require manual review',
                             'a small sample empirical FAR is not a population FAR bound',
                             'cross-camera handoff only supported for queries counted as cross_camera_queries'])


def run(manifest, out, config_path=DEFAULT_PATH, architectures=ARCHITECTURES):
    rows = read_manifest(manifest)
    settings = load(config_path)['reid']
    crops = []
    for row in rows:
        image = cv2.imread(str(row['_path']))
        if image is None:
            raise ValueError('unreadable person image')
        crop = crop_person(image, row['_box'], settings['min_crop_height'], settings['min_crop_width']) if row['_box'] else image
        if crop is None:
            raise ValueError('annotated person crop too small/outside')
        crops.append(crop)
    results = {}
    for architecture in architectures:
        encoder = OSNetEncoder.from_config(architecture, config_path)
        vectors = np.concatenate([encoder.encode(crops[i:i + 16]) for i in range(0, len(crops), 16)])
        results[architecture] = dict(model_id=encoder.model_id, **evaluate_vectors(rows, vectors, settings))
    # Model choice is on calibration only; test results never choose the winner.
    winner = max(results, key=lambda a: (results[a]['calibration']['rank1'],
                 results[a]['threshold_selected_on_calibration']['tar'], a))
    report = dict(models=results, candidate_selected_on_calibration=winner,
                  recommended_model=winner if results[winner]['acceptance_pass'] else None,
                  manifest_sha256=hashlib.sha256(Path(manifest).read_bytes()).hexdigest(),
                  samples=len(rows), identities=len({r['identity'] for r in rows}),
                  scope='annotated crops only; person detector recall evaluated separately', motor_commands_sent=0)
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--manifest', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--config', default=str(DEFAULT_PATH))
    a = ap.parse_args()
    report = run(a.manifest, a.out, a.config)
    print(json.dumps({k: report[k] for k in ('samples', 'identities', 'recommended_model')}, indent=2))
    raise SystemExit(0 if report['recommended_model'] else 1)


if __name__ == '__main__':
    main()
