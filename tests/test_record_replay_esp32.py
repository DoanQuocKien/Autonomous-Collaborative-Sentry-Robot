"""T0: record-then-replay round trip for the ESP32 view (plan section 5, Week 1 / KR): frames recorded by tools/record.py's record_esp32 from an MJPEG stream
come back byte for byte from tools/replay.py's mock ESP32 server, and the metadata lists every file. Uses the MJPEG relay with a fake receiver as the source
(the same path the GC2145 boards take), on ephemeral ports."""
import http.client
import itertools
import json
import threading
import time
import urllib.request

import numpy as np

from tools import record, replay
from tools.esp_mjpeg_relay import make_server


class FakeReceiver:
    def __init__(self):
        self.n = itertools.count(1)

    def latest(self):
        i = next(self.n)
        yy, xx = np.mgrid[0:60, 0:80]
        return ((xx * 3 + yy * 2 + i * 17) % 256).astype(np.uint8)[:, :, None].repeat(3, axis=2), i, 0.0


def _read_frames(resp, count, timeout=10):
    buf, frames, t0 = b"", [], time.time()
    while len(frames) < count and time.time() - t0 < timeout:
        buf += resp.read(512)
        a, b = buf.find(b"\xff\xd8"), buf.find(b"\xff\xd9")
        if a != -1 and b > a:
            frames.append(buf[a:b + 2])
            buf = buf[b + 2:]
    return frames


def test_record_then_replay_gives_identical_frames(tmp_path, monkeypatch):
    src = make_server(FakeReceiver(), port=0, fps=30, host="127.0.0.1")
    threading.Thread(target=src.serve_forever, daemon=True).start()
    real_urlopen = urllib.request.urlopen
    # record_esp32 hardcodes port 81 (the stock sketch); point it at our ephemeral test server
    monkeypatch.setattr(record.urllib.request, "urlopen", lambda req, timeout=None: real_urlopen(
        urllib.request.Request(req.full_url.replace(":81/", ":%d/" % src.server_address[1])), timeout=timeout))
    (tmp_path / "esp32").mkdir()
    threading.Thread(target=record.record_esp32, args=("127.0.0.1", tmp_path), daemon=True).start()
    time.sleep(2.0)
    src.shutdown()
    meta = [json.loads(line) for line in open(tmp_path / "esp32_meta.jsonl")]
    assert len(meta) >= 5
    recorded = [(tmp_path / "esp32" / m["file"]).read_bytes() for m in meta]
    assert [m["seq"] for m in meta] == list(range(len(meta)))  # no gaps in the sequence numbers
    assert all(m["t_local"] <= n["t_local"] for m, n in zip(meta, meta[1:]))  # timestamps do not go backwards

    srv = replay.ThreadingHTTPServer(("127.0.0.1", 0), replay.MJPEGHandler)
    srv.data_dir = tmp_path
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=5)
        c.request("GET", "/stream")
        played = _read_frames(c.getresponse(), 3)
        c.close()
    finally:
        srv.shutdown()
    assert played == recorded[:3]
