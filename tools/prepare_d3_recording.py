"""Convert tools.record JetBot JSONL to private timestamped replay epochs.

Offline only. Never interpolates timestamps, drops frames, labels people, or
claims D3 acceptance. Output includes UNREVIEWED annotation templates. Retain
the original recording folder with its prepared manifests for relative paths.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(recording, data_root):
    recording, data_root = Path(recording).resolve(), Path(data_root).resolve()
    if not recording.is_relative_to(data_root):
        raise ValueError('private recording must stay under data/')
    image_root = (recording / 'jetbot').resolve()
    if not image_root.is_relative_to(recording):
        raise ValueError('JetBot images escape recording folder')
    metadata = (recording / 'jetbot_meta.jsonl').resolve()
    if not metadata.is_relative_to(recording):
        raise ValueError('metadata path escapes recording folder')
    epochs, rows, seen_files, previous = [], [], set(), None
    with metadata.open(encoding='utf-8-sig') as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError('metadata row must be an object')
            seq, t = row.get('seq'), row.get('t_cap')
            if (type(seq) is not int or seq < 0 or isinstance(t, bool)
                    or not isinstance(t, (float, int)) or not math.isfinite(t)):
                raise ValueError('nonnegative integer seq and finite numeric t_cap required')
            filename = row.get('file')
            if (not isinstance(filename, str) or not filename or '/' in filename or '\\' in filename
                    or Path(filename).name != filename or Path(filename).suffix.lower() not in ('.jpg', '.jpeg')):
                raise ValueError('metadata file must be a JPEG basename')
            image = (image_root / filename).resolve()
            if not image.is_relative_to(image_root) or image in seen_files:
                raise ValueError('image path escapes recording or is reused')
            for key in ('w', 'h'):
                if type(row.get(key)) is not int or row[key] <= 0:
                    raise ValueError('positive integer image dimensions required')
            decoded = cv2.imread(str(image))
            if decoded is None or decoded.shape[:2] != (row['h'], row['w']):
                raise ValueError('missing/invalid image or dimensions disagree with metadata')
            if previous is not None:
                if seq == previous['seq'] and t >= previous['t_cap']:
                    raise ValueError('duplicate source sequence; cannot manufacture a replay timestamp')
                reset = seq < previous['seq'] or t < previous['t_cap']
                if reset:
                    epochs.append(rows)
                    rows = []
                elif t <= previous['t_cap']:
                    raise ValueError('capture timestamps must strictly increase within an epoch')
            seen_files.add(image)
            rows.append(dict(t=t, seq=seq, source_image=image, w=row['w'], h=row['h'],
                             source_line=line_number, image_sha256=sha256(image)))
            previous = row
    if not rows:
        raise ValueError('nonempty JetBot recording required')
    epochs.append(rows)
    return recording, metadata, epochs


def prepare(recording, out_dir, data_root=None):
    data_root = (ROOT / 'data' if data_root is None else Path(data_root)).resolve()
    out_dir = Path(out_dir).resolve()
    if not out_dir.is_relative_to(data_root):
        raise ValueError('private manifests/templates must stay under data/')
    if out_dir.exists():
        raise FileExistsError('choose a new output directory; never overwrite annotations')
    recording, metadata, epochs = audit(recording, data_root)
    if (recording.is_relative_to(out_dir) or out_dir.is_relative_to(recording / 'jetbot')):
        raise ValueError('output cannot contain original recording or be inside raw images')
    summary = dict(schema_version=1, camera='jetbot', source_metadata_sha256=sha256(metadata),
        frames=sum(len(rows) for rows in epochs), epochs=[], reviewed_labels=False,
        t1_passed=False, motor_commands_sent=0,
        limitations=['annotation templates are empty and UNREVIEWED, not ground truth',
                     'sequence gaps include intentionally skipped frames; not packet loss',
                     'retain original recording and prepared folder together; do not replace timestamps'])
    # All rows/images validated before creating output. An interrupted export has
    # no READY.json; downstream callers must use only a completed export.
    out_dir.mkdir(parents=True)
    for index, rows in enumerate(epochs):
        folder = out_dir / ('epoch-%03d' % index)
        folder.mkdir()
        frames = [dict(t=r['t'], image=Path(os.path.relpath(r['source_image'], folder)).as_posix(),
                       seq=r['seq'], w=r['w'], h=r['h'], image_sha256=r['image_sha256']) for r in rows]
        manifest = dict(camera='jetbot', timestamp_source='jetbot_meta.jsonl:t_cap', frames=frames)
        template = dict(kind='D3_TRACKING', camera='jetbot', reviewed=False, annotation_template=True,
                        frames=[dict(t=r['t'], objects=[]) for r in rows])
        for name, value in [('frames.json', manifest), ('truth-template.json', template)]:
            (folder / name).write_text(json.dumps(value, indent=2, allow_nan=False)+'\n', encoding='utf-8')
        summary['epochs'].append(dict(epoch=index, frames=len(rows), duration_s=rows[-1]['t']-rows[0]['t'],
            sequence_gaps=sum(max(0, b['seq']-a['seq']-1) for a, b in zip(rows, rows[1:])),
            manifest='epoch-%03d/frames.json' % index,
            manifest_sha256=sha256(folder/'frames.json'),
            truth_template='epoch-%03d/truth-template.json' % index))
    (out_dir/'READY.json').write_text(json.dumps(summary, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--recording', type=Path, required=True)
    ap.add_argument('--out-dir', type=Path, required=True)
    a = ap.parse_args()
    result = prepare(a.recording, a.out_dir)
    print(json.dumps(dict(frames=result['frames'], epochs=len(result['epochs']), reviewed_labels=False,
                          t1_passed=False, motor_commands_sent=0)))


if __name__ == '__main__':
    main()
