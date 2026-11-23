"""Measure the evasion pulse from a phone video, with no manual frame stepping.

Wheels OFF the ground (project rule). Film the wheel (a tape stripe on the tyre helps) and run:

  python -m tools.pulse_video clip.mp4 --capture-fps 240 [--wheel-roi x,y,w,h] [--out pulses.csv]

WHEEL ONLY: prints every burst of wheel motion with its length (the real pulse). No time zero, so no delay.

WITH THE FLASH (optional): also film the laptop's flash window (`tools.pursue_live --evade --flash`, white while a STRIKE is on,
time zero = the moment the override triggers) and add --flash-roi x,y,w,h. Then each flash also gives the delay to the first wheel
motion and the stop lag after the flash ended. Delay is good to about +-30 ms (60 Hz screen, its own latency) and includes the
sender period and the network.

Without --wheel-roi (and --flash-roi) the first frame opens and you drag the box(es), Enter to accept.
Times = frame index / --capture-fps (the rate when filmed, not the playback rate: phone slow-motion files are often stored at 30 fps),
so compare the printed 'video covers' with how long you really filmed.
"""
import argparse
import csv
import threading
import time

import numpy as np


class FlashWindow:
    """White while a pulse is on, black otherwise; its own thread owns the OpenCV window."""

    def __init__(self, title="STRIKE flash", size=(360, 240), margin=(8, 90)):
        import cv2
        self._cv2, self._title, self._until = cv2, title, 0.0
        self._size, self._margin = size, margin        # margin: px kept free at the right and bottom (task bar)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def pulse(self, seconds):
        self._until = time.perf_counter() + seconds

    def _run(self):
        cv2 = self._cv2
        black = np.zeros((300, 400, 3), np.uint8)
        white = black + 255
        cv2.namedWindow(self._title, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self._title, *self._size)
        cv2.moveWindow(self._title, *self._corner())
        try:
            cv2.setWindowProperty(self._title, cv2.WND_PROP_TOPMOST, 1)
        except cv2.error:
            pass
        while not self._stop.is_set():
            cv2.imshow(self._title, white if time.perf_counter() < self._until else black)
            cv2.waitKey(1)
        cv2.destroyWindow(self._title)

    def _corner(self):
        """Top-left of a window that sits in the bottom RIGHT corner of the screen (the phone aims there)."""
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()      # real pixels, so the corner is the real corner
            sw, sh = ctypes.windll.user32.GetSystemMetrics(0), ctypes.windll.user32.GetSystemMetrics(1)
        except (AttributeError, OSError):
            sw, sh = 1920, 1080
        return sw - self._size[0] - self._margin[0], sh - self._size[1] - self._margin[1]

    def close(self):
        self._stop.set()
        self._thread.join(2.0)


def segments(flag):
    """Boolean array -> [(start, end_exclusive)] of the True runs."""
    edges = np.diff(np.concatenate(([0], np.asarray(flag, np.int8), [0])))
    return list(zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)))


def flash_events(brightness, min_frames=3, min_contrast=20.0):
    lo, hi = np.percentile(brightness, [5, 95])
    if hi - lo < min_contrast:
        return []                                              # no flash visible in the box
    return [(int(s), int(e)) for s, e in segments(np.asarray(brightness) > (lo + hi) / 2) if e - s >= min_frames]


def moving_flags(motion, quiet_frames=0):
    """True where the wheel moves: threshold = noise + 25 % of the way to the 99th percentile."""
    motion = np.asarray(motion, float)
    noise = float(np.median(motion[:quiet_frames])) if quiet_frames >= 10 else float(np.percentile(motion, 20))
    return motion > noise + 0.25 * (float(np.percentile(motion, 99)) - noise)


def motion_bursts(motion, fps, min_gap_s=0.05, min_len_s=0.05):
    """Wheel-only mode: [(start_frame, end_frame)] of motion; gaps shorter than min_gap_s are joined."""
    runs = segments(moving_flags(motion))
    gap = int(min_gap_s * fps)
    merged = []
    for s, e in runs:
        if merged and s - merged[-1][1] <= gap:
            merged[-1] = (merged[-1][0], e)
        else:
            merged.append((int(s), int(e)))
    return [(s, e) for s, e in merged if e - s >= min_len_s * fps]


