"""A fake ESP32-CAM: sends the tile stream (docs/ESP32-CAM.md) of a synthetic moving scene to the laptop, so sentry.espcam.TileReceiver, tools/esp_mjpeg_relay.py and
tools/record.py can be developed and tested without the board.

    python -m tools.esp_tile_sim --seconds 30 --fps 15 [--host 127.0.0.1]
It answers REFR (resend all tiles) like the firmware and sends the JPEG header once a second.
"""
import argparse
import socket
import struct
import time

import cv2
import numpy as np

from sentry.espcam import HDR, H, T_END, T_HDR, T_TILES, TH, TILES_X, TW, W, planar

NT = TILES_X * (H // TH)


def scene(t):
    """Raw Bayer (BG) image: a gradient background and a bright square that moves."""
    yy, xx = np.mgrid[0:H, 0:W]
    img = (40 + xx // 6 + yy // 8).astype(np.uint8)
    cx = int(60 + (W - 160) * (0.5 + 0.5 * np.sin(t)))
    img[200:280, cx:cx + 80] = 235
    return img


def jpeg_parts(tile):
    j = cv2.imencode(".jpg", planar(tile), [cv2.IMWRITE_JPEG_QUALITY, 80])[1].tobytes()
    i = j.index(b"\xff\xda")
    he = i + 2 + ((j[i + 2] << 8) | j[i + 3])
    return j[:he], j[he:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5600)
    ap.add_argument("--fps", type=float, default=15)
    ap.add_argument("--seconds", type=float, default=30)
    a = ap.parse_args()
    tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx.bind(("0.0.0.0", a.port + 1))
    rx.settimeout(0.001)
    prev = np.zeros((H, W), np.uint8)
    header, t_hdr, fid, t0 = None, 0.0, 0, time.perf_counter()
    while time.perf_counter() - t0 < a.seconds:
        t_frame = time.perf_counter()
        try:
            while True:
                d, _ = rx.recvfrom(64)
                if d.startswith(b"REFR"):
                    prev[:] = 0xFF  # everything counts as changed again
        except socket.timeout:
            pass
        cur = scene(t_frame - t0)
        ms = int((t_frame - t0) * 1000) & 0xFFFFFFFF
        entries, sent = [], 0
        for idx in range(NT):
            y, x = (idx // TILES_X) * TH, (idx % TILES_X) * TW
            c, p = cur[y:y + TH, x:x + TW], prev[y:y + TH, x:x + TW]
            if np.abs(c.astype(int) - p.astype(int)).mean() >= 16:
                hdr, scan = jpeg_parts(c)
                header = header or hdr
                entries.append((idx, scan))
                prev[y:y + TH, x:x + TW] = c
        if header and time.perf_counter() - t_hdr > 1:
            tx.sendto(HDR.pack(b"ST", T_HDR, 0, fid, ms, len(header), 0) + header, (a.host, a.port))
            t_hdr = time.perf_counter()
        pkt = b""
        n = 0
        for idx, scan in entries + [(None, None)]:
            blob = b"" if idx is None else struct.pack("<HH", idx, len(scan)) + scan
            if n and (idx is None or len(pkt) + len(blob) > 1400):
                tx.sendto(HDR.pack(b"ST", T_TILES, 0, fid, ms, n, 0) + pkt, (a.host, a.port))
                sent += n
                pkt, n = b"", 0
            if idx is not None:
                pkt += blob
                n += 1
        tx.sendto(HDR.pack(b"ST", T_END, 0, fid, ms, sent, len(entries)), (a.host, a.port))
        fid += 1
        time.sleep(max(0.0, 1 / a.fps - (time.perf_counter() - t_frame)))
    print("sent %d frames" % fid)


if __name__ == "__main__":
    main()
