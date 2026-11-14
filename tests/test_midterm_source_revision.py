"""Historical source verification must not silently bless changed plans."""
from types import SimpleNamespace

import pytest

from tools import check_midterm_hnhl as checker


def test_historical_hash_uses_pinned_revision_without_reading_current_file(monkeypatch, tmp_path):
    (tmp_path / 'plan.md').write_bytes(b'changed current plan\n')
    monkeypatch.setattr(checker, 'ROOT', tmp_path)
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(stdout=b'historical plan\r\n')
    monkeypatch.setattr(checker.subprocess, 'run', run)
    sha = 'a' * 40
    assert checker.source_bytes(dict(path='plan.md', git_commit=sha)) == b'historical plan\n'
    assert calls == [['git', 'show', sha + ':plan.md']]
    assert checker.source_bytes(dict(path='plan.md')) == b'changed current plan\n'


def test_mutable_ref_is_not_a_historical_revision():
    with pytest.raises(ValueError, match='full SHA'):
        checker.source_bytes(dict(path='plan.md', git_commit='origin/main'))