def pulse_events(brightness, motion, fps, search_s=1.5, lead_s=0.05, n_on=2, n_off=3):
    """With the flash: brightness[i] = flash box mean, motion[i] = wheel box mean abs difference to frame i-1. One dict per flash."""
    flashes = flash_events(brightness)
    if not flashes:
        return []
    moving = moving_flags(motion, flashes[0][0])
    ms = lambda n: round(1000.0 * n / fps, 1)
    out = []
    for k, (s, e) in enumerate(flashes):
        lo = max(s - int(lead_s * fps), 1)
        hi = min(s + int(search_s * fps), flashes[k + 1][0] if k + 1 < len(flashes) else len(motion))
        start = next((i for i in range(lo, hi - n_on + 1) if moving[i:i + n_on].all()), None)
        end = None
        if start is not None:
            end = next((i for i in range(start, hi - n_off + 1) if not moving[i:i + n_off].any()), None)
        out.append({"flash_ms": ms(e - s),
                    "start_delay_ms": None if start is None else ms(start - s),
                    "motion_ms": None if end is None else ms(end - start),
                    "stop_lag_ms": None if end is None else ms(end - e)})
    return out


def read_signals(path, flash_roi, wheel_roi):
    import cv2
    cap = cv2.VideoCapture(path)
    bright, motion, prev = [], [], None
    while True:
        ok, f = cap.read()
        if not ok:
            break
        g = cv2.GaussianBlur(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), (5, 5), 0)
        if flash_roi:
            x, y, w, h = flash_roi
            bright.append(float(g[y:y + h, x:x + w].mean()))
        x, y, w, h = wheel_roi
        wheel = g[y:y + h, x:x + w].astype(np.float32)
        motion.append(0.0 if prev is None else float(np.abs(wheel - prev).mean()))
        prev = wheel
    container_fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    return np.array(bright), np.array(motion), container_fps


def pick_rois(path, want_flash):
    import cv2
    cap = cv2.VideoCapture(path)
    ok, f = cap.read()
    cap.release()
    if not ok:
        raise SystemExit("cannot read " + path)
    flash = tuple(int(v) for v in cv2.selectROI("drag the FLASH window box, Enter", f)) if want_flash else None
    wheel = tuple(int(v) for v in cv2.selectROI("drag the WHEEL box (tape stripe), Enter", f))
    cv2.destroyAllWindows()
    return flash, wheel


def _roi(text):
    return tuple(int(v) for v in text.split(","))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--capture-fps", type=float, default=240.0, help="frames per real second when filmed (240 or 120), NOT the playback rate")
    ap.add_argument("--flash-roi", type=_roi, help="x,y,w,h of the flash window (optional: gives the delay)")
    ap.add_argument("--flash", action="store_true", help="the flash window is in the video: drag its box when asked")
    ap.add_argument("--wheel-roi", type=_roi, help="x,y,w,h around the wheel")
    ap.add_argument("--out", help="CSV path for the table")
    a = ap.parse_args()
    flash_roi, wheel_roi = a.flash_roi, a.wheel_roi
    if wheel_roi is None:
        flash_roi, wheel_roi = pick_rois(a.video, a.flash or flash_roi is not None)
    bright, motion, cfps = read_signals(a.video, flash_roi, wheel_roi)
    print("video: %d frames, file says %.1f fps; times use %.0f fps -> video covers %.2f s (compare with how long you filmed)"
          % (len(bright) or len(motion), cfps, a.capture_fps, len(motion) / a.capture_fps))
    if flash_roi:
        rows = pulse_events(bright, motion, a.capture_fps)
        if not rows:
            raise SystemExit("no flash found in the flash box (white vs black contrast < 20)")
        print("flash | commanded pulse ms | delay to wheel motion ms | wheel moved ms | stop lag after flash ms")
        for i, r in enumerate(rows, 1):
            print("%5d | %18s | %24s | %14s | %s" % (i, r["flash_ms"], r["start_delay_ms"], r["motion_ms"], r["stop_lag_ms"]))
    else:
        rows = [{"start_s": round(s / a.capture_fps, 3), "motion_ms": round(1000.0 * (e - s) / a.capture_fps, 1)}
                for s, e in motion_bursts(motion, a.capture_fps)]
        print("burst | starts at s | wheel moved ms")
        for i, r in enumerate(rows, 1):
            print("%5d | %11s | %s" % (i, r["start_s"], r["motion_ms"]))
    if a.out and rows:
        with open(a.out, "w", newline="") as fh:
            wr = csv.DictWriter(fh, fieldnames=list(rows[0]))
            wr.writeheader()
            wr.writerows(rows)


if __name__ == "__main__":
    main()
