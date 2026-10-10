"""Serve the ESP32-CAM tile stream as a normal MJPEG stream, so tools that expect the stock sketch's  http://<ip>:81/stream  (tools/record.py, replay symmetry, browsers, VLC)
work unchanged with the GC2145 boards (see docs/ESP32-CAM.md).

    python -m tools.esp_mjpeg_relay               # listens on port 81; set esp32_ip = "127.0.0.1" in config.toml for record.py
    http://127.0.0.1:81/stream   (multipart MJPEG)      http://127.0.0.1:81/jpg   (one still)
Only new frames are sent (at most --fps per second). Port 81 may need the firewall allowed for Python, or pass --port 8081.
"""
import argparse
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

import cv2

from sentry.espcam import TileReceiver


class _Server(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def make_server(rx, port=81, quality=85, fps=15.0, host="0.0.0.0"):
    """HTTP server around a receiver (anything with latest() -> (bgr, frame_id, age)); call serve_forever() on the result."""
    enc = [cv2.IMWRITE_JPEG_QUALITY, quality]

    def jpeg():
        frame, fid, _ = rx.latest()
        if frame is None:
            return None, fid
        return cv2.imencode(".jpg", frame, enc)[1].tobytes(), fid

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.split("?")[0] == "/stream":
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                last = None
                try:
                    while True:
                        t0 = time.perf_counter()
                        frame, fid, _ = rx.latest()
                        if frame is not None and fid != last:
                            data = cv2.imencode(".jpg", frame, enc)[1].tobytes()
                            last = fid
                            self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(data) + data + b"\r\n")
                            self.wfile.flush()
                        time.sleep(max(0.0, 1.0 / fps - (time.perf_counter() - t0)))
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass
            elif self.path.split("?")[0] == "/jpg":
                data, _ = jpeg()
                if data is None:
                    self.send_response(503)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *args):
            pass

    return _Server((host, port), Handler)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=81)
    ap.add_argument("--udp-port", type=int, default=5600)
    ap.add_argument("--quality", type=int, default=85)
    ap.add_argument("--fps", type=float, default=15.0)
    a = ap.parse_args()
    rx = TileReceiver(a.udp_port).start()
    srv = make_server(rx, a.port, a.quality, a.fps)
    print("serving http://0.0.0.0:%d/stream from the ESP32 tile stream (UDP %d); Ctrl+C to stop" % (a.port, a.udp_port))
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        while True:
            time.sleep(5)
            print("frames %d, tiles %d, missing %d" % (rx.frames, rx.tiles, rx.missing))
    except KeyboardInterrupt:
        pass
    finally:
        srv.shutdown()
        rx.stop()


if __name__ == "__main__":
    main()
