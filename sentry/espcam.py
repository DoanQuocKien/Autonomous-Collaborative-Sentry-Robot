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

from sentry.net.discover import local_ipv4

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


def colour_lut(gains, gamma=None):
    """One 256-entry table per channel (shape 1 x 256 x 3, for cv2.LUT): white-balance gain, clipping and gamma in one lookup."""
    lut = np.clip(np.arange(256, dtype=np.float32)[:, None] * np.asarray(gains, np.float32)[None, :], 0, 255).astype(np.uint8)
    if gamma is not None:
        lut = gamma[lut]
    return lut.reshape(1, 256, 3)


def broadcast_targets():
    """Limited broadcast plus the /24 broadcast of every local address (the Windows hotspot is a /24)."""
    return ["255.255.255.255"] + sorted({ip.rsplit(".", 1)[0] + ".255" for ip in local_ipv4()})


class TileReceiver:
    """Receives the tile stream, maintains the picture. Thread-based; start() / stop(). wb: 'gray' (gray-world, smoothed over time) or 'none'.

    latest() returns the picture as it was at the last frame end (no half-updated frames), processed once per frame and
    shared by every caller. The receiver follows one ESP32: packets from another source are ignored until the current
    one has been silent for SOURCE_QUIET_S (then the next sender is taken, e.g. the board rebooted with a new IP).
    """

    SOURCE_QUIET_S = 5.0
    MAX_PENDING = 64  # frame ids with tiles but no frame end yet; bounded so stray packets cannot grow memory

    def __init__(self, port=PORT, pattern="BG", wb="gray", gamma=1.0, wb_smooth=0.05):
        self.port, self.wb, self.wb_smooth = port, wb, wb_smooth
        self.code = getattr(cv2, "COLOR_BAYER_%s2BGR" % pattern)
        self.lut = gamma_lut(gamma) if gamma != 1.0 else None
        self.raw = np.full((H, W), 128, np.uint8)
        self.complete = None   # copy of raw at the last frame end
        self.version = 0       # frame ends seen; latest() reprocesses only when it changes
        self._cache = (-1, None)
        self._out_lock = threading.Lock()
        self.source, self._source_t = None, 0.0
        self.foreign = 0
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
        """(BGR frame, frame id, seconds since it was completed); frame is None until the first tiles arrived.

        The frame is shared by every caller and read-only: .copy() it before drawing on it. Check age_s: a stalled
        stream keeps returning the last frame with a growing age."""
        with self._out_lock:
            with self._lock:
                if self.header is None:
                    return None, -1, float("inf")
                version, fid, t = self.version, self.last_frame_id, self.last_t
                if self._cache[0] != version or self._cache[1] is None:
                    raw = self.complete if self.complete is not None else self.raw.copy()
                else:
                    raw = None
            if raw is not None:  # a new frame: demosaic, white balance and gamma once, for every caller
                bgr = cv2.cvtColor(raw, self.code)
                if self.wb == "gray":
                    g = gray_world_gains(bgr[::4, ::4])
                    self.gains = g if not self._wb_init else (1 - self.wb_smooth) * self.gains + self.wb_smooth * g  # the first measurement is taken as is
                    self._wb_init = True
                if self.wb != "none":
                    bgr = cv2.LUT(bgr, colour_lut(self.gains, self.lut))
                elif self.lut is not None:
                    bgr = self.lut[bgr]
                bgr.setflags(write=False)  # shared between callers
                self._cache = (version, bgr)
            return self._cache[1], fid, time.perf_counter() - t

    def _paste(self, idx, jpg):
        if idx >= TILES_X * (H // TH):
            return False
        tile = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_GRAYSCALE)
        if tile is None or tile.shape != (TH, TW):
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
        if src is not None:
            now = time.perf_counter()
            if self.source is not None and src[0] != self.source and now - self._source_t < self.SOURCE_QUIET_S:
                self.foreign += 1
                return
            self.source, self._source_t = src[0], now
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
                    self._count(fid)
                pos += ln
        elif typ == T_TILE and self.header:
            if self._paste(p1, self.header + payload):
                self._count(fid)
        elif typ == T_FULL:
            if self._paste(p1, payload):
                self._count(fid)
        elif typ == T_END:
            self.frames += 1
            self.missing += max(0, p1 - self._got.pop(fid, 0))
            for k in [k for k in self._got if k < fid - 50 or k > fid + 50]:
                self._got.pop(k)
            with self._lock:
                self.complete = self.raw.copy()
                self.version += 1
                self.last_frame_id, self.last_t = fid, time.perf_counter()
            if sock is not None and src is not None:
                sock.sendto(b"ACK " + struct.pack("<II", fid, esp_ms), src)  # lets the ESP32 measure its round trip

    def _count(self, fid):
        self.tiles += 1
        self._got[fid] = self._got.get(fid, 0) + 1
        while len(self._got) > self.MAX_PENDING:
            self._got.pop(min(self._got))

    # -- thread -------------------------------------------------------------------------------------------------------------------
    def _run(self):
        sock = self._sock
        t_hello, t_targets, t_start, targets = 0.0, 0.0, time.perf_counter(), []
        while not self._stop.is_set():
            now = time.perf_counter()
            if now >= t_targets:  # adapters come and go (hotspot restarts): recompute every 10 s; never crash the thread
                targets, t_targets = broadcast_targets(), now + 10
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
