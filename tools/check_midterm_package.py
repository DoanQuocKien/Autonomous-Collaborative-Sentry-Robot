"""Audit committed package paths; this does not certify or rewrite Git history."""
from __future__ import annotations

import argparse
import json
from pathlib import PurePosixPath
import subprocess

FORBIDDEN_PREFIXES = ('data/', 'recordings/', 'weights/')
FORBIDDEN_NAMES = ('.env', 'secrets.h', 'jetbot_host_key', 'id_rsa', 'id_ed25519')
FORBIDDEN_SUFFIXES = ('.pt', '.pth', '.onnx', '.engine', '.pem', '.key')


def forbidden(path: str) -> bool:
    name = PurePosixPath(path).name.lower()
    lower = path.lower()
    return (lower.startswith(FORBIDDEN_PREFIXES)
            or name in FORBIDDEN_NAMES or name.startswith('.env.')
            or lower.endswith(FORBIDDEN_SUFFIXES)
            or (lower.startswith('team_data/') and lower.endswith('.zip')))


def tracked_paths(ref: str = 'HEAD', *, index: bool = False, cwd=None) -> list[str]:
    command = ['git', 'ls-files', '-z'] if index else ['git', 'ls-tree', '-rz', '--name-only', ref]
    result = subprocess.run(command, cwd=cwd, check=True, stdout=subprocess.PIPE)
    return [path for path in result.stdout.decode().split('\0') if path]


def audit(ref: str = 'HEAD', *, index: bool = False, cwd=None) -> dict:
    paths = tracked_paths(ref, index=index, cwd=cwd)
    return dict(scope='index' if index else 'committed tree', ref=None if index else ref,
                tracked_files=len(paths), violations=[p for p in paths if forbidden(p)],
                history_verified=False,
                note='Path check only. Deleting tracked files does not remove historical data or credentials.')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ref', default='HEAD')
    parser.add_argument('--index', action='store_true', help='pre-commit check of the staging index')
    args = parser.parse_args()
    result = audit(args.ref, index=args.index)
    print(json.dumps(result, indent=2))
    return int(bool(result['violations']))


if __name__ == '__main__':
    raise SystemExit(main())
