"""Measure an MJPEG stream: per-second fps and KB/s, optional /diag polling. usage: meas.py URL SECONDS LOGCSV [DIAGURL]"""
import sys, time, socket, csv, json, urllib.request, threading
from urllib.parse import urlparse

url, secs, out = sys.argv[1], float(sys.argv[2]), sys.argv[3]
diag_url = sys.argv[4] if len(sys.argv) > 4 else None
u = urlparse(url)
s = socket.create_connection((u.hostname, u.port or 80), timeout=10)
s.sendall(b"GET %s HTTP/1.1\r\nHost: %s\r\n\r\n" % ((u.path + ("?" + u.query if u.query else "")).encode(), u.hostname.encode()))
buf = b""
t0 = time.time()
frames = []  # (t, size, width?)
nbytes_sec = {}
diags = []
stop = False

def poll():
    while not stop:
        try:
            d = json.loads(urllib.request.urlopen(diag_url, timeout=3).read())
            d["t"] = time.time() - t0
            diags.append(d)
        except Exception as e:
            diags.append({"t": time.time() - t0, "err": str(e)[:60]})
        time.sleep(10)

if diag_url:
    threading.Thread(target=poll, daemon=True).start()
first_dim = None
while time.time() - t0 < secs:
    try:
        d = s.recv(65536)
    except socket.timeout:
        d = b""
    if d is None:
        break
    now = time.time() - t0
    k = int(now)
    nbytes_sec[k] = nbytes_sec.get(k, 0) + len(d)
    buf += d
    while True:
        i = buf.find(b"\xff\xd8")
        if i < 0:
            buf = buf[-1:]
            break
        j = buf.find(b"\xff\xd9", i + 2)
        if j < 0:
            buf = buf[i:]
            break
        jpg = buf[i:j + 2]
        if first_dim is None:
            try:
                import numpy as np, cv2
                im = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
                first_dim = im.shape[:2] if im is not None else "decode-fail"
            except Exception as e:
                first_dim = str(e)
        frames.append((now, len(jpg))); last_jpg = jpg
        buf = buf[j + 2:]
stop = True
n = int(secs)
fps = [0] * n
for t, _ in frames:
    if int(t) < n:
        fps[int(t)] += 1
kbs = [nbytes_sec.get(k, 0) / 1024 for k in range(n)]
with open(out, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["sec", "fps", "KBps"])
    for k in range(n):
        w.writerow([k, fps[k], round(kbs[k], 1)])
skip = min(5, n // 4)
fs = sorted(fps[skip:])
p5 = fs[int(0.05 * len(fs))] if fs else 0
third = max(1, (n - skip) // 3)
a = fps[skip:skip + third]; b = fps[n - third:]
sz = [x for _, x in frames]
print("dim %s frames %d mean %.2f fps p5 %d | KB/s %.0f | frame %.1f KB | first-third %.2f last-third %.2f" % (
    first_dim, len(frames), sum(fps[skip:]) / max(1, n - skip), p5, sum(kbs[skip:]) / max(1, n - skip),
    (sum(sz) / len(sz) / 1024) if sz else 0, sum(a) / len(a), sum(b) / len(b)))
# per-minute
for m in range(0, n, 60):
    seg = fps[m:m + 60]
    print("  min %d: %.2f fps %.0f KB/s" % (m // 60, sum(seg) / len(seg), sum(kbs[m:m + 60]) / len(seg)))
prev = None
for s in diags:
    if "err" in s:
        print("  stats err", s); continue
    if prev:
        n = s["frames"] - prev["frames"]; dt = s["up_ms"] / 1e3 - prev["up_ms"] / 1e3; k = max(n, 1)
        print("  %5.0fs fps %4.1f KB/s %4.0f get %4.0f send %4.0f ms max %d/%d null %d fail %d str %d heap %d min %d big %d psram %d rssi %d T %.0f" % (
            s["t"], n / dt, (s["bytes"] - prev["bytes"]) / dt / 1024, (s["get_us"] - prev["get_us"]) / k / 1e3, (s["send_us"] - prev["send_us"]) / k / 1e3,
            s["max_get_ms"], s["max_send_ms"], s["nullfb"], s["sendfail"], s["streams"], s["heap"], s["heap_min"], s["heap_big"], s["psram"], s["rssi"], s["temp_c"]))
    else:
        print("  stats0", json.dumps(s))
    prev = s
gaps = [frames[i + 1][0] - frames[i][0] for i in range(len(frames) - 1)]
if gaps:
    gs = sorted(gaps)
    print("  inter-frame ms: median %.0f p95 %.0f max %.0f" % (gs[len(gs) // 2] * 1000, gs[int(.95 * len(gs))] * 1000, gs[-1] * 1000))
open(out + ".jpg", "wb").write(last_jpg)
