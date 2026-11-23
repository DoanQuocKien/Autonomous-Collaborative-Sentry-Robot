"""Live window for the robot camera: what it sees, what the pipeline makes of it, and what to do next (no beeps needed).

  python -m tools.sentry_ui [--ip auto] [--mode tower|live]

Keys:  T tower pitch registration (the wizard, writes calib/camera_pose_tower_<date>_<n>.json when 4 faces are done)
       L live view (every ArUco marker with id, range and pitch)     U undistorted / raw     R restart the wizard
       S save a screenshot to data/ui/     Q or Esc quit
Panels: header (link, FPS, frame age), camera image with marker overlay, big instruction banner, right panel with the face checklist, the
live numbers of the current face and the reason when a face is rejected. The pipeline models (YOLO, re-ID) are NOT in this window yet.
"""
import argparse
import json
import time
from collections import deque
from pathlib import Path

import cv2
import numpy as np

from sentry.net.discover import resolve
from sentry.net.zmq_rx import ZMQReceiver
from sentry.perception import tower_markers as tm
from sentry.perception.camera_pose import detect_corners, pose_from_corners
from tools.estimate_camera_tilt import undistorter
from tools.tower_register import face_pitch, save_pose

GREEN, YELLOW, RED, GREY, WHITE, BLUE = (80, 200, 80), (0, 200, 255), (70, 70, 230), (150, 150, 150), (240, 240, 240), (230, 160, 60)
LEVEL = {"ok": GREEN, "warn": YELLOW, "bad": RED, "info": WHITE}


class TowerWizard:
    """Same acceptance rule as tools/tower_register.py (frames consecutive frames of one face, spread under max_spread_deg), but it says WHY nothing is accepted."""

    def __init__(self, K, frames=30, max_spread_deg=0.4, camera_h=0.100):
        self.K, self.frames, self.max_spread, self.camera_h = K, frames, max_spread_deg, camera_h
        self.done, self.buf, self.cur = {}, [], None
        self.msg, self.level, self.spread, self.pitch_now, self.dist_now, self.saved = "Put the tower on the floor about 30 cm in front of the robot", "info", None, None, None, None

    def reset(self):
        self.__init__(self.K, self.frames, self.max_spread, self.camera_h)

    def update(self, found):
        """found: list of (id, corners) in the undistorted image."""
        tower = {i: c for i, c in found if i in tm.TOWER}
        fresh = {i: c for i, c in tower.items() if i not in self.done}
        self.pitch_now = self.dist_now = None
        if len(self.done) == 4:
            return
        if not found:
            self._reset_buf("No marker visible. Is the tower screen on and in front of the camera (30 cm)?", "bad")
        elif not tower:
            self._reset_buf("Markers %s seen, but none is a tower face (ids 10-13)" % sorted(i for i, _ in found), "bad")
        elif len(tower) > 1:
            self._reset_buf("Two tower faces visible at once: turn the tower so only ONE face shows", "warn")
        elif not fresh:
            (i,) = tower
            self._reset_buf("Face %d (%s) is already registered: turn the tower to a NEW face" % (i, tm.TOWER[i][0]), "warn")
        else:
            (i, c), = fresh.items()
            if i != self.cur:
                self.buf, self.cur = [], i
            c = tm.upright(i, c)
            est = pose_from_corners(c, self.K, tm.MARKER_M, tm.bottom_h(i), self.camera_h)
            if est:
                self.pitch_now, self.dist_now = est["pitch_deg"], est["distance_m"]
            self.buf.append(c)
            self.msg, self.level = "Hold still: face %d (%s) %d/%d frames" % (i, tm.TOWER[i][0], len(self.buf), self.frames), "info"
            if self.dist_now is not None and not 0.15 <= self.dist_now <= 0.6:
                self.msg, self.level = "Face %d is %.0f cm away: put the tower about 30 cm in front" % (i, 100 * self.dist_now), "warn"
            if len(self.buf) >= self.frames:
                self._judge(i)

    def _reset_buf(self, msg, level):
        self.buf, self.cur, self.msg, self.level = [], None, msg, level

    def _judge(self, i):
        r = face_pitch(self.buf, self.K, tm.bottom_h(i), self.camera_h)
        self.buf, self.cur = [], None
        if r is None:
            self.msg, self.level = "Face %d: marker pose could not be solved, move the tower a little and retry" % i, "bad"
            return
        self.spread = r[1]
        if r[2] < self.frames or r[1] > self.max_spread:
            self.msg, self.level = "Face %d rejected: pitch scatter %.2f deg (limit %.2f), %d/%d usable frames. Keep the tower still and flat" % (i, r[1], self.max_spread, r[2], self.frames), "bad"
            return
        self.done[i] = dict(pitch_deg=round(r[0], 2), spread_deg=round(r[1], 3), distance_m=round(r[3], 3), offset_to_ref_m=None)
        if len(self.done) == 4:
            path, pitches = save_pose(self.done, self.camera_h, "calib")
            self.saved = "%s  median pitch %+.2f deg (spread between faces %.2f)" % (path.name, float(np.median(pitches)), float(np.std(pitches)))
            self.msg, self.level = "ALL 4 FACES DONE. Saved " + self.saved, "ok"
        else:
            self.msg, self.level = "Face %d (%s) accepted: %+.2f deg. TURN THE TOWER to another face (%d of 4)" % (i, tm.TOWER[i][0], r[0], len(self.done)), "ok"


