"""Reproduce the static-JPEG cadence control from the repository root."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["before", "after"])
    parser.add_argument("--out-root", default="data/phase2-profile-1114")
    args = parser.parse_args()
    repo = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
    sys.path.insert(0, str(repo))
    from tools import monitor_door

    root = monitor_door.private_path(args.out_root)
    out = root / args.mode
    if out.exists():
        raise FileExistsError("choose a new --out-root")
    root.mkdir(parents=True, exist_ok=True)

    if args.mode == "before":
        old_path = root / "baseline_phase2_live.py"
        old_path.write_bytes(subprocess.check_output(["git", "show", "df513f3:sentry/app/phase2_live.py"]))
        spec = importlib.util.spec_from_file_location("baseline_phase2_live", old_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        monitor_door.DoorMonitor = module.DoorMonitor
        original_build = monitor_door.build_monitor

        def build(config_path, whitelist, settings, emit, *, live):
            return original_build(config_path, whitelist, settings, emit, live=live, warmup=False)

        monitor_door.build_monitor = build

    with np.load("data/D2/1028/DQK/c02/faces.npz", allow_pickle=False) as archive:
        filename = str(archive["frame_files"][0])
    image = Path("data/D2/1028/DQK/c02") / filename
    payload = image.read_bytes()
    stop = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *unused):
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()
            deadline = time.perf_counter()
            try:
                while not stop.is_set():
                    header = b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                    self.wfile.write(header + str(len(payload)).encode() + b"\r\n\r\n" + payload + b"\r\n")
                    self.wfile.flush()
                    deadline += 1 / 12
                    stop.wait(max(0, deadline - time.perf_counter()))
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    command = [
        "--url", "http://127.0.0.1:%d/stream" % server.server_port,
        "--whitelist", "data/door-whitelist-1114",
        "--out-dir", str(out),
        "--seconds", "20",
    ]
    if args.mode == "after":
        command.append("--diagnostics")
    try:
        monitor_door.main(command)
    finally:
        stop.set()
        server.shutdown()
        server.server_close()
        thread.join(2)

    sources = ["sentry/app/phase2_live.py", "tools/monitor_door.py"]
    provenance = dict(
        synthetic_http_stream=True,
        source_hz=12,
        source="one repeated private D2 JPEG",
        source_image_sha256=hashlib.sha256(payload).hexdigest(),
        accuracy_evaluation=False,
        mode=args.mode,
        baseline_commit="df513f3" if args.mode == "before" else None,
        code_sha256={name: hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in sources},
    )
    (out / "profile_source.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
