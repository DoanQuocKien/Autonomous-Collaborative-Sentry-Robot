import http.server
import threading
import time

import cv2
import numpy as np

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
    assert n >= 5 and frame.shape == (48, 64, 3) and age < 5
