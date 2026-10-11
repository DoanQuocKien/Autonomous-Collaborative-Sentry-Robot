import argparse
import time
import json
import math
import threading
from pathlib import Path
import zmq
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
import cv2
from common.protocol import encode_video_header
from sentry.config import load as load_config
from sentry.net.zmq_rx import decode_frame

# ---- Replay Iterators for Unit Testing (Offline) ----

class ReplayStream:
    """JetBot read() returns VideoFrame; iteration retains legacy (image, time)."""
    def __init__(self, data_dir, source="jetbot"):
        self.data_dir = Path(data_dir)
        self.source = source
        self.meta_path = self.data_dir / f"{source}_meta.jsonl"
        self.frames = []
        if self.meta_path.exists():
            with open(self.meta_path, "r", encoding="utf-8") as f:
                for line in f:
                    self.frames.append(json.loads(line))
        self.idx = 0
        
    def __iter__(self):
        return self
        
    def __next__(self):
        if self.source == "jetbot":
            frame = self.read()
            if frame is None:
                raise StopIteration
            return frame.frame_bgr, frame.t_cap
        if self.idx >= len(self.frames):
            raise StopIteration
            
        meta = self.frames[self.idx]
        self.idx += 1
        
        img_path = self.data_dir / self.source / meta["file"]
        frame = cv2.imread(str(img_path))
        
        # Return frame and the original monotonic/local timestamp
        t = meta.get("t_cap", meta.get("t_local", 0.0))
        return frame, t

    def read(self, timeout=None):
        """Immediate offline read; source times/seq and recorded local times stay intact.

        Older recordings lack t_rx/t_decode, so those local timestamps are taken
        during replay. ESP32 recordings still use the legacy iterator: their
        metadata has no JetBot monotonic capture clock.
        """
        if timeout is not None and (not math.isfinite(timeout) or timeout < 0):
            raise ValueError("timeout must be nonnegative and finite")
        if self.source != "jetbot":
            raise ValueError("VideoFrame read() is for JetBot recordings only")
        if self.idx >= len(self.frames):
            return None
        meta = self.frames[self.idx]
        self.idx += 1
        jpeg = (self.data_dir / self.source / meta["file"]).read_bytes()
        header = encode_video_header(meta["seq"], meta["t_cap"], meta["w"], meta["h"])
        return decode_frame([header, jpeg], meta.get("t_rx", time.perf_counter()),
                            clock=lambda: meta.get("t_decode", time.perf_counter()))

# ---- Network Server Mocking (HIL Replay) ----

def frame_gaps(frames, default_fps):
    """Seconds to wait after each frame: the recorded spacing (t_cap, else t_local), so a replay runs at the recorded
    rate instead of a fixed FPS. Unknown, negative (source restart) or long (pause) gaps fall back to 1 / default_fps."""
    default = 1.0 / default_fps
    gaps = []
    for a, b in zip(frames, frames[1:] + frames[:1]):
        key = "t_cap" if "t_cap" in a and "t_cap" in b else "t_local"
        dt = b.get(key, 0.0) - a.get(key, 0.0) if key in a and key in b else None
        gaps.append(dt if dt is not None and 0.0 < dt <= 1.0 else default)
    return gaps


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    pass

class MJPEGHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/stream':
            self.send_response(200)
            self.send_header('Content-type', 'multipart/x-mixed-replace; boundary=frame')
            self.end_headers()
            
            data_dir = self.server.data_dir
            meta_path = data_dir / "esp32_meta.jsonl"
            
            if not meta_path.exists():
                return
                
            frames = []
            with open(meta_path, "r") as f:
                for line in f:
                    frames.append(json.loads(line))
            
            if not frames:
                return
                
            gaps = frame_gaps(frames, 15.0)
            idx = 0
            
            while True:
                meta = frames[idx]
                img_path = data_dir / "esp32" / meta["file"]
                if img_path.exists():
                    with open(img_path, "rb") as f:
                        jpeg = f.read()
                        
                    try:
                        self.wfile.write(b'--frame\r\n')
                        self.send_header('Content-type', 'image/jpeg')
                        self.send_header('Content-length', str(len(jpeg)))
                        self.end_headers()
                        self.wfile.write(jpeg)
                        self.wfile.write(b'\r\n')
                    except Exception:
                        break
                time.sleep(gaps[idx])
                idx = (idx + 1) % len(frames)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass # Suppress HTTP logs

def replay_jetbot(port, data_dir):
    ctx = zmq.Context()
    sock = ctx.socket(zmq.PUB)
    sock.bind(f"tcp://0.0.0.0:{port}")
    
    meta_path = data_dir / "jetbot_meta.jsonl"
    if not meta_path.exists():
        print(f"[JetBot Replay] No metadata found at {meta_path}")
        return
        
    frames = []
    with open(meta_path, "r") as f:
        for line in f:
            frames.append(json.loads(line))
            
    if not frames:
        return
        
    gaps = frame_gaps(frames, 20.0)
    idx = seq = 0
    print(f"[JetBot Replay] Mocking JetBot ZMQ PUB on tcp://0.0.0.0:{port}")

    while True:
        meta = frames[idx]
        img_path = data_dir / "jetbot" / meta["file"]
        if img_path.exists():
            with open(img_path, "rb") as f:
                jpeg = f.read()
            # The wire format of jetson/camera_pub.py: a fresh monotonic t_cap for realistic pipeline delays, and a seq
            # that keeps increasing when the recording loops (a reset would look like a publisher restart)
            header = encode_video_header(seq, time.monotonic(), meta["w"], meta["h"])
            sock.send_multipart([header, jpeg])
            seq += 1
        time.sleep(gaps[idx])
        idx = (idx + 1) % len(frames)

def main():
    parser = argparse.ArgumentParser(description="Replay datasets as live network streams")
    parser.add_argument("data_dir", help="Directory name inside data/ (e.g. D1)")
    parser.add_argument("--esp32-port", type=int, default=81, help="Port for ESP32 Mock (default: 81)")
    args = parser.parse_args()
    
    config = load_config()
    video_port = config["net"]["video_port"]
    
    root_dir = Path(__file__).parent.parent
    data_dir = root_dir / "data" / args.data_dir
    
    if not data_dir.exists():
        print(f"Error: Dataset directory does not exist: {data_dir}")
        return
        
    # JetBot Network Mock
    t1 = threading.Thread(target=replay_jetbot, args=(video_port, data_dir), daemon=True)
    t1.start()
    
    # ESP32 HTTP Mock
    try:
        server = ThreadingHTTPServer(('0.0.0.0', args.esp32_port), MJPEGHandler)
        server.data_dir = data_dir
        print(f"[ESP32 Replay] Mocking ESP32 MJPEG on http://0.0.0.0:{args.esp32_port}/stream")
        t2 = threading.Thread(target=server.serve_forever, daemon=True)
        t2.start()
    except PermissionError:
        print(f"\n[ESP32 Replay] Permission denied for port {args.esp32_port}. Try running with sudo, or specify a higher port: --esp32-port 8081")
        
    print(f"Replaying dataset '{args.data_dir}' in a loop... Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nReplay stopped.")

if __name__ == "__main__":
    main()
