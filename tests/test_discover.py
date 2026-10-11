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


def test_esp32_fixed_ip_is_not_scanned(monkeypatch):
    monkeypatch.setattr(discover, "find_esp32", lambda: pytest.fail("scanned"))
    assert discover.resolve_esp32("10.0.0.5") == "10.0.0.5"


def test_esp32_auto_uses_the_scan(monkeypatch):
    monkeypatch.setattr(discover, "find_esp32", lambda: "10.0.0.5")
    assert discover.resolve_esp32("auto") == "10.0.0.5"


def test_esp32_prefers_local_relay(monkeypatch):
    discover.find_esp32.cache_clear()
    monkeypatch.setattr(discover, "_http81", lambda ip: ip == "127.0.0.1")
    monkeypatch.setattr(discover, "_candidates", lambda: pytest.fail("scanned the LAN"))
    assert discover.find_esp32() == "127.0.0.1"
    discover.find_esp32.cache_clear()


def test_esp32_lan_scan(monkeypatch):
    discover.find_esp32.cache_clear()
    monkeypatch.setattr(discover, "_http81", lambda ip: ip == "10.0.0.5")
    monkeypatch.setattr(discover, "_candidates", lambda: ["10.0.0.4", "10.0.0.5"])
    assert discover.find_esp32() == "10.0.0.5"
    discover.find_esp32.cache_clear()


def test_esp32_missing_exits(monkeypatch):
    monkeypatch.setattr(discover, "find_esp32", lambda: None)
    with pytest.raises(SystemExit):
        discover.resolve_esp32("auto")
