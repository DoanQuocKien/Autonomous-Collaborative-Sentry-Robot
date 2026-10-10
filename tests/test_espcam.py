"""T0 tests for the ESP32-CAM tile receiver (sentry/espcam.py): plane shuffle, white balance, and packet handling with synthetic tiles."""
import struct

import cv2
import numpy as np

from sentry import espcam
from sentry.espcam import HDR, T_END, T_HDR, T_TILES, TH, TW, TileReceiver, gray_world_gains, planar, unplanar


def _jpeg_parts(img):
    """(header, scan data) of a grayscale JPEG: the split the firmware makes (header = everything up to the end of the SOS header)."""
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    j = buf.tobytes()
    i = j.index(b"\xff\xda")
    he = i + 2 + ((j[i + 2] << 8) | j[i + 3])
    return j[:he], j[he:]


def _pkt(typ, fid, a, b, payload=b""):
    return HDR.pack(b"ST", typ, 0, fid, 0, a, b) + payload


def test_planar_roundtrip():
    t = np.random.default_rng(1).integers(0, 256, (TH, TW), dtype=np.uint8)
    assert np.array_equal(unplanar(planar(t)), t)


def test_gray_world_removes_a_colour_cast():
    rng = np.random.default_rng(2)
    base = rng.integers(60, 200, (120, 160, 1), dtype=np.uint8).repeat(3, axis=2).astype(np.float32)
    tinted = np.clip(base * np.array([1.5, 1.0, 0.7], np.float32), 0, 255).astype(np.uint8)  # B, G, R
    g = gray_world_gains(tinted)
    fixed = np.clip(tinted.astype(np.float32) * g, 0, 255)
    means = fixed.reshape(-1, 3).mean(axis=0)
    assert means.max() - means.min() < 6
    assert abs(g[1] - 1.0) < 1e-6  # normalised to green


def test_gray_world_ignores_a_black_picture():
    assert np.array_equal(gray_world_gains(np.zeros((40, 40, 3), np.uint8)), np.ones(3, np.float32))


def test_receiver_assembles_tiles_and_counts_missing():
    rng = np.random.default_rng(3)
    tiles = []
    for _ in range(2):
        yy, xx = np.mgrid[0:TH, 0:TW]
        tiles.append(np.clip(40 + 3 * yy + 2 * xx + rng.integers(-5, 5, (TH, TW)), 0, 255).astype(np.uint8))
    parts = [_jpeg_parts(planar(t)) for t in tiles]
    header = parts[0][0]
    assert all(p[0] == header for p in parts)  # the firmware relies on one shared header
    payload = b"".join(struct.pack("<HH", idx, len(scan)) + scan for idx, (h, scan) in zip((0, 11), parts))
    rx = TileReceiver(wb="none")
    rx.handle(_pkt(T_HDR, 1, len(header), 0, header))
    rx.handle(_pkt(T_TILES, 1, 2, 0, payload))
    rx.handle(_pkt(T_END, 1, 3, 3))  # the firmware says it sent 3 tiles; only 2 arrived
    assert rx.frames == 1 and rx.tiles == 2 and rx.missing == 1
    # tile 0 is at (0, 0), tile 11 at column 1, row 1 (10 tiles per row)
    got0 = rx.raw[0:TH, 0:TW]
    got11 = rx.raw[TH:2 * TH, TW:2 * TW]
    assert np.abs(got0.astype(int) - tiles[0]).mean() < 4
    assert np.abs(got11.astype(int) - tiles[1]).mean() < 4
    frame, fid, age = rx.latest()
    assert frame.shape == (espcam.H, espcam.W, 3) and fid == 1 and age < 5


def test_packets_before_the_header_and_garbage_are_ignored():
    rx = TileReceiver(wb="none")
    rx.handle(b"short")
    rx.handle(b"XX" + bytes(30))
    rx.handle(_pkt(T_TILES, 1, 1, 0, struct.pack("<HH", 0, 4) + b"abcd"))  # no header yet
    assert rx.tiles == 0 and rx.latest()[0] is None
