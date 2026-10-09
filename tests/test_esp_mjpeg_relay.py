"""T0: the MJPEG relay serves a normal multipart stream that tools/record.py's byte scanner can read, and only sends new frames."""
import http.client
import itertools
import threading
import urllib.request

import numpy as np

from tools.esp_mjpeg_relay import make_server


class FakeReceiver:
    """Gives a new frame (new id, different brightness) on every call."""

    def __init__(self):
        self.n = itertools.count(1)

    def latest(self):
        i = next(self.n)
        return np.full((48, 64, 3), (i * 20) % 250, np.uint8), i, 0.0


class SilentReceiver:
    def latest(self):
        return None, -1, float("inf")


def _serve(rx):
    srv = make_server(rx, port=0, fps=200, host="127.0.0.1")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def test_stream_headers_and_frames_readable_like_record_py():
    srv, port = _serve(FakeReceiver())
    try:
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        c.request("GET", "/stream")
        r = c.getresponse()
        assert r.status == 200 and "multipart/x-mixed-replace" in r.getheader("Content-Type") and "boundary=frame" in r.getheader("Content-Type")
        buf, frames = b"", []
        while len(frames) < 3:  # the same marker scan tools/record.py uses
            buf += r.read(512)
            a, b = buf.find(b"\xff\xd8"), buf.find(b"\xff\xd9")
            if a != -1 and b > a:
                frames.append(buf[a:b + 2])
                buf = buf[b + 2:]
        assert len(frames) == 3 and len(set(frames)) == 3  # new frames, not the same one repeated
        c.close()
    finally:
        srv.shutdown()


def test_still_and_not_ready_and_404():
    srv, port = _serve(FakeReceiver())
    try:
        data = urllib.request.urlopen("http://127.0.0.1:%d/jpg" % port, timeout=5).read()
        assert data[:2] == b"\xff\xd8" and data[-2:] == b"\xff\xd9"
        for path, code in (("/nothing", 404),):
            try:
                urllib.request.urlopen("http://127.0.0.1:%d%s" % (port, path), timeout=5)
                raise AssertionError("expected an HTTP error")
            except urllib.error.HTTPError as e:
                assert e.code == code
    finally:
        srv.shutdown()
    srv, port = _serve(SilentReceiver())
    try:
        try:
            urllib.request.urlopen("http://127.0.0.1:%d/jpg" % port, timeout=5)
            raise AssertionError("expected 503")
        except urllib.error.HTTPError as e:
            assert e.code == 503  # no picture yet
    finally:
        srv.shutdown()
