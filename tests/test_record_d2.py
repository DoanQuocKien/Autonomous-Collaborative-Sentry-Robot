import csv
import http.server
import threading
import time
from argparse import Namespace

import cv2
import numpy as np

from tools import record_d2


def test_schedule_is_balanced_and_fills_with_centre():
    assert record_d2.schedule(10) == list("LCRLCRLCRC")
    assert record_d2.schedule(3) == list("LCR")
    assert record_d2.schedule(1) == ["C"]


def test_records_labelled_entries_from_a_fake_stream(tmp_path, monkeypatch):
    ok, jpg = cv2.imencode(".jpg", np.full((48, 64, 3), 90, np.uint8))
    part = b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(jpg) + jpg.tobytes() + b"\r\n"

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()
            try:
                for _ in range(600):
                    self.wfile.write(part)
                    time.sleep(0.01)
            except OSError:
                pass

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    real = record_d2.jpegs
    # the tool talks to <ip>:81; point it at the fake server's port instead
    monkeypatch.setattr(record_d2, "jpegs", lambda url, timeout=10: real("http://127.0.0.1:%d/stream" % srv.server_address[1], timeout))
    ns = Namespace(member="T", entries=4, seconds=0.3, ready=0.05, gap=0.05, start_delay=0.05, dist="2.0", light="test", session="s",
                   ip="127.0.0.1", out=str(tmp_path), no_beep=True)
    try:
        bad = record_d2.run(ns)
    finally:
        srv.shutdown()
    rows = list(csv.DictReader(open(str(tmp_path / "s" / "manifest.csv"))))
    assert [x["direction"] for x in rows] == list("LCRC") and [x["entry"] for x in rows] == ["1", "2", "3", "4"]
    assert all(int(x["n_frames"]) >= record_d2.MIN_FRAMES for x in rows) and bad == []
    assert len(list((tmp_path / "s" / "T" / "e01_L").glob("f*.jpg"))) == int(rows[0]["n_frames"])


def test_continuous_clip_saves_every_frame_and_one_manifest_row(tmp_path, monkeypatch):
    ok, jpg = cv2.imencode(".jpg", np.full((48, 64, 3), 60, np.uint8))
    part = b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(jpg) + jpg.tobytes() + b"\r\n"

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()
            try:
                for _ in range(600):
                    self.wfile.write(part)
                    time.sleep(0.01)
            except OSError:
                pass

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    real = record_d2.jpegs
    monkeypatch.setattr(record_d2, "jpegs", lambda url, timeout=10: real("http://127.0.0.1:%d/stream" % srv.server_address[1], timeout))
    ns = Namespace(member="T", continuous=True, seconds=0.6, start_delay=0.05, dist="", light="t", session="s", ip="127.0.0.1", out=str(tmp_path), no_beep=True)
    try:
        bad = record_d2.run(ns)
        record_d2.run(ns)
    finally:
        srv.shutdown()
    rows = list(csv.DictReader(open(str(tmp_path / "s" / "manifest.csv"))))
    assert bad == [] and [x["entry"] for x in rows] == ["c01", "c02"] and rows[0]["direction"] == "-"
    assert len(list((tmp_path / "s" / "T" / "c01").glob("f*.jpg"))) == int(rows[0]["n_frames"]) >= 24
