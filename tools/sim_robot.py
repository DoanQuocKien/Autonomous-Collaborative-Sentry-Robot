import socket
import json
import time
import math
from pathlib import Path

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        print("Please install tomli if using Python < 3.11: pip install tomli")
        exit(1)

def load_config():
    # Find config.toml relative to this script
    root_dir = Path(__file__).parent.parent
    config_path = root_dir / "config.toml"
    with open(config_path, "rb") as f:
        return tomllib.load(f)

def main():
    config = load_config()
    
    port = config["net"]["control_port"]
    v_max = config.get("sim", {}).get("v_max_mps", 0.5)
    w_max = config.get("sim", {}).get("w_max_radps", 2.0)
    loop_hz = config.get("sim", {}).get("loop_hz", 50)
    dt = 1.0 / loop_hz
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", port))
    sock.setblocking(False)
    
    print(f"[Sim] Listening on UDP {port}...")
    
    x, y, theta = 0.0, 0.0, 0.0
    v_cmd, w_cmd = 0.0, 0.0
    last_cmd_time = time.time()
    watchdog_s = config["safety"]["watchdog_s"]
    
    print(f"[Sim] Starting unicycle kinematics. V_max={v_max} m/s, W_max={w_max} rad/s")
    
    try:
        while True:
            loop_start = time.time()
            
            # 1. Read all pending UDP packets
            while True:
                try:
                    data, addr = sock.recvfrom(1024)
                    msg = json.loads(data.decode("utf-8"))
                    if "v" in msg and "w" in msg:
                        v_cmd = max(-1.0, min(1.0, float(msg["v"])))
                        w_cmd = max(-1.0, min(1.0, float(msg["w"])))
                        last_cmd_time = time.time()
                    elif "play" in msg:
                        print(f"[Sim] Audio play command: {msg['play']}")
                except BlockingIOError:
                    break
                except Exception as e:
                    print(f"[Sim] Packet error: {e}")
                    break
                    
            # 2. Safety watchdog
            if time.time() - last_cmd_time > watchdog_s:
                if v_cmd != 0.0 or w_cmd != 0.0:
                    print("[Sim] Watchdog timeout. Stopping motors.")
                v_cmd, w_cmd = 0.0, 0.0
                
            # 3. Kinematics integration
            v_phys = v_cmd * v_max
            w_phys = w_cmd * w_max
            
            x += v_phys * math.cos(theta) * dt
            y += v_phys * math.sin(theta) * dt
            theta += w_phys * dt
            
            # Normalize theta to [-pi, pi]
            theta = (theta + math.pi) % (2 * math.pi) - math.pi
            
            # Only print pose when moving to avoid spamming the console
            if v_cmd != 0.0 or w_cmd != 0.0:
                print(f"[Sim Pose] x={x:.3f} m, y={y:.3f} m, theta={math.degrees(theta):.1f}° (v={v_cmd:.2f}, w={w_cmd:.2f})")
                
            # 4. Sleep to maintain loop_hz
            elapsed = time.time() - loop_start
            time.sleep(max(0, dt - elapsed))
            
    except KeyboardInterrupt:
        print("\n[Sim] Terminated.")

if __name__ == "__main__":
    main()
