"""Client-churn test for the ESP32-CAM stream (device only, no scene needed): N rapid connect / read / disconnect cycles on :81/stream, the board's /stats before and after (heap, minimum heap, send failures, streams).
One of the drift suspects was leftover client connections; this checks that cycling clients leaves the heap and the frame rate unchanged.
  python churn_test.py 10.169.60.9 30 5 out.csv"""
import csv
import json
import socket
import sys
import time
import urllib.request

ip, n_cycles, secs, out = sys.argv[1], int(sys.argv[2]), float(sys.argv[3]), sys.argv[4]


def stats():
    try:
        return json.loads(urllib.request.urlopen("http://%s/stats" % ip, timeout=4).read())
    except Exception as e:                                         # noqa: BLE001
        return {"err": str(e)[:60]}


def one_cycle():
    t0 = time.time()
    s = socket.create_connection((ip, 81), timeout=6)
    s.settimeout(3)
    s.sendall(b"GET /stream HTTP/1.1\r\nHost: x\r\n\r\n")
    data, first = [], None
    try:
        while time.time() - t0 < secs:
            d = s.recv(65536)
            if not d:
                break
            if first is None:
                first = time.time() - t0
            data.append(d)
    except Exception:                                              # noqa: BLE001
        pass
    s.close()
    blob = b"".join(data)
    frames = max(blob.count(b"\xff\xd8\xff") - 1, 0)
    return frames / max(time.time() - t0, 1e-6), len(blob) / 1024.0 / max(time.time() - t0, 1e-6), first


before = stats()
rows = []
for i in range(1, n_cycles + 1):
    fps, kbs, first = one_cycle()
    rows.append((i, round(fps, 2), round(kbs, 1), None if first is None else round(first, 2)))
    print("cycle %2d: %.1f fps, %.0f KB/s, first byte after %s s" % (i, fps, kbs, rows[-1][3]), flush=True)
    time.sleep(0.3)
after = stats()
with open(out, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["cycle", "fps", "KBps", "first_byte_s"])
    w.writerows(rows)
json.dump({"before": before, "after": after}, open(out + ".stats.json", "w"), indent=1)
print("heap before/after:", before.get("heap"), after.get("heap"), "| heap_min:", before.get("heap_min"), after.get("heap_min"), "| sendfail:", before.get("sendfail"), after.get("sendfail"), "| streams:", after.get("streams"))
