"""Python 3.6 ESP32-CAM UDP tile receiver for the Jetson Nano (firmware: esp32/tile_stream, docs/ESP32-CAM.md).

Standalone port of `sentry/espcam.py` with no `sentry.*` imports and strict Python 3.6 compatibility,
so on-robot scripts (`jetson/edge_bench.py`, Stage C door worker) and CPU-only T0 tests can ingest live
or recorded GC2145 UDP tile streams directly.

    import espcam
    rx = espcam.TileReceiver().start()
    frame, frame_id, age_s = rx.latest()
"""
import socket
import struct
import threading
import time

import cv2
import numpy as np

_clock = getattr(time, "monotonic", time.time)

W, H, TW, TH = 640, 480, 64, 32
TILES_X = W // TW
NT = TILES_X * (H // TH)
HDR = struct.Struct("<2sBBIIHH")  # 'S' 'T' type flags frame_id esp_ms a b
T_TILE, T_HDR, T_END, T_FULL, T_TILES = 0, 1, 2, 3, 4
PORT = 5600

MEAN_THR, OUT_DIFF, OUT_COUNT = 16, 48, 8


def fingerprint(tile):
    """8 rows (every 4th) x four 4-byte pieces at columns 4, 20, 36, 52 of a 64x32 tile -> 8 x 16 samples."""
    rows = tile[0:32:4]
    return np.concatenate([rows[:, 4 + 16 * s:8 + 16 * s] for s in range(4)], axis=1).astype(np.int32)


def tile_dirty(now, old):
    """Changed when the mean difference of the fingerprints is large, or enough single samples differ strongly."""
    d = np.abs(fingerprint(now) - fingerprint(old))
    return bool(d.mean() >= MEAN_THR or (d >= OUT_DIFF).sum() >= OUT_COUNT)


def unplanar(t):
    """The firmware sends each Bayer tile as four colour planes in the quadrants of a 64x32 image (R, G1, G2, B, each 32x16)."""
    out = np.empty((TH, TW), np.uint8)
    out[0::2, 0::2] = t[0:16, 0:32]
    out[0::2, 1::2] = t[0:16, 32:64]
    out[1::2, 0::2] = t[16:32, 0:32]
    out[1::2, 1::2] = t[16:32, 32:64]
    return out


def planar(tile):
    """Inverse of unplanar (what the firmware does); used by simulators and tests."""
    out = np.empty((TH, TW), np.uint8)
    out[0:16, 0:32] = tile[0::2, 0::2]
    out[0:16, 32:64] = tile[0::2, 1::2]
    out[16:32, 0:32] = tile[1::2, 0::2]
    out[16:32, 32:64] = tile[1::2, 1::2]
    return out


def gray_world_gains(bgr, limit=(0.4, 3.0)):
    """Per-channel gains that make the picture's average grey, normalised to the green channel."""
    px = bgr.reshape(-1, 3).astype(np.float32)
    keep = (px.min(axis=1) > 12) & (px.max(axis=1) < 243)
    if keep.sum() < 500:
        return np.ones(3, np.float32)
    m = px[keep].mean(axis=0)
    return np.clip(m[1] / np.maximum(m, 1.0), limit[0], limit[1]).astype(np.float32)


def gamma_lut(gamma):
    return (255.0 * (np.arange(256) / 255.0) ** (1.0 / gamma)).astype(np.uint8)


def colour_lut(gains, gamma=None):
    """One 256-entry table per channel (shape 1 x 256 x 3, for cv2.LUT)."""
    lut = np.clip(np.arange(256, dtype=np.float32)[:, None] * np.asarray(gains, np.float32)[None, :], 0, 255).astype(np.uint8)
    if gamma is not None:
        lut = gamma[lut]
    return lut.reshape(1, 256, 3)


def local_ipv4():
    """Local IPv4 addresses without loopback or link-local (169.254.*), standalone for Python 3.6 on Jetson."""
    found = []
    try:
        mine = socket.gethostbyname_ex(socket.gethostname())[2]
        found.extend(mine)
    except OSError:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("10.255.255.255", 1))
            found.append(s.getsockname()[0])
        finally:
            s.close()
    except OSError:
        pass
    out = []
    for ip in found:
        if not ip.startswith(("127.", "169.254.")) and ip not in out:
            out.append(ip)
    return out


def broadcast_targets():
    """Limited broadcast plus the /24 broadcast of every local address."""
    return ["255.255.255.255"] + sorted({ip.rsplit(".", 1)[0] + ".255" for ip in local_ipv4()})


