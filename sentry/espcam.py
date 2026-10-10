"""Laptop side of the ESP32-CAM stream (firmware: esp32/tile_stream, protocol and measurements: docs/ESP32-CAM.md).

The GC2145 camera has no hardware JPEG, so the ESP32 sends a raw Bayer 640x480 picture as small changed tiles (64x32, JPEG-coded, four colour planes per tile).
TileReceiver keeps the full picture, demosaics it and white-balances it; latest() returns a normal BGR frame for the rest of the pipeline.

    rx = TileReceiver()          # announces itself by broadcast; the ESP32 finds the laptop by itself
    rx.start()
    frame, frame_id, age_s = rx.latest()
"""
import socket
import struct
import threading
import time

import cv2
import numpy as np

W, H, TW, TH = 640, 480, 64, 32
TILES_X = W // TW
HDR = struct.Struct("<2sBBIIHH")  # 'S' 'T' type flags frame_id esp_ms a b
T_TILE, T_HDR, T_END, T_FULL, T_TILES = 0, 1, 2, 3, 4
PORT = 5600


# Change detector, a Python mirror of esp32/tile_stream/tile_stream.ino (sampleTile / tileDirty); tests/test_tile_detect.py checks its properties and tools/esp_tile_sim.py uses it.
MEAN_THR, OUT_DIFF, OUT_COUNT = 16, 48, 8


def fingerprint(tile):
    """8 rows (every 4th) x four 4-byte pieces at columns 4, 20, 36, 52 of a 64x32 tile -> 8 x 16 samples."""
    rows = tile[0:32:4]
    return np.concatenate([rows[:, 4 + 16 * s:8 + 16 * s] for s in range(4)], axis=1).astype(np.int32)


def tile_dirty(now, old):
    """Changed when the mean difference of the fingerprints is large, or enough single samples differ strongly (a thin edge covering part of the tile)."""
    d = np.abs(fingerprint(now) - fingerprint(old))
    return bool(d.mean() >= MEAN_THR or (d >= OUT_DIFF).sum() >= OUT_COUNT)


def unplanar(t):
    """The firmware sends each Bayer tile as four colour planes in the quadrants of a 64x32 image (R, G1, G2, B, each 32x16); put it back."""
    out = np.empty((TH, TW), np.uint8)
    out[0::2, 0::2] = t[0:16, 0:32]
    out[0::2, 1::2] = t[0:16, 32:64]
    out[1::2, 0::2] = t[16:32, 0:32]
    out[1::2, 1::2] = t[16:32, 32:64]
    return out


def planar(tile):
    """Inverse of unplanar (what the firmware does); used by the tests."""
    out = np.empty((TH, TW), np.uint8)
    out[0:16, 0:32] = tile[0::2, 0::2]
    out[0:16, 32:64] = tile[0::2, 1::2]
    out[16:32, 0:32] = tile[1::2, 0::2]
    out[16:32, 32:64] = tile[1::2, 1::2]
    return out


def gray_world_gains(bgr, limit=(0.4, 3.0)):
    """Per-channel gains that make the picture's average grey, normalised to the green channel. Pixels that are nearly black or saturated are ignored."""
    px = bgr.reshape(-1, 3).astype(np.float32)
    keep = (px.min(axis=1) > 12) & (px.max(axis=1) < 243)
    if keep.sum() < 500:
        return np.ones(3, np.float32)
    m = px[keep].mean(axis=0)
    return np.clip(m[1] / np.maximum(m, 1.0), *limit).astype(np.float32)


def gamma_lut(gamma):
    return (255.0 * (np.arange(256) / 255.0) ** (1.0 / gamma)).astype(np.uint8)