def text(img, s, org, scale=0.55, color=WHITE, thick=1):
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), thick + 2, cv2.LINE_AA)
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick, cv2.LINE_AA)


def overlay(img, found, K, camera_h, done=()):
    for i, c in found:
        tower = i in tm.TOWER
        col = GREEN if i in done else (BLUE if tower else GREY)
        cv2.polylines(img, [c.astype(np.int32).reshape(-1, 1, 2)], True, col, 2)
        label = "id %d" % i
        if tower:
            est = pose_from_corners(tm.upright(i, c), K, tm.MARKER_M, tm.bottom_h(i), camera_h)
            label += " %s" % tm.TOWER[i][0]
            if est:
                label += " %.0fcm %+.1fdeg" % (100 * est["distance_m"], est["pitch_deg"])
        text(img, label, (int(c[:, 0].min()), max(14, int(c[:, 1].min()) - 6)), 0.5, col)


def render(frame, found, wiz, mode, link, fps, age, undist, K, camera_h):
    W, FW, FH, HEAD, BANNER = 1060, 640, 480, 36, 110
    canvas = np.full((HEAD + FH + BANNER, W, 3), 30, np.uint8)
    if frame is not None:
        img = frame.copy()
        overlay(img, found, K, camera_h, wiz.done if mode == "tower" else ())
        canvas[HEAD:HEAD + FH, :FW] = img
        if mode == "tower" and wiz.cur is not None:                     # progress bar under the picture
            cv2.rectangle(canvas, (0, HEAD + FH - 10), (int(FW * len(wiz.buf) / wiz.frames), HEAD + FH), GREEN, -1)
    else:
        text(canvas, "WAITING FOR FRAMES ...", (150, HEAD + FH // 2), 0.9, RED, 2)
    # header
    stale = age is None or age > 1.0
    text(canvas, "LINK: %s" % ("NO FRAMES (%s)" % ("never" if age is None else "%.0f s ago" % age) if stale else "LIVE"), (10, 24), 0.6, RED if stale else GREEN, 2)
    text(canvas, "%.1f FPS   %s   robot %s" % (fps, "UNDISTORTED" if undist else "RAW", link), (260, 24), 0.55, WHITE)
    text(canvas, "[T] tower  [L] live  [U] undistort  [R] restart  [S] shot  [Q] quit", (560, 24), 0.45, GREY)
    # right panel
    x, y = FW + 15, HEAD + 25
    text(canvas, "MODE: " + ("TOWER REGISTRATION" if mode == "tower" else "LIVE VIEW"), (x, y), 0.6, YELLOW, 2)
    y += 30
    if mode == "tower":
        for i in (10, 11, 12, 13):
            d = wiz.done.get(i)
            col = GREEN if d else GREY
            cv2.rectangle(canvas, (x, y - 14), (x + 16, y + 2), col, -1 if d else 1)
            text(canvas, "id %d %-5s %s" % (i, tm.TOWER[i][0], "%+.2f deg  (spread %.2f)" % (d["pitch_deg"], d["spread_deg"]) if d else "to do"), (x + 26, y), 0.5, col)
            y += 26
        y += 10
        text(canvas, "current face", (x, y), 0.5, GREY); y += 24
        text(canvas, "pitch now : %s" % ("%+.2f deg" % wiz.pitch_now if wiz.pitch_now is not None else "-"), (x, y), 0.5); y += 22
        text(canvas, "distance  : %s" % ("%.0f cm" % (100 * wiz.dist_now) if wiz.dist_now is not None else "-"), (x, y), 0.5); y += 22
        text(canvas, "last spread: %s (limit %.2f)" % ("%.2f deg" % wiz.spread if wiz.spread is not None else "-", wiz.max_spread), (x, y), 0.5); y += 22
        text(canvas, "frames    : %d/%d" % (len(wiz.buf), wiz.frames), (x, y), 0.5); y += 34
        if wiz.done:
            p = [v["pitch_deg"] for v in wiz.done.values()]
            text(canvas, "median so far %+.2f deg" % float(np.median(p)), (x, y), 0.5, GREEN); y += 22
        text(canvas, "20/11 fits: -11.67, -11.29 deg", (x, y), 0.45, GREY)
    else:
        for i, c in found[:8]:
            text(canvas, "marker %d  centre (%d,%d)" % (i, c[:, 0].mean(), c[:, 1].mean()), (x, y), 0.5)
            y += 22
        if not found:
            text(canvas, "no ArUco marker in view", (x, y), 0.5, GREY)
    # banner
    cv2.rectangle(canvas, (0, HEAD + FH), (W, HEAD + FH + BANNER), (45, 45, 45), -1)
    msg = wiz.msg if mode == "tower" else "Live view: markers are outlined with id, range and pitch. Press T for the tower registration."
    col = LEVEL[wiz.level] if mode == "tower" else WHITE
    words, lines, cur = msg.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > 62:
            lines.append(cur); cur = w
        else:
            cur = (cur + " " + w).strip()
    lines.append(cur)
    for k, ln in enumerate(lines[:3]):
        text(canvas, ln, (15, HEAD + FH + 36 + 32 * k), 0.85, col, 2)
    return canvas


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ip", default="auto")
    ap.add_argument("--mode", choices=("tower", "live"), default="tower")
    ap.add_argument("--camera", default="calib/camera.json")
    ap.add_argument("--camera-h", type=float, default=0.100)
    ap.add_argument("--frames", type=int, default=30)
    ap.add_argument("--max-spread-deg", type=float, default=0.4)
    a = ap.parse_args()
    K, und = undistorter(json.load(open(a.camera)))
    wiz, mode, undist = TowerWizard(K, a.frames, a.max_spread_deg, a.camera_h), a.mode, True
    ip = resolve(a.ip)
    print("robot at", ip, "- window 'sentry' opened (click it, then T / L / U / R / S / Q)", flush=True)
    stamps, last_rx, frame, found = deque(maxlen=30), None, None, []
    shots = Path("data/ui")
    with ZMQReceiver(ip=ip) as rx:
        while True:
            f = rx.read(timeout=0.05)
            if f is not None:
                last_rx = time.time()
                stamps.append(f.t_rx)
                u = und(f.frame_bgr)
                det = detect_corners(u)                                  # always on the undistorted image
                frame, found = (u, det) if undist else (f.frame_bgr, [])   # corners are valid only on the undistorted picture
                if mode == "tower":
                    wiz.update(det)
            fps = (len(stamps) - 1) / (stamps[-1] - stamps[0]) if len(stamps) > 1 and stamps[-1] > stamps[0] else 0.0
            age = None if last_rx is None else time.time() - last_rx
            cv2.imshow("sentry", render(frame, found, wiz, mode, ip, fps, age, undist, K, a.camera_h))
            k = cv2.waitKey(1) & 0xFF
            if k in (ord("q"), 27) or cv2.getWindowProperty("sentry", cv2.WND_PROP_VISIBLE) < 1:
                break
            if k == ord("t"):
                mode = "tower"
            elif k == ord("l"):
                mode = "live"
            elif k == ord("u"):
                undist = not undist
            elif k == ord("r"):
                wiz.reset()
            elif k == ord("s") and frame is not None:
                shots.mkdir(parents=True, exist_ok=True)
                p = shots / time.strftime("ui_%m%d_%H%M%S.png")
                cv2.imwrite(str(p), frame)
                print("saved", p, flush=True)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
