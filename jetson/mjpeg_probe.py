"""How fast does the ESP32-CAM OV2640 stream reach THIS machine? Python 3.6, stdlib only (cv2/numpy only with --decode).

    python3 jetson/mjpeg_probe.py http://10.195.93.9:81/stream --seconds 20 [--decode]

Reads the HTTP body with plain recv_into (no urllib, no per-chunk Python parsing beyond counting JPEG start markers), counts frames and bytes, and prints
one line per second plus a summary (frames/s, kB/s, longest gap between frames). With --decode every frame is also decoded with cv2 (the cost of the bench's reader).
Run it on the Jetson with the bench idle, then under load, then on the laptop: the difference says whether the radio, the CPU or the reader is the limit.
"""
import argparse
import socket
import time
from urllib.parse import urlsplit


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url")
    ap.add_argument("--seconds", type=float, default=20)
    ap.add_argument("--decode", action="store_true", help="also cv2.imdecode every frame")
    ap.add_argument("--rcvbuf", type=int, default=0, help="SO_RCVBUF in bytes (0 = system default)")
    a = ap.parse_args()
    u = urlsplit(a.url)
    s = socket.create_connection((u.hostname, u.port or 80), timeout=10)
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    if a.rcvbuf:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, a.rcvbuf)
    s.sendall(("GET %s HTTP/1.1\r\nHost: %s\r\nConnection: close\r\n\r\n" % (u.path or "/", u.netloc)).encode())
    if a.decode:
        import cv2
        import numpy as np
    buf = bytearray()
    tmp = bytearray(65536)
    mv = memoryview(tmp)
    t0 = last_t = time.time()
    frames = total = sec_frames = sec_bytes = reads = 0
    last_frame_t, gap_max, started = t0, 0.0, False
    while time.time() - t0 < a.seconds:
        n = s.recv_into(tmp)
        if not n:
            print("connection closed by the ESP32")
            break
        reads += 1
        total += n
        sec_bytes += n
        buf += mv[:n]
        while True:
            i = buf.find(b"\xff\xd8")
            j = buf.find(b"\xff\xd9", i + 2) if i >= 0 else -1
            if i < 0 or j < 0:
                if i < 0:
                    del buf[:-1]
                elif i > 0:
                    del buf[:i]
                break
            if a.decode:
                cv2.imdecode(np.frombuffer(bytes(buf[i:j + 2]), np.uint8), cv2.IMREAD_COLOR)
            del buf[:j + 2]
            now = time.time()
            if started:
                gap_max = max(gap_max, now - last_frame_t)
            started, last_frame_t = True, now
            frames += 1
            sec_frames += 1
        if time.time() - last_t >= 1.0:
            print("%5.1fs  %2d frames  %4.0f kB/s" % (time.time() - t0, sec_frames, sec_bytes / 1024.0))
            last_t, sec_frames, sec_bytes = time.time(), 0, 0
    dt = time.time() - t0
    print("SUMMARY %.1f fps, %.0f kB/s, %d frames, %d reads (%.0f B/read), longest gap %.2f s%s" % (
        frames / dt, total / dt / 1024.0, frames, reads, total / max(reads, 1), gap_max, ", with decode" if a.decode else ""))


if __name__ == "__main__":
    main()
