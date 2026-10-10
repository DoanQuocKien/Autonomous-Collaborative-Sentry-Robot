"""Find the JetBot on the laptop's current network (the hotspot hands out a new IP after every restart).

    python -m tools.find_jetbot            # prints the IP
resolve(ip) returns ip unchanged unless it is "" / "auto", so config.toml can say jetbot_ip = "auto".
"""
import socket
from concurrent.futures import ThreadPoolExecutor


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


def find(verbose=False):
    # ponytail: assumes a /24 on every local address (same as sentry/espcam.py); several matching hosts -> first, camera publisher preferred
    mine = socket.gethostbyname_ex(socket.gethostname())[2]
    cand = [p.rsplit(".", 1)[0] + "." + str(i) for p in mine if not p.startswith("127.") for i in range(1, 255) if p.rsplit(".", 1)[0] + "." + str(i) not in mine]
    with ThreadPoolExecutor(128) as ex:
        hits = [(ip, k) for ip, k in zip(cand, ex.map(_probe, cand)) if k]
    hits.sort(key=lambda h: h[1] != "video")
    if verbose:
        print(hits)
    return hits[0][0] if hits else None


def resolve(ip):
    if ip and ip != "auto":
        return ip
    found = find()
    if not found:
        raise SystemExit("JetBot not found on this network (is it on the same hotspot? give the IP explicitly)")
    print("JetBot found at", found)
    return found


if __name__ == "__main__":
    print(resolve("auto"))
