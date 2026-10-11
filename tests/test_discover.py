import pytest

from sentry.net import discover


def test_fixed_ip_is_not_scanned(monkeypatch):
    monkeypatch.setattr(discover, "find", lambda: pytest.fail("scanned"))
    assert discover.resolve("10.0.0.7") == "10.0.0.7"


def test_auto_uses_the_scan(monkeypatch):
    monkeypatch.setattr(discover, "find", lambda: "10.0.0.9")
    assert discover.resolve("auto") == "10.0.0.9"


def test_auto_without_robot_exits(monkeypatch):
    monkeypatch.setattr(discover, "find", lambda: None)
    with pytest.raises(SystemExit):
        discover.resolve("auto")
