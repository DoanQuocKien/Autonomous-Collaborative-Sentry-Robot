import json
import sys

import pytest

from tools import session_run


def test_newest_summary_picks_the_latest_run_of_a_label(tmp_path):
    for n, ok in ((1, False), (2, True)):
        d = tmp_path / ("take_a_%d" % n)
        d.mkdir()
        (d / "summary.json").write_text(json.dumps({"success": ok}))
        import os, time
        os.utime(d, (time.time() + n, time.time() + n))
    assert session_run.newest_summary(tmp_path, "take_a")["success"] is True
    assert session_run.newest_summary(tmp_path, "other") is None


@pytest.mark.parametrize('new_results', [[], [False], [True, True]])
def test_session_never_uses_old_or_ambiguous_success(monkeypatch, tmp_path, new_results):
    monkeypatch.chdir(tmp_path)
    old = tmp_path / 'data/deploy/take_a_1'
    old.mkdir(parents=True)
    (old / 'summary.json').write_text(json.dumps({'success': True}))
    calls = []

    def call(command):
        calls.append(command)
        for n, success in enumerate(new_results, 2):
            run = old.parent / ('take_a_' + str(n))
            run.mkdir()
            (run / 'summary.json').write_text(json.dumps({'success': success}))
        return 0

    monkeypatch.setattr(sys, 'argv', ['session_run', '--label', 'take', '--camera-pose', 'pose.json'])
    monkeypatch.setattr(session_run.subprocess, 'call', call)
    monkeypatch.setattr(session_run, 'wait_key', lambda prompt: 'p')
    with pytest.raises(SystemExit, match='did not reach STANDBY'):
        session_run.main()
    assert len(calls) == 1


@pytest.mark.parametrize('success', [False, True])
def test_session_uses_forwarded_output_and_label(monkeypatch, tmp_path, success):
    monkeypatch.chdir(tmp_path)
    output = tmp_path / 'custom-output'
    calls = []

    def call(command):
        calls.append(command)
        if len(calls) == 1:
            run = output / 'actual_1'
            run.mkdir(parents=True)
            (run / 'summary.json').write_text(json.dumps({'success': success}))
        return 0

    monkeypatch.setattr(sys, 'argv', ['session_run', '--label', 'take', '--camera-pose', 'pose.json',
                                    '--', '--out', str(output), '--label', 'actual'])
    monkeypatch.setattr(session_run.subprocess, 'call', call)
    monkeypatch.setattr(session_run, 'wait_key', lambda prompt: 'p')
    with pytest.raises(SystemExit) as exc:
        session_run.main()
    if success:
        assert exc.value.code == 0
    else:
        assert 'did not reach STANDBY' in str(exc.value)
    assert len(calls) == (2 if success else 1)
