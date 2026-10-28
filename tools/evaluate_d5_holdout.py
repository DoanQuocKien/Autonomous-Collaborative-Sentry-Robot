"""Audit an independent D5 capture before evaluating a frozen candidate.

Manifest CSV: image,label,session,floor. Paths relative to CSV, floor=glossy/matte.
Use only reviewed labels. The report distinguishes detection from distance/HIL.
"""
import argparse
import csv
import json
from pathlib import Path
import tempfile

import yaml

from tools.freeze_d5 import sha256
from tools.prepare_d5_yolo_dev import validate_label


def audit(manifest_path, frozen_manifest):
    manifest_path = Path(manifest_path)
    frozen = json.loads(Path(frozen_manifest).read_text(encoding='utf-8'))
    rows = list(csv.DictReader(manifest_path.open(encoding='utf-8-sig', newline='')))
    if not rows:
        raise ValueError('nonempty independent D5 manifest required')
    training = set(frozen['provenance']['capture_sessions'])
    train_hashes = set(frozen['provenance']['image_sha256'])
    seen, floors, sessions = set(), set(), set()
    for row in rows:
        if any(not row.get(k) for k in ('image', 'label', 'session', 'floor')):
            raise ValueError('image, label, session and floor required')
        if row['session'] in training:
            raise ValueError('capture session overlaps the training/development session')
        if row['floor'] not in ('glossy', 'matte'):
            raise ValueError('confirmed glossy/matte label required')
        image = (manifest_path.parent / row['image']).resolve()
        label = (manifest_path.parent / row['label']).resolve()
        # Ultralytics discovers labels by the images/ -> labels/ convention.
        expected = Path(str(image).replace('/images/', '/labels/').replace('\\images\\', '\\labels\\')).with_suffix('.txt')
        if label != expected:
            raise ValueError('image/label must use the Ultralytics images/labels layout')
        digest = sha256(image)
        if digest in train_hashes or digest in seen:
            raise ValueError('duplicate image within holdout or against development data')
        seen.add(digest)
        row['_instances'], row['_classes'] = validate_label(label)
        row['_image'] = image
        floors.add(row['floor'])
        sessions.add(row['session'])
    return rows, dict(images=len(rows), capture_sessions=sorted(sessions), floors=sorted(floors),
                     floor_comparison_complete=floors == {'glossy', 'matte'},
                     manifest_sha256=sha256(manifest_path), classes=frozen['classes'])


def run(manifest_path, artifact_dir, out, device='0'):
    from ultralytics import YOLO
    artifact_dir, out = Path(artifact_dir), Path(out)
    frozen_path = artifact_dir / 'manifest.json'
    frozen = json.loads(frozen_path.read_text())
    weights = artifact_dir / 'd5_candidate.pt'
    if sha256(weights) != frozen['weights_sha256']:
        raise ValueError('frozen checkpoint hash mismatch')
    rows, report = audit(manifest_path, frozen_path)
    report.update(frozen_manifest_sha256=sha256(frozen_path), weights_sha256=sha256(weights))
    by_floor = {}
    with tempfile.TemporaryDirectory(prefix='d5_holdout_') as tmp:
        for floor in sorted({r['floor'] for r in rows}):
            selected = [r for r in rows if r['floor'] == floor]
            file_list = Path(tmp) / (floor + '.txt')
            file_list.write_text('\n'.join(str(r['_image']) for r in selected), encoding='utf-8')
            config = Path(tmp) / (floor + '.yaml')
            config.write_text(yaml.safe_dump(dict(path=tmp, train=str(file_list), val=str(file_list),
                                                 names=frozen['classes'])), encoding='utf-8')
            model = YOLO(str(weights))
            metrics = model.val(data=str(config), imgsz=frozen['input_size'], device=device,
                                plots=False, project='data/d5_holdout_runs', name=floor, exist_ok=False)
            values = {}
            for index, cls in enumerate(metrics.box.ap_class_index):
                values[frozen['classes'][int(cls)]] = dict(precision=float(metrics.box.p[index]),
                    recall=float(metrics.box.r[index]), map50=float(metrics.box.ap50[index]))
            # Empty controls are evaluated at a fixed declared confidence.
            controls = [r for r in selected if r['_instances'] == 0]
            alarms = 0
            for row in controls:
                result = model.predict(str(row['_image']), imgsz=frozen['input_size'], device=device,
                                       conf=.25, verbose=False)[0]
                alarms += int(any(int(c) == frozen['classes'].index('wire') for c in result.boxes.cls))
            by_floor[floor] = dict(classes=values, empty_controls=len(controls),
                                   wire_alarm_frames=alarms, wire_alarm_confidence=.25,
                                   wire_alarm_fraction=alarms / len(controls) if controls else None,
                                   operating_point='Ultralytics class metrics at validation operating point')
    report.update(by_floor=by_floor, t1_passed=False, distance_passed=False, motor_commands_sent=0,
                  pending=['contact/forward distance against tape', 'review detection operating point and per-class targets',
                           'hardware exploration T2; this command cannot approve deployment'])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--manifest', required=True)
    ap.add_argument('--artifact-dir', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--device', default='0')
    a = ap.parse_args()
    report = run(a.manifest, a.artifact_dir, a.out, a.device)
    print(json.dumps({k: report[k] for k in ('images', 'floors', 't1_passed')}, indent=2))


if __name__ == '__main__':
    main()
