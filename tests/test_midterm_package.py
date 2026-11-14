import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

import pytest

from tools.check_midterm_package import audit, forbidden
from tools.build_midterm_package import build


@pytest.mark.parametrize('path', ['data/D5/a.jpg', 'recordings/run/log.csv', 'weights/model.bin',
                                  '.env.production', 'esp32/new/secrets.h', 'data/jetbot_host_key',
                                  'foo/id_ed25519', 'a.ENGINE', 'team_data/D2.zip'])
def test_private_package_paths_are_rejected(path):
    assert forbidden(path)


@pytest.mark.parametrize('path', ['calib/motion.json', 'esp32/sentry_cam/secrets.example.h',
                                  'reports/run/summary.json', 'team_data/README.md'])
def test_public_package_inputs_are_allowed(path):
    assert not forbidden(path)


def repo(tmp_path):
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=tmp_path, text=True)
    git('init', '-q')
    git('config', 'user.name', 'Package test')
    git('config', 'user.email', 'test@example.invalid')
    (tmp_path/'README.md').write_text('reproduce\n')
    git('add', '.')
    git('commit', '-qm', 'test fixture')
    return git


def test_package_uses_commit_not_dirty_workspace_and_has_verified_manifest(tmp_path):
    git = repo(tmp_path)
    (tmp_path/'README.md').write_text('uncommitted change')
    out = tmp_path/'submission.zip'
    result = build('HEAD', out, cwd=tmp_path)
    with zipfile.ZipFile(out) as archive:
        assert archive.read('README.md') == b'reproduce\n'
        assert not any('.git/' in name for name in archive.namelist())
        manifest = json.loads(archive.read('SUBMISSION-MANIFEST.json'))
        assert manifest['commit'] == git('rev-parse', 'HEAD').strip()
        for name, digest in manifest['files'].items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == digest
    assert result['history_included'] is False
    with pytest.raises(FileExistsError):
        build('HEAD', out, cwd=tmp_path)


def test_untracking_does_not_make_committed_tree_pass(tmp_path):
    git = repo(tmp_path)
    (tmp_path/'data').mkdir()
    (tmp_path/'data/private.txt').write_text('fixture data')
    git('add', '.')
    git('commit', '-qm', 'private fixture')
    git('rm', '--cached', 'data/private.txt')
    assert audit(index=True, cwd=tmp_path)['violations'] == []
    assert audit(cwd=tmp_path)['violations'] == ['data/private.txt']
    with pytest.raises(ValueError):
        build('HEAD', tmp_path/'bad.zip', cwd=tmp_path)
    assert not (tmp_path/'bad.zip').exists()


def test_same_commit_produces_same_zip_independent_of_wall_clock(tmp_path, monkeypatch):
    repo(tmp_path)
    monkeypatch.setattr(zipfile.time, 'localtime', lambda *_: (1980, 1, 1, 0, 0, 0, 1, 1, 0))
    first = build('HEAD', tmp_path/'first.zip', cwd=tmp_path)
    monkeypatch.setattr(zipfile.time, 'localtime', lambda *_: (2000, 1, 1, 0, 0, 0, 1, 1, 0))
    second = build('HEAD', tmp_path/'second.zip', cwd=tmp_path)
    assert first['sha256'] == second['sha256']
