import http.server
import threading
import time

import cv2
import numpy as np
import pytest

from jetson.mjpeg_latest import MjpegLatest


def test_reads_newest_frame_from_a_multipart_stream():
    ok, jpg = cv2.imencode(".jpg", np.full((48, 64, 3), 200, np.uint8))
    part = b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(jpg) + jpg.tobytes() + b"\r\n"

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()
            try:
                for _ in range(5):
                    self.wfile.write(part)
                    time.sleep(0.05)
            except OSError:
                pass

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    rx = MjpegLatest("http://127.0.0.1:%d/stream" % srv.server_address[1]).start()
    t0 = time.time()
    while rx.frames < 5 and time.time() - t0 < 5:
        time.sleep(0.05)
    frame, n, age = rx.latest()
    rx.stop()
    srv.shutdown()
    srv.server_close()
    assert n >= 5 and frame.shape == (48, 64, 3) and age < 5
    assert not rx._thread.is_alive()


def test_fragmented_jpeg_bounded_buffer_and_stale_frame(monkeypatch):
    _, jpg = cv2.imencode('.jpg', np.full((16, 24, 3), 123, np.uint8))
    rx = MjpegLatest('http://localhost/stream')
    data = jpg.tobytes()
    for chunk in (b'header\xff', data[1:10], data[10:]):
        rx._consume(chunk)
    assert rx.latest()[0].shape == (16, 24, 3) and rx.frames == 1
    rx._t -= 3
    assert rx.latest()[0] is None
    rx.MAX_BUFFER_BYTES = 100
    with pytest.raises(ValueError, match='buffer'):
        rx._consume(b'\xff\xd8' + b'x' * 101)
    assert rx._buffer == b''


def test_reconnect_and_small_frame_does_not_wait_for_4096_bytes():
    _, jpg = cv2.imencode('.jpg', np.full((16, 24, 3), 123, np.uint8))
    assert len(jpg) < 4096
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(jpg.tobytes())
            self.wfile.flush()
            time.sleep(.2)
        def log_message(self, *args):
            pass
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    rx = MjpegLatest('http://127.0.0.1:%d/stream' % srv.server_port, reconnect_s=.01).start()
    try:
        deadline = time.monotonic() + 3
        while rx.frames < 2 and time.monotonic() < deadline:
            time.sleep(.01)
        assert rx.frames >= 2 and rx.reconnects >= 1
        with pytest.raises(RuntimeError):
            rx.start()
    finally:
        rx.stop()
        srv.shutdown()
        srv.server_close()
    assert not rx._thread.is_alive()


@pytest.mark.parametrize('url,delay', [('file:///tmp/image', 1), ('http://localhost', 0), ('http://localhost', float('nan'))])
def test_invalid_receiver_settings(url, delay):
    with pytest.raises(ValueError):
        MjpegLatest(url, reconnect_s=delay)
