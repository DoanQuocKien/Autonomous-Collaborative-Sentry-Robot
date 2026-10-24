"""T0 tests for the Python 3.6 robot variant of the ESP32 tile receiver (jetson/espcam.py) on recorded tile streams."""
import ast
import os
from pathlib import Path
import struct
import sys

import cv2
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "jetson"))

import espcam as jetson_espcam  # noqa: E402
from sentry import espcam as laptop_espcam  # noqa: E402


def _synthetic_scene(step):
    """640x480 raw Bayer BG scene with a moving bright doorway-like rectangle."""
    yy, xx = np.mgrid[0:jetson_espcam.H, 0:jetson_espcam.W]
    img = (45 + xx // 7 + yy // 9).astype(np.uint8)
    x0 = 80 + (step * 48) % 360
    img[120:360, x0:x0 + 96] = 230
    return img


def test_jetson_espcam_is_python36_compatible_and_does_not_import_sentry():
    path = ROOT / "jetson" / "espcam.py"
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(path), feature_version=(3, 6))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("sentry"), "jetson/espcam.py must not import sentry"
                assert alias.name != "dataclasses"
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            assert not mod.startswith("sentry"), "jetson/espcam.py must not import from sentry"
            assert mod not in ("dataclasses", "__future__")


def test_recorded_tile_stream_roundtrip_and_parity_with_laptop_receiver(tmp_path):
    all_packets = []
    prev, last_sent = None, None
    scenes = [_synthetic_scene(i) for i in range(5)]

    for fid, bayer in enumerate(scenes):
        pkts, prev, last_sent = jetson_espcam.encode_frame_packets(
            bayer,
            prev=prev,
            fid=fid,
            esp_ms=fid * 66,
            quality=90,
            include_header=(fid == 0),
            last_sent=last_sent,
        )
        all_packets.extend(pkts)

    rec_path = tmp_path / "door_tiles.strec"
    jetson_espcam.dump_tile_stream(rec_path, all_packets)
    loaded = jetson_espcam.load_tile_stream(rec_path)
    assert loaded == all_packets

    # Replay through jetson.espcam.TileReceiver and compare frame-by-frame with sentry.espcam.TileReceiver
    j_frames, j_rx = jetson_espcam.replay_tile_stream(rec_path, wb="gray", gamma=1.1)
    l_rx = laptop_espcam.TileReceiver(wb="gray", gamma=1.1)
    l_frames = []
    prev_ver = l_rx.version
    for pkt in loaded:
        l_rx.handle(pkt)
        if l_rx.version != prev_ver:
            prev_ver = l_rx.version
            bgr, fid, _ = l_rx.latest()
            l_frames.append((fid, bgr.copy()))

    assert len(j_frames) == 5 and len(l_frames) == 5
    assert j_rx.frames == 5 and j_rx.missing == 0 and j_rx.tiles > 150
    for (j_fid, j_bgr), (l_fid, l_bgr) in zip(j_frames, l_frames):
        assert j_fid == l_fid
        assert j_bgr.shape == (480, 640, 3)
        assert np.array_equal(j_bgr, l_bgr)


def test_legacy_single_tile_full_tile_and_ack_reply(tmp_path):
    rx = jetson_espcam.TileReceiver(wb="none")
    tile_raw = np.full((jetson_espcam.TH, jetson_espcam.TW), 180, np.uint8)
    hdr, scan = jetson_espcam._jpeg_parts(tile_raw, quality=95)
    full_jpg = hdr + scan

    sent_acks = []

    class DummySock(object):
        def sendto(self, data, addr):
            sent_acks.append((data, addr))

    esp_addr = ("192.168.137.42", 5601)
    rx.handle(jetson_espcam.HDR.pack(b"ST", jetson_espcam.T_HDR, 0, 10, 500, len(hdr), 0) + hdr, esp_addr)
    rx.handle(jetson_espcam.HDR.pack(b"ST", jetson_espcam.T_TILE, 0, 10, 500, 0, 0) + scan, esp_addr)
    rx.handle(jetson_espcam.HDR.pack(b"ST", jetson_espcam.T_FULL, 0, 10, 500, 1, 0) + full_jpg, esp_addr)
    rx.handle(jetson_espcam.HDR.pack(b"ST", jetson_espcam.T_END, 0, 10, 500, 2, 2), esp_addr, DummySock())

    bgr, fid, age = rx.latest()
    assert fid == 10 and rx.tiles == 2 and rx.missing == 0 and age >= 0.0
    assert bgr[0:32, 0:128].mean() > 160
    assert sent_acks == [(b"ACK " + struct.pack("<II", 10, 500), esp_addr)]

    # Truncated or bad recording file raises ValueError
    bad_path = tmp_path / "bad.strec"
    bad_path.write_bytes(b"NOT_STREC")
    with pytest.raises(ValueError):
        jetson_espcam.load_tile_stream(bad_path)


def test_broadcast_targets_always_includes_limited_broadcast():
    targets = jetson_espcam.broadcast_targets()
    assert "255.255.255.255" in targets
    assert all(t.endswith(".255") for t in targets)