class TileReceiver(object):
    """Receives the GC2145 UDP tile stream and maintains the latest completed 640x480 BGR picture."""

    SOURCE_QUIET_S = 5.0
    MAX_PENDING = 64
    REFRESH_S = 10  # ask for a complete picture this often (s): at 1-2 fps the firmware's own slow refresh leaves grey holes for minutes

    def __init__(self, port=PORT, pattern="BG", wb="gray", gamma=1.0, wb_smooth=0.05, clock=None):
        self.port, self.wb, self.wb_smooth = port, wb, wb_smooth
        self._clock = _clock if clock is None else clock
        self.code = getattr(cv2, "COLOR_BAYER_%s2BGR" % pattern)
        self.lut = gamma_lut(gamma) if gamma != 1.0 else None
        self.raw = np.full((H, W), 128, np.uint8)
        self.complete = None
        self.version = 0
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

    def latest(self):
        """(BGR frame, frame id, seconds since completed); frame is None until the first frame arrives."""
        with self._out_lock:
            with self._lock:
                if self.header is None:
                    return None, -1, float("inf")
                version, fid, t = self.version, self.last_frame_id, self.last_t
                if self._cache[0] != version or self._cache[1] is None:
                    raw = self.complete if self.complete is not None else self.raw.copy()
                else:
                    raw = None
            if raw is not None:
                bgr = cv2.cvtColor(raw, self.code)
                if self.wb == "gray":
                    g = gray_world_gains(bgr[::4, ::4])
                    self.gains = g if not self._wb_init else (1 - self.wb_smooth) * self.gains + self.wb_smooth * g
                    self._wb_init = True
                if self.wb != "none":
                    bgr = cv2.LUT(bgr, colour_lut(self.gains, self.lut))
                elif self.lut is not None:
                    bgr = self.lut[bgr]
                bgr.setflags(write=False)
                self._cache = (version, bgr)
            return self._cache[1], fid, self._clock() - t

    def _paste(self, idx, jpg):
        if idx >= NT:
            return False
        tile = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_GRAYSCALE)
        if tile is None or tile.shape != (TH, TW):
            return False
        x, y = (idx % TILES_X) * TW, (idx // TILES_X) * TH
        with self._lock:
            self.raw[y:y + TH, x:x + TW] = unplanar(tile)
        return True

    def handle(self, data, src=None, sock=None):
        """Process one UDP packet (public so recorded streams and unit tests can feed packets directly)."""
        if len(data) < HDR.size:
            return
        magic, typ, _, fid, esp_ms, p1, p2 = HDR.unpack_from(data)
        if magic != b"ST":
            return
        if src is not None:
            now = self._clock()
            if self.source is not None and src[0] != self.source and now - self._source_t < self.SOURCE_QUIET_S:
                self.foreign += 1
                return
            self.source, self._source_t = src[0], now
        payload = data[HDR.size:]
        self.bytes += len(data)
        if typ == T_HDR:
            self.header = payload[:p1]
        elif typ == T_TILES and self.header:
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
                self.last_frame_id, self.last_t = fid, self._clock()
            if sock is not None and src is not None:
                sock.sendto(b"ACK " + struct.pack("<II", fid, esp_ms), src)

    def _count(self, fid):
        self.tiles += 1
        self._got[fid] = self._got.get(fid, 0) + 1
        while len(self._got) > self.MAX_PENDING:
            self._got.pop(min(self._got))

    def _run(self):
        sock = self._sock
        t_hello, t_targets, t_start, targets = 0.0, 0.0, self._clock(), []
        while not self._stop.is_set():
            now = self._clock()
            if now >= t_targets:
                targets, t_targets = broadcast_targets(), now + 10
            if now >= t_hello:
                for t in targets:
                    try:
                        sock.sendto(b"HELO", (t, self.port + 1))
                        if now - t_start < 3 or int(now) % self.REFRESH_S == 0:
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

    close = stop

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()


# ---- Recorded tile-stream helpers (offline T0 / replay on CPU) ---------------

_REC_MAGIC = b"STREC1\x00\x00"
_REC_ITEM = struct.Struct("<I")


def _jpeg_parts(tile_bayer, quality=80):
    ok, buf = cv2.imencode(".jpg", planar(tile_bayer), [cv2.IMWRITE_JPEG_QUALITY, int(quality)])
    if not ok:
        raise ValueError("failed to encode Bayer tile")
    j = buf.tobytes()
    i = j.index(b"\xff\xda")
    he = i + 2 + ((j[i + 2] << 8) | j[i + 3])
    return j[:he], j[he:]


def encode_frame_packets(bayer, prev=None, fid=0, esp_ms=0, quality=80, include_header=False, last_sent=None):
    """Encode one 640x480 raw Bayer frame into UDP tile packets like esp32/tile_stream."""
    if bayer.shape != (H, W):
        raise ValueError("expected (%d, %d) Bayer array" % (H, W))
    if prev is None:
        prev = np.full((H, W), 255, np.uint8)
        include_header = True
    else:
        prev = prev.copy()
    if last_sent is None:
        last_sent = np.zeros(NT, np.int64)
    else:
        last_sent = last_sent.copy()

    header = None
    entries = []
    for idx in range(NT):
        y, x = (idx // TILES_X) * TH, (idx % TILES_X) * TW
        c, p = bayer[y:y + TH, x:x + TW], prev[y:y + TH, x:x + TW]
        if tile_dirty(c, p):
            hdr, scan = _jpeg_parts(c, quality=quality)
            if header is None:
                header = hdr
            entries.append((idx, scan))
            prev[y:y + TH, x:x + TW] = c
            last_sent[idx] = fid

    queued = {i for i, _ in entries}
    for idx in [int(i) for i in np.argsort(last_sent) if int(i) not in queued][:2]:
        y, x = (idx // TILES_X) * TH, (idx % TILES_X) * TW
        hdr, scan = _jpeg_parts(bayer[y:y + TH, x:x + TW], quality=quality)
        if header is None:
            header = hdr
        entries.append((idx, scan))
        prev[y:y + TH, x:x + TW] = bayer[y:y + TH, x:x + TW]
        last_sent[idx] = fid

    packets = []
    if include_header and header is not None:
        packets.append(HDR.pack(b"ST", T_HDR, 0, fid, esp_ms, len(header), 0) + header)

    pkt = b""
    n = 0
    sent = 0
    for idx, scan in entries + [(None, None)]:
        blob = b"" if idx is None else struct.pack("<HH", idx, len(scan)) + scan
        if n and (idx is None or len(pkt) + len(blob) > 1400):
            packets.append(HDR.pack(b"ST", T_TILES, 0, fid, esp_ms, n, 0) + pkt)
            sent += n
            pkt, n = b"", 0
        if idx is not None:
            pkt += blob
            n += 1

    packets.append(HDR.pack(b"ST", T_END, 0, fid, esp_ms, sent, len(entries)))
    return packets, prev, last_sent


def dump_tile_stream(path, packets):
    """Save a sequence of raw UDP tile packets to `path`."""
    with open(str(path), "wb") as f:
        f.write(_REC_MAGIC)
        for pkt in packets:
            data = bytes(pkt)
            f.write(_REC_ITEM.pack(len(data)))
            f.write(data)


def load_tile_stream(path):
    """Load a list of raw UDP tile packets previously written by `dump_tile_stream`."""
    with open(str(path), "rb") as f:
        blob = f.read()
    if not blob.startswith(_REC_MAGIC):
        raise ValueError("invalid tile stream header in %s" % path)
    pos = len(_REC_MAGIC)
    out = []
    while pos < len(blob):
        if pos + _REC_ITEM.size > len(blob):
            raise ValueError("truncated packet length in %s" % path)
        (ln,) = _REC_ITEM.unpack_from(blob, pos)
        pos += _REC_ITEM.size
        if pos + ln > len(blob):
            raise ValueError("truncated packet payload in %s" % path)
        out.append(blob[pos:pos + ln])
        pos += ln
    return out


def replay_tile_stream(packets_or_path, rx=None, **rx_kwargs):
    """Feed a recorded packet list or file into `TileReceiver` -> list of `(frame_id, bgr_frame)`."""
    if isinstance(packets_or_path, (list, tuple)):
        packets = packets_or_path
    else:
        packets = load_tile_stream(packets_or_path)
    if rx is None:
        rx = TileReceiver(**rx_kwargs)
    frames = []
    prev_ver = rx.version
    for pkt in packets:
        rx.handle(pkt)
        if rx.version != prev_ver:
            prev_ver = rx.version
            bgr, fid, _ = rx.latest()
            if bgr is not None:
                frames.append((fid, bgr.copy()))
    return frames, rx
