"""Receive frames the ESP32-CAM sends over UDP (raw RGB565 from esp32/raw_udp, or JPEG from esp32/jpeg_udp, detected automatically; it finds this laptop by itself), reassemble, decode, and report per second:
completed fps, lost frames, Mbit/s, spread (first to last packet of a frame), decode time, relative latency.
Latency without synchronised clocks: (laptop receive time - ESP32 timestamp) minus the smallest value seen, so it shows delay above the best case.
The real round trip time is printed by the ESP32 itself (serial). Allow python through the Windows firewall for UDP (Private networks).

    python -m tools.esp_raw_rx --seconds 40 --save reports/DoanQuocKien/week-01/camera
"""
import argparse
import socket
import struct
import time
from pathlib import Path

import numpy as np

HDR = struct.Struct("<2sBBIIHH")
SIZES = {153600: (240, 320), 38400: (120, 160), 614400: (480, 640)}  # frame bytes -> (h, w), RGB565


def rgb565_to_bgr(buf, h, w):
    v = np.frombuffer(buf, dtype=">u2").reshape(h, w)  # the camera sends the high byte first
    r = ((v >> 11) & 31) << 3
    g = ((v >> 5) & 63) << 2
    b = (v & 31) << 3
    return np.dstack([b, g, r]).astype(np.uint8)


def new_stats():
    return dict(ok=0, lost=0, bytes=0, spread=[], dec=[], lat=[], size=[], res="-")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5600)
    ap.add_argument("--seconds", type=float, default=40)
    ap.add_argument("--save", default="", help="folder for one decoded still per phase")
    a = ap.parse_args()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 << 20)
    sock.bind(("0.0.0.0", a.port))
    sock.settimeout(0.2)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    # the ESP32 has no configured IP: announce ourselves once a second and it sends to whoever announced
    # ponytail: assumes a /24 on every local address; use the real netmask if a network is not /24
    targets = ["255.255.255.255"] + [ip.rsplit(".", 1)[0] + ".255" for ip in socket.gethostbyname_ex(socket.gethostname())[2]]
    t_hello = 0.0
    frames, done = {}, set()
    best = None  # smallest (receive time - ESP32 timestamp) seen = the clock offset plus the best-case delay
    st = new_stats()
    cur_phase, last_save = -1, 0.0
    t0 = time.perf_counter()
    t_end, t_rep = t0 + a.seconds, t0 + 1
    print("listening on UDP %d for %.0f s ..." % (a.port, a.seconds))
    while time.perf_counter() < t_end:
        try:
            data, src = sock.recvfrom(2048)
        except socket.timeout:
            data = None
        now = time.perf_counter()
        if now >= t_hello:
            for t in targets:
                try:
                    sock.sendto(b"HELO", (t, a.port + 1))
                except OSError:
                    pass
            t_hello = now + 1
        if data and len(data) > HDR.size:
            magic, phase, _, fid, esp_ms, idx, cnt = HDR.unpack_from(data)
            if magic == b"SC":
                if phase != cur_phase:
                    cur_phase = phase
                    frames.clear()
                    print("--- phase %d ---" % phase)
                fr = frames.setdefault(fid, dict(parts={}, first=now, esp=esp_ms, src=src))
                fr["parts"][idx] = data[HDR.size:]
                st["bytes"] += len(data)
                if len(fr["parts"]) == cnt and fid not in done:
                    done.add(fid)
                    sock.sendto(b"ACK " + struct.pack("<II", fid, fr["esp"]), fr["src"])
                    rel = (now - t0) * 1000 - fr["esp"]
                    best = rel if best is None else min(best, rel)
                    raw = b"".join(fr["parts"][i] for i in range(cnt))
                    img = None
                    if raw[:2] == b"\xff\xd8":  # a JPEG frame (esp32/jpeg_udp)
                        import cv2
                        t1 = time.perf_counter()
                        img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
                        st["dec"].append((time.perf_counter() - t1) * 1000)
                    elif len(raw) in SIZES:
                        t1 = time.perf_counter()
                        img = rgb565_to_bgr(raw, *SIZES[len(raw)])
                        st["dec"].append((time.perf_counter() - t1) * 1000)
                    if img is not None:
                        st["size"].append(len(raw))
                        st["res"] = "%dx%d" % (img.shape[1], img.shape[0])
                        if a.save and now - last_save >= 3:  # refresh the still every 3 s, so it ends up a recent frame
                            import cv2
                            Path(a.save).mkdir(parents=True, exist_ok=True)
                            cv2.imwrite(str(Path(a.save) / ("gc2145_latest.png")), img)
                            last_save = now
                    st["ok"] += 1
                    st["spread"].append((now - fr["first"]) * 1000)
                    st["lat"].append(rel - best)
                    frames.pop(fid, None)
        for fid in [k for k, v in frames.items() if now - v["first"] > 0.5]:  # never completed: lost
            frames.pop(fid)
            st["lost"] += 1
        if now >= t_rep:
            n = max(len(st["spread"]), 1)
            lat = sorted(st["lat"]) or [0]
            print("%s %5.1f fps ok | lost %2d | %5.1f Mbit/s | spread avg %5.1f ms | decode avg %4.1f ms | rel latency p50 %5.1f p95 %5.1f ms | %6.0f B/frame" % (
                st["res"], st["ok"], st["lost"], st["bytes"] * 8 / 1e6, sum(st["spread"]) / n,
                sum(st["dec"]) / max(len(st["dec"]), 1), lat[len(lat) // 2], lat[min(int(len(lat) * 0.95), len(lat) - 1)], sum(st["size"]) / max(len(st["size"]), 1)))
            st = new_stats()
            t_rep += 1


if __name__ == "__main__":
    main()
