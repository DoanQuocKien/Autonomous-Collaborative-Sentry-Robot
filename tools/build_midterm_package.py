"""Build a code/report ZIP from an audited Git commit, without repository history."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import zipfile

from tools.check_midterm_package import audit


def build(ref: str, out: Path, *, cwd=None) -> dict:
    commit = subprocess.check_output(['git', 'rev-parse', '--verify', ref + '^{commit}'], cwd=cwd, text=True).strip()
    result = audit(commit, cwd=cwd)
    if result['violations']:
        raise ValueError('Forbidden paths in committed package: ' + ', '.join(result['violations']))
    raw = subprocess.check_output(['git', 'archive', '--format=zip', commit], cwd=cwd)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        timestamp = archive.infolist()[0].date_time
        files = {item.filename: hashlib.sha256(archive.read(item)).hexdigest()
                 for item in archive.infolist() if not item.is_dir()}
    manifest = dict(commit=commit, files=files, file_count=len(files),
                    history_included=False, history_verified=False,
                    note='The archive omits .git. Original repository history is not sanitized by this operation.')
    # Exclusive creation protects an earlier package and its reviewable checksum.
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('xb') as stream:
        stream.write(raw)
    with zipfile.ZipFile(out, 'a', compression=zipfile.ZIP_DEFLATED) as archive:
        info = zipfile.ZipInfo('SUBMISSION-MANIFEST.json', date_time=timestamp)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        archive.writestr(info, json.dumps(manifest, indent=2) + '\n')
    return dict(commit=commit, archive=str(out), sha256=hashlib.sha256(out.read_bytes()).hexdigest(),
                file_count=len(files), history_included=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ref', default='HEAD')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.ref, args.out), indent=2))


if __name__ == '__main__':
    main()
