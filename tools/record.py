import argparse
import time
import json
import threading
import urllib.request
from pathlib import Path
import zmq

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        pass

def load_config():
    root_dir = Path(__file__).parent.parent
    config_path = root_dir / "config.toml"
    with open(config_path, "rb") as f:
        return tomllib.load(f)

def record_jetbot(ip, port, out_dir):
    ctx = zmq.Context()
    sock = ctx.socket(zmq.SUB)
    sock.setsockopt(zmq.CONFLATE, 1)
    sock.connect(f"tcp://{ip}:{port}")
    sock.setsockopt_string(zmq.SUBSCRIBE, "")
    
    meta_path = out_dir / "jetbot_meta.jsonl"
    print(f"[JetBot] Recording to {out_dir}/jetbot, connecting to tcp://{ip}:{port}")
    
    with open(meta_path, "a") as meta_f:
        while True:
            try:
                parts = sock.recv_multipart()
                if len(parts) != 2:
                    continue
                header_bytes, jpeg = parts
                msg = json.loads(header_bytes.decode('utf-8'))
                
                t_local = time.time()
                seq = msg.get("seq", int(t_local * 1000))
                
                filename = f"{seq:06d}.jpg"
                img_path = out_dir / "jetbot" / filename
                with open(img_path, "wb") as f:
                    f.write(jpeg)
                
                msg["t_local"] = t_local
                msg["file"] = filename
                meta_f.write(json.dumps(msg) + "\n")
                meta_f.flush()
            except zmq.ZMQError as e:
                pass
            except Exception as e:
                print(f"[JetBot] Error: {e}")
                time.sleep(1)

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
    jetbot_ip = config["net"]["jetbot_ip"]
    esp32_ip = config["net"]["esp32_ip"]
    video_port = config["net"]["video_port"]
    
    root_dir = Path(__file__).parent.parent
    data_dir = root_dir / "data" / args.out_dir
    (data_dir / "jetbot").mkdir(parents=True, exist_ok=True)
    (data_dir / "esp32").mkdir(parents=True, exist_ok=True)
    
    t1 = threading.Thread(target=record_jetbot, args=(jetbot_ip, video_port, data_dir), daemon=True)
    t2 = threading.Thread(target=record_esp32, args=(esp32_ip, data_dir), daemon=True)
    
    t1.start()
    t2.start()
    
    print(f"Recording to {data_dir}... Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nRecording stopped.")

if __name__ == "__main__":
    main()
