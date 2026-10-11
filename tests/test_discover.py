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
    monkeypatch.setattr(discover, "_found", {})
    monkeypatch.setattr(discover, "_http81", lambda ip: ip == "127.0.0.1")
    monkeypatch.setattr(discover, "_candidates", lambda: pytest.fail("scanned the LAN"))
    assert discover.find_esp32() == "127.0.0.1"


def test_esp32_lan_scan(monkeypatch):
    monkeypatch.setattr(discover, "_found", {})
    monkeypatch.setattr(discover, "_http81", lambda ip: ip == "10.0.0.5")
    monkeypatch.setattr(discover, "_candidates", lambda: ["10.0.0.4", "10.0.0.5"])
    assert discover.find_esp32() == "10.0.0.5"


def test_esp32_missing_exits(monkeypatch):
    monkeypatch.setattr(discover, "find_esp32", lambda: None)
    with pytest.raises(SystemExit):
        discover.resolve_esp32("auto")


def test_a_failed_scan_is_retried_and_a_hit_is_remembered(monkeypatch):
    monkeypatch.setattr(discover, "_found", {})
    monkeypatch.setattr(discover, "_candidates", lambda: ["10.0.0.4"])
    up = []
    monkeypatch.setattr(discover, "_probe", lambda ip: "video" if up else None)
    assert discover.find() is None          # robot still booting
    up.append(1)
    assert discover.find() == "10.0.0.4"    # the next call scans again
    monkeypatch.setattr(discover, "_candidates", lambda: pytest.fail("scanned again"))
    assert discover.find() == "10.0.0.4"


def test_candidates_skip_loopback_link_local_and_self(monkeypatch):
    monkeypatch.setattr(discover.socket, "gethostbyname_ex", lambda h: (h, [], ["127.0.1.1", "169.254.3.4", "192.168.137.1"]))
    cand = discover._candidates()
    assert len(cand) == 253 and "192.168.137.1" not in cand and all(c.startswith("192.168.137.") for c in cand)
    monkeypatch.setattr(discover.socket, "gethostbyname_ex", lambda h: (_ for _ in ()).throw(OSError("no name")))
    assert discover._candidates() == []
