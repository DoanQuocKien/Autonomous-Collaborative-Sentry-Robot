"""Record D2 (ESP32 door entries): N labelled walk-ins of one team member, no keyboard needed.

  python -m tools.record_d2 DQK --entries 10 --dist 2.0 --light "cafe, window left"      # ESP32 found on the network
  python -m tools.record_d2 KR --ip 10.195.93.9 --entries 10

Reads the OV2640 MJPEG stream (`esp32/sentry_cam`, one client at a time: close every other reader) on ONE connection and, per entry, saves the frames of
a short window to data/D2/<session>/<member>/e<NN>_<dir>/f<NNN>.jpg (the JPEG bytes of the ESP32, untouched) and a row to data/D2/<session>/manifest.csv:
member, entry, direction, dist_m, light, n_frames, seconds, time. data/ is git-ignored: these are face images, keep them local (privacy rule, plan 4.2).

Beep protocol (the person walking cannot read the screen): 1 beep = enter from the LEFT of the camera image, 2 = CENTRE, 3 = RIGHT; a pause; one long high
beep = start walking in and look at the door/camera; one low beep = stop; then `--gap` seconds to walk back. Entry directions cycle L C R L C R L C R C (balanced for 10).
Keep strangers out of the ESP32 view; an entry with a stranger in it must be deleted (folder and manifest row) and re-recorded.
"""
import argparse
import csv
import socket
import time
import urllib.request
from pathlib import Path

DIRS = ["L", "C", "R"]
BEEPS = {"L": 1, "C": 2, "R": 3}
MIN_FRAMES = 8          # fewer frames than this in a window: the stream stalled, re-record the entry


def schedule(n):
    """Directions for n entries: L C R repeated, the remainder filled with C (the most common real arrival)."""
    return [DIRS[i % 3] if i < (n // 3) * 3 else "C" for i in range(n)]


def beep(freq, ms, enabled):
    if not enabled:
        return
    try:
        import winsound
        winsound.Beep(freq, ms)
    except ImportError:             # not Windows: terminal bell instead
        print("\a", end="", flush=True)


def jpegs(url, timeout=10):
    """Yield complete JPEG byte strings from an HTTP MJPEG stream (start and end markers)."""
    buf = b""
    with urllib.request.urlopen(url, timeout=timeout) as r:
        while True:
            chunk = r.read(8192)
            if not chunk:
                return
            buf += chunk
            while True:
                a = buf.find(b"\xff\xd8")
                b = buf.find(b"\xff\xd9", a + 2) if a >= 0 else -1
                if a < 0 or b < 0:
                    if a < 0:
                        buf = buf[-1:]
                    elif a > 0:
                        buf = buf[a:]
                    break
                yield buf[a:b + 2]
                buf = buf[b + 2:]


def run(a):
    url = "http://%s:81/stream" % a.ip
    root = Path(a.out) / a.session
    mdir = root / a.member
    mdir.mkdir(parents=True, exist_ok=True)
    manifest = root / "manifest.csv"
    new = not manifest.exists()
    first_entry = 1 + len([p for p in mdir.glob("e*") if p.is_dir()])      # never reuse a number
    dirs = schedule(a.entries)
    stream = jpegs(url)
    bad = []
    with manifest.open("a", newline="") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["member", "entry", "direction", "dist_m", "light", "n_frames", "seconds", "time"])
        next(stream)                                   # connected and streaming
        print("recording %d entries of %s from %s (directions %s)" % (a.entries, a.member, url, "".join(dirs)), flush=True)
        t_wait = time.time() + a.start_delay
        while time.time() < t_wait:                    # keep reading so the ESP32 never blocks; nothing is saved
            next(stream)
        for k, d in enumerate(dirs):
            e = first_entry + k
            for _ in range(BEEPS[d]):
                beep(880, 150, not a.no_beep)
                time.sleep(0.1)
            t_ready = time.time() + a.ready
            while time.time() < t_ready:
                next(stream)
            beep(1400, 450, not a.no_beep)
            edir = mdir / ("e%02d_%s" % (e, d))
            edir.mkdir(exist_ok=True)
            t0 = time.time()
            n = 0
            while time.time() - t0 < a.seconds:
                (edir / ("f%03d.jpg" % n)).write_bytes(next(stream))
                n += 1
            beep(500, 350, not a.no_beep)
            w.writerow([a.member, e, d, a.dist, a.light, n, "%.1f" % (time.time() - t0), time.strftime("%Y-%m-%d %H:%M:%S")])
            fh.flush()
            print("entry %02d %s: %d frames" % (e, d, n), flush=True)
            if n < MIN_FRAMES:
                bad.append(e)
            t_gap = time.time() + a.gap
            while time.time() < t_gap:
                next(stream)
    print("done: %d entries in %s" % (a.entries, mdir))
    if bad:
        print("RE-RECORD entries with fewer than %d frames (stream stalled): %s" % (MIN_FRAMES, bad))
    return bad


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("member", help="who is walking in (e.g. DQK, HNHL, KR)")
    ap.add_argument("--entries", type=int, default=10)
    ap.add_argument("--seconds", type=float, default=3.0, help="length of the saved window per entry")
    ap.add_argument("--ready", type=float, default=1.5, help="pause between the direction beeps and the start beep")
    ap.add_argument("--gap", type=float, default=6.0, help="time to walk back between entries")
    ap.add_argument("--start-delay", type=float, default=5.0, help="seconds before the first entry")
    ap.add_argument("--dist", default="", help="tape distance from the camera to the face, m (free text, e.g. 2.0)")
    ap.add_argument("--light", default="", help="free text: lighting of the session")
    ap.add_argument("--session", default=time.strftime("%m%d"), help="folder under --out; one per day and place")
    ap.add_argument("--ip", default=None, help="ESP32 address (default: found on the network)")
    ap.add_argument("--out", default="data/D2")
    ap.add_argument("--no-beep", action="store_true", help="no sound (tests, or a quiet room)")
    a = ap.parse_args()
    if a.ip is None:
        from sentry.net.discover import find_esp32
        a.ip = find_esp32()
        if a.ip is None:
            raise SystemExit("no ESP32 found on this network (is the hotspot on and the ESP32 powered? give --ip)")
    try:
        bad = run(a)
    except (socket.timeout, OSError) as e:
        raise SystemExit("stream lost: %r (only one client may read the ESP32 stream)" % (e,))
    raise SystemExit(1 if bad else 0)


if __name__ == "__main__":
    main()
