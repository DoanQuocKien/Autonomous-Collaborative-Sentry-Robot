"""Find the JetBot and the ESP32-CAM on the laptop's current network (the hotspot hands out a new IP after every restart).

resolve(ip) / resolve_esp32(ip) return ip unchanged unless it is "" / "auto", so config.toml can say jetbot_ip = "auto". Each scan runs once per process.
"""
import socket
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache


def _probe(ip):
    """'video' if the camera publisher answers (ZMQ 5555), 'ssh' if an Ubuntu 18.04 OpenSSH banner (the Jetson image) answers, else None."""
    for port, kind in ((5555, "video"), (22, "ssh")):
        try:
            with socket.create_connection((ip, port), timeout=0.4) as s:
                if kind == "video":
                    return kind
                s.settimeout(0.5)
                if b"OpenSSH_7.6p1 Ubuntu" in s.recv(100):
                    return kind
        except OSError:
            pass


def _candidates():
    # ponytail: assumes a /24 on every local address (same as sentry/espcam.py)
    mine = socket.gethostbyname_ex(socket.gethostname())[2]
    return [p.rsplit(".", 1)[0] + "." + str(i) for p in mine if not p.startswith("127.") for i in range(1, 255) if p.rsplit(".", 1)[0] + "." + str(i) not in mine]


def _http81(ip):
    """True if something listens on port 81 (the OV2640 stock sketch streams MJPEG there; so does tools/esp_mjpeg_relay.py)."""
    try:
        with socket.create_connection((ip, 81), timeout=0.4):
            return True
    except OSError:
        return False


@lru_cache(maxsize=1)
def find(verbose=False):
    # several matching hosts -> first, camera publisher preferred
    cand = _candidates()
    with ThreadPoolExecutor(128) as ex:
        hits = [(ip, k) for ip, k in zip(cand, ex.map(_probe, cand)) if k]
    hits.sort(key=lambda h: h[1] != "video")
    if verbose:
        print(hits)
    return hits[0][0] if hits else None


@lru_cache(maxsize=1)
def find_esp32():
    """127.0.0.1 if tools/esp_mjpeg_relay.py is running here (GC2145 boards), else the first LAN host with port 81 open (OV2640 board)."""
    if _http81("127.0.0.1"):
        return "127.0.0.1"
    cand = _candidates()
    with ThreadPoolExecutor(128) as ex:
        hits = [ip for ip, ok in zip(cand, ex.map(_http81, cand)) if ok]
    return hits[0] if hits else None


def resolve(ip):
    if ip and ip != "auto":
        return ip
    found = find()
    if not found:
        raise SystemExit("JetBot not found on this network (is it on the same hotspot? give the IP explicitly)")
    print("JetBot found at", found)
    return found


def resolve_esp32(ip):
    if ip and ip != "auto":
        return ip
    found = find_esp32()
    if not found:
        raise SystemExit("ESP32-CAM not found (start tools/esp_mjpeg_relay.py for a GC2145 board, or check the OV2640 board is on the hotspot; or give its IP)")
    print("ESP32-CAM stream at", found)
    return found

