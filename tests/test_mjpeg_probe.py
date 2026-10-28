import http.server
import re
import sys
import threading
import time

import cv2
import numpy as np

from jetson import mjpeg_probe


def test_probe_counts_frames_of_a_fake_stream(capsys, monkeypatch):
    ok, jpg = cv2.imencode(".jpg", np.full((48, 64, 3), 120, np.uint8))
    part = b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(jpg) + jpg.tobytes() + b"\r\n"

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()
            try:
                for _ in range(20):
                    self.wfile.write(part)
                    time.sleep(0.02)
            except OSError:
                pass

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(sys, "argv", ["probe", "http://127.0.0.1:%d/stream" % srv.server_address[1], "--seconds", "3", "--decode"])
    mjpeg_probe.main()
    srv.shutdown()
    out = capsys.readouterr().out
    n = int(re.search(r"(\d+) frames, ", out).group(1))
    assert n == 20 and "with decode" in out
