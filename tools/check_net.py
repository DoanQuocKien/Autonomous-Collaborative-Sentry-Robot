"""Offline W1 telemetry smoke test: synthetic Jetson publisher + clock echo on localhost.

    python -m tools.check_net --fps 30 --seconds 5

Uses real wire messages and JPEGs; no motors or external connections.
The resulting CSV/JSON is loopback evidence, never robot/Wi-Fi acceptance.
"""
import argparse
import json
import math
from pathlib import Path
import queue
import socket
import subprocess
import sys
import threading
import time

import zmq

from common.protocol import decode_clock_request, encode_clock_reply
from jetson.camera_pub import serve, synthetic_frames
from sentry.config import load


def main():
    cfg = load()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fps", type=float, default=cfg["camera"]["fps"])
    ap.add_argument("--seconds", type=float, default=cfg["telemetry"]["duration_s"])
    ap.add_argument("--offset", type=float, default=100.0, help="simulated Jetson-minus-laptop seconds")
    ap.add_argument("--out", type=Path,
                    default=Path("reports/HuynhNguyenHoaiLoc/week-01/loopback_latency.csv"))
    args = ap.parse_args()
    if not (0 < args.fps < float("inf") and 0 < args.seconds < float("inf")):
        ap.error("fps and seconds must be positive and finite")
    if not math.isfinite(args.offset):
        ap.error("--offset must be finite")
    ready = queue.Queue()
    stop = threading.Event()
    errors = []

    def pause(seconds):
        # Event.wait has coarse timing on some Windows hosts. Keep time.sleep's
        # resolution, with bounded slices so even a low-FPS publisher can stop.
        deadline = time.perf_counter() + seconds
        while not stop.is_set():
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                break
            time.sleep(min(remaining, cfg["net"]["video_poll_ms"] / 1000))

    def publish():
        ctx = pub = None
        try:
            ctx = zmq.Context()
            pub = ctx.socket(zmq.XPUB)
            pub.setsockopt(zmq.LINGER, 0)
            port = pub.bind_to_random_port("tcp://127.0.0.1")
            ready.put(port)
            while not stop.is_set():
                if pub.poll(cfg["net"]["video_poll_ms"]):
                    pub.recv()  # subscriber handshake
                    break

            def frames():
                for image in synthetic_frames(cfg["camera"]["width"], cfg["camera"]["height"],
                                              args.fps, sleep=pause):
                    if stop.is_set():
                        break
                    yield image

            serve(pub, frames(), cfg["camera"]["jpeg_quality"], clock=lambda: time.perf_counter() + args.offset)
        except Exception as exc:
            errors.append(str(exc))
        finally:
            try:
                if pub is not None:
                    pub.close(linger=0)
            finally:
                if ctx is not None:
                    ctx.term()

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as echo:
        echo.bind(("127.0.0.1", 0))
        echo.settimeout(cfg["net"]["clock_timeout_s"])

        def clock_echo():
            try:
                while not stop.is_set():
                    try:
                        data, address = echo.recvfrom(512)
                    except socket.timeout:
                        continue
                    echo.sendto(encode_clock_reply(decode_clock_request(data),
                                                   time.perf_counter() + args.offset), address)
            except Exception as exc:
                errors.append(str(exc))

        workers = [threading.Thread(target=publish), threading.Thread(target=clock_echo)]
        for worker in workers:
            worker.start()
        try:
            video_port = ready.get(timeout=cfg["net"]["video_join_timeout_s"])
            command = [sys.executable, "-m", "tools.log_latency", "--ip", "127.0.0.1",
                       "--video-port", str(video_port), "--clock-port", str(echo.getsockname()[1]),
                       "--seconds", str(args.seconds), "--out", str(args.out)]
            process = subprocess.run(command, check=False,
                                     timeout=args.seconds + cfg["net"]["clock_samples"]
                                     * cfg["net"]["clock_timeout_s"] + cfg["net"]["video_join_timeout_s"])
        finally:
            stop.set()
            for worker in workers:
                worker.join(cfg["net"]["video_join_timeout_s"])
        if errors or any(w.is_alive() for w in workers):
            raise RuntimeError("loopback worker failed: " + repr(errors))
    metrics_path = args.out.with_suffix(".json")
    if metrics_path.exists():
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        metrics.update(scope="synthetic localhost only; not HIL", source_fps=args.fps,
                       simulated_clock_offset_s=args.offset)
        metrics_path.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    return process.returncode


if __name__ == "__main__":
    raise SystemExit(main())