class TileReceiver:
    """Receives the tile stream, maintains the picture. Thread-based; start() / stop(). wb: 'gray' (gray-world, smoothed over time) or 'none'."""

    def __init__(self, port=PORT, pattern="BG", wb="gray", gamma=1.0, wb_smooth=0.05):
        self.port, self.wb, self.wb_smooth = port, wb, wb_smooth
        self.code = getattr(cv2, "COLOR_BAYER_%s2BGR" % pattern)
        self.lut = gamma_lut(gamma) if gamma != 1.0 else None
        self.raw = np.full((H, W), 128, np.uint8)
        self.gains = np.ones(3, np.float32)
        self._wb_init = False
        self.header = None
        self.frames = self.tiles = self.missing = self.bytes = 0
        self.last_frame_id, self.last_t = -1, 0.0
        self._got = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._sock = None

    # -- picture ------------------------------------------------------------------------------------------------------------------
    def latest(self):
        """(BGR frame, frame id, seconds since it was completed); frame is None until the first tiles arrived."""
        with self._lock:
            if self.header is None:
                return None, -1, float("inf")
            bgr = cv2.cvtColor(self.raw, self.code)
            fid, t = self.last_frame_id, self.last_t
        if self.wb == "gray":
            g = gray_world_gains(bgr[::4, ::4])
            self.gains = g if not self._wb_init else (1 - self.wb_smooth) * self.gains + self.wb_smooth * g  # the first measurement is taken as is
            self._wb_init = True
        if self.wb != "none":
            bgr = np.clip(bgr.astype(np.float32) * self.gains, 0, 255).astype(np.uint8)
        if self.lut is not None:
            bgr = self.lut[bgr]
        return bgr, fid, time.perf_counter() - t

    def _paste(self, idx, jpg):
        tile = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_GRAYSCALE)
        if tile is None or tile.shape != (TH, TW) or idx >= TILES_X * (H // TH):
            return False
        x, y = (idx % TILES_X) * TW, (idx // TILES_X) * TH
        with self._lock:
            self.raw[y:y + TH, x:x + TW] = unplanar(tile)
        return True

    # -- packets ------------------------------------------------------------------------------------------------------------------
    def handle(self, data, src=None, sock=None):
        """Process one UDP packet (public so tests can feed packets)."""
        if len(data) < HDR.size:
            return
        magic, typ, _, fid, esp_ms, p1, p2 = HDR.unpack_from(data)
        if magic != b"ST":
            return
        payload = data[HDR.size:]
        self.bytes += len(data)
        if typ == T_HDR:
            self.header = payload[:p1]
        elif typ == T_TILES and self.header:  # p1 tiles: [index u16][length u16][scan data] ...
            pos = 0
            for _ in range(p1):
                if pos + 4 > len(payload):
                    break
                idx, ln = struct.unpack_from("<HH", payload, pos)
                pos += 4
                if self._paste(idx, self.header + payload[pos:pos + ln]):
                    self._got[fid] = self._got.get(fid, 0) + 1
                    self.tiles += 1
                pos += ln
        elif typ == T_TILE and self.header:
            if self._paste(p1, self.header + payload):
                self._got[fid] = self._got.get(fid, 0) + 1
                self.tiles += 1
        elif typ == T_FULL:
            if self._paste(p1, payload):
                self._got[fid] = self._got.get(fid, 0) + 1
                self.tiles += 1
        elif typ == T_END:
            self.frames += 1
            self.missing += max(0, p1 - self._got.pop(fid, 0))
            for k in [k for k in self._got if k < fid - 50]:
                self._got.pop(k)
            self.last_frame_id, self.last_t = fid, time.perf_counter()
            if sock is not None and src is not None:
                sock.sendto(b"ACK " + struct.pack("<II", fid, esp_ms), src)  # lets the ESP32 measure its round trip

    # -- thread -------------------------------------------------------------------------------------------------------------------
    def _run(self):
        sock = self._sock
        # ponytail: assumes a /24 on every local address; use the real netmask if a network is not /24
        targets = ["255.255.255.255"] + [ip.rsplit(".", 1)[0] + ".255" for ip in socket.gethostbyname_ex(socket.gethostname())[2]]
        t_hello, t_start = 0.0, time.perf_counter()
        while not self._stop.is_set():
            now = time.perf_counter()
            if now >= t_hello:  # the ESP32 sends to whoever announced
                for t in targets:
                    try:
                        sock.sendto(b"HELO", (t, self.port + 1))
                        if now - t_start < 3:  # just started: ask for a complete picture (repeated, UDP can lose it)
                            sock.sendto(b"REFR", (t, self.port + 1))
                    except OSError:
                        pass
                t_hello = now + 1
            try:
                data, src = sock.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                break
            self.handle(data, src, sock)

    def start(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 << 20)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.bind(("0.0.0.0", self.port))
        s.settimeout(0.1)
        self._sock = s
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)
        if self._sock:
            self._sock.close()
