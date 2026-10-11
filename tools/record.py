import argparse
import time
import json
import threading
import urllib.request
from pathlib import Path
from sentry.config import load as load_config
from sentry.net.zmq_rx import ZMQReceiver

def record_jetbot(ip, port, out_dir, stop_event=None):
    """Record complete multipart frames; retain JPEG bytes and both clock domains."""
    out_dir = Path(out_dir)
    (out_dir / "jetbot").mkdir(parents=True, exist_ok=True)
    stop_event = threading.Event() if stop_event is None else stop_event
    timeout = load_config()["telemetry"]["frame_timeout_s"]
    meta_path = out_dir / "jetbot_meta.jsonl"
    print(f"[JetBot] Recording to {out_dir}/jetbot, connecting to tcp://{ip}:{port}")
    
    index = 0
    with ZMQReceiver(ip, port) as receiver, meta_path.open("a", encoding="utf-8") as meta_f:
        while not stop_event.is_set():
            frame = receiver.read(timeout=timeout)
            if frame is None:
                continue
            # File numbering is independent of source seq, which may reset.
            while (out_dir / "jetbot" / f"{index:06d}.jpg").exists():
                index += 1
            filename = f"{index:06d}.jpg"
            (out_dir / "jetbot" / filename).write_bytes(frame.jpeg)
            msg = {"seq": frame.seq, "t_cap": frame.t_cap, "w": frame.w, "h": frame.h,
                   "t_rx": frame.t_rx, "t_decode": frame.t_decode,
                   "laptop_clock": "perf_counter", "t_local": time.time(), "file": filename}
            meta_f.write(json.dumps(msg) + "\n")
            meta_f.flush()
            index += 1

def record_esp32(ip, out_dir):
    url = f"http://{ip}:81/stream"
    meta_path = out_dir / "esp32_meta.jsonl"
    print(f"[ESP32] Recording to {out_dir}/esp32, connecting to {url}")
    
    seq = 0
    with open(meta_path, "a") as meta_f:
        while True:
            try:
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=5.0) as stream:
                    bytes_buf = b''
                    while True:
                        chunk = stream.read(4096)
                        if not chunk:
                            break
                        bytes_buf += chunk
                        
                        # Find JPEG boundaries
                        a = bytes_buf.find(b'\xff\xd8')
                        b = bytes_buf.find(b'\xff\xd9')
                        
                        if a != -1 and b != -1 and b > a:
                            jpeg = bytes_buf[a:b+2]
                            bytes_buf = bytes_buf[b+2:]
                            
                            t_local = time.time()
                            filename = f"{seq:06d}.jpg"
                            img_path = out_dir / "esp32" / filename
                            
                            with open(img_path, "wb") as f:
                                f.write(jpeg)
                                
                            meta = {"seq": seq, "t_local": t_local, "file": filename}
                            meta_f.write(json.dumps(meta) + "\n")
                            meta_f.flush()
                            seq += 1
            except Exception as e:
                print(f"[ESP32] Error: {e}. Retrying in 2s...")
                time.sleep(2)

def main():
    parser = argparse.ArgumentParser(description="Record Jetbot and ESP32 streams to disk")
    parser.add_argument("out_dir", help="Output directory name inside data/ (e.g. D1)")
    args = parser.parse_args()
    
    config = load_config()
    from tools.find_jetbot import resolve  # jetbot_ip = "auto" scans the network
    jetbot_ip = resolve(config["net"]["jetbot_ip"])
    esp32_ip = config["net"]["esp32_ip"]
    video_port = config["net"]["video_port"]
    
    root_dir = Path(__file__).parent.parent
    data_dir = root_dir / "data" / args.out_dir
    (data_dir / "jetbot").mkdir(parents=True, exist_ok=True)
    (data_dir / "esp32").mkdir(parents=True, exist_ok=True)
    
    stop_event = threading.Event()
    t1 = threading.Thread(target=record_jetbot, args=(jetbot_ip, video_port, data_dir, stop_event), daemon=True)
    t2 = threading.Thread(target=record_esp32, args=(esp32_ip, data_dir), daemon=True)
    
    t1.start()
    t2.start()
    
    print(f"Recording to {data_dir}... Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nRecording stopped.")
    finally:
        stop_event.set()
        t1.join(config["telemetry"]["frame_timeout_s"] + config["net"]["video_join_timeout_s"])

if __name__ == "__main__":
    main()
