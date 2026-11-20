"""Check editor source hashes and local links in the consolidated report."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlsplit


def check(root: Path, registry: Path, report: Path) -> dict:
    doc = json.loads(registry.read_text(encoding='utf-8'))
    errors = []
    for entry in doc['files']:
        try:
            data = subprocess.check_output(['git', 'show', entry['source_commit'] + ':' + entry['path']], cwd=root, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError:
            errors.append('pinned source unavailable: ' + entry['path'])
            continue
        if hashlib.sha256(data).hexdigest() != entry['sha256']:
            errors.append('source hash mismatch: ' + entry['path'])
    for link in re.findall(r'!?\[[^]]*\]\(([^)]+)\)', report.read_text(encoding='utf-8')):
        parsed = urlsplit(link)
        if parsed.scheme or parsed.netloc or not parsed.path:
            continue
        if not (report.parent / unquote(parsed.path)).is_file():
            errors.append('missing report link: ' + link)
    return dict(status='FAIL' if errors else 'PASS', source_files=len(doc['files']), errors=errors)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('.'))
    args = parser.parse_args()
    root = args.root
    result = check(root, root/'reports/kouun-rokku/week-07/editor-source-registry.json',
                   root/'reports/midterm_report_draft.md')
    print(json.dumps(result, indent=2))
    raise SystemExit(result['status'] != 'PASS')


if __name__ == '__main__':
    main()
