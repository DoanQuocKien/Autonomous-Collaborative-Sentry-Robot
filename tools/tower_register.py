"""Tower registration + self-pose, prompted by beeps (the robot does not move). The ESP32 tower carries ArUco ids 10 (back), 11 (front, ROTATED 180 DEG: its corners are reordered with tower_markers.upright), 12 (right), 13 (left); heights in sentry/perception/tower_markers.py.

  python -m tools.tower_register [--ref-pitch -10.37]

BEEPS: ONE deep beep = put the tower on the floor about 30 cm in front of the robot, any face toward it. Each face that gives a steady pose (--frames frames with a spread under --max-spread-deg)
beeps TWICE: turn the tower to another face. When all four faces are done: THREE beeps, and the median pitch of the four faces is written to a pose file (like tools.self_pose).
If a face does not settle within --wait seconds, registration stops with one low beep and saves the faces already accepted. --ref-pitch (a pitch from a 150 mm board in the same session): also print, per face, the lower-edge offset that would reconcile the face
with it (the tower heights are the board's edge, the black square sits a paper margin higher; this finds the margin, it does not change the pose).
The floor search, the 10 s placement windows and the reverse to STANDBY are the next steps (not in this tool)."""
import argparse
import json
import math
import time
from pathlib import Path

import cv2
import numpy as np

from sentry.net.discover import resolve
from sentry.net.zmq_rx import ZMQReceiver
from sentry.perception import tower_markers as tm
from sentry.perception.camera_pose import detect_corners, pose_from_corners
from tools.estimate_camera_tilt import undistorter
from tools.self_pose import make_pose


def beep(freq, ms):
    try:
        import winsound
        winsound.Beep(freq, ms)
    except (ImportError, RuntimeError):
        print("\a", end="", flush=True)


def face_pitch(corner_sets, K, bottom_h, camera_h):
    est = [pose_from_corners(c, K, tm.MARKER_M, bottom_h, camera_h) for c in corner_sets]
    p = [e["pitch_deg"] for e in est if e]
    return (float(np.median(p)), float(np.std(p)), len(p), float(np.median([e["distance_m"] for e in est if e]))) if p else None


def implied_offset(corner_sets, K, bottom_h, camera_h, ref_pitch):
    """lower-edge offset (m) above the tabulated height that makes this face's pitch equal ref_pitch (scan -1..+3 cm)."""
    best = min(np.linspace(-0.01, 0.03, 81), key=lambda d: abs(face_pitch(corner_sets, K, bottom_h + d, camera_h)[0] - ref_pitch))
    return float(best)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frames", type=int, default=30, help="consecutive frames of one face per measurement")
    ap.add_argument("--max-spread-deg", type=float, default=0.4)
    ap.add_argument("--wait", type=float, default=90.0, help="seconds to wait per face")
    ap.add_argument("--camera-h", type=float, default=0.100)
    ap.add_argument("--camera", default="calib/camera.json")
    ap.add_argument("--ip", default="auto")
    ap.add_argument("--ref-pitch", type=float, default=None)
    ap.add_argument("--out", default="calib")
    a = ap.parse_args()
    if a.frames < 1 or not all(math.isfinite(v) and v > 0 for v in (a.wait, a.camera_h, a.max_spread_deg)):
        ap.error("frames must be at least 1, wait/camera-h/max-spread-deg must be positive and finite")
    K, und = undistorter(json.load(open(a.camera)))
    done, buf, cur, t_face = {}, [], None, time.time()
    print("ONE deep beep: put the tower on the floor ~30 cm in front, any face toward the robot", flush=True)
    beep(300, 1200)
    with ZMQReceiver(ip=resolve(a.ip)) as rx:
        while len(done) < 4:
            remaining = a.wait - (time.time() - t_face)
            if remaining <= 0:
                beep(300, 400)
                print("no steady face for %.0f s: stopping with %d of 4" % (a.wait, len(done)), flush=True)
                break
            f = rx.read(timeout=min(3, remaining))
            if f is None:
                continue
            seen = {i: c for i, c in detect_corners(und(f.frame_bgr)) if i in tm.TOWER and i not in done}
            if len(seen) != 1:                                  # none, or two faces at once (the tower is turned): start over
                buf, cur = [], None
            else:
                (i, c), = seen.items()
                if i != cur:
                    buf, cur = [], i
                buf.append(tm.upright(i, c))                         # the front marker (id 11) is rotated 180 deg: corners reordered
            if len(buf) >= a.frames:
                r = face_pitch(buf, K, tm.bottom_h(cur), a.camera_h)
                print("id %d (%s): %s" % (cur, tm.TOWER[cur][0], r), flush=True)
                if r is not None and r[2] >= a.frames and r[1] <= a.max_spread_deg:
                    done[cur] = dict(pitch_deg=round(r[0], 2), spread_deg=round(r[1], 3), distance_m=round(r[3], 3),
                                     offset_to_ref_m=None if a.ref_pitch is None else round(implied_offset(buf, K, tm.bottom_h(cur), a.camera_h, a.ref_pitch), 4))
                    if a.ref_pitch is not None:
                        print("   lower edge would need %+.1f mm to match the reference pitch %.2f" % (1000 * done[cur]["offset_to_ref_m"], a.ref_pitch), flush=True)
                    beep(1000, 150); beep(1000, 150)
                    print("TWO beeps: turn the tower to another face (%d of 4 done)" % len(done), flush=True)
                    t_face = time.time()
                buf, cur = [], None
    if done:
        pitches = [v["pitch_deg"] for v in done.values()]
        pose = make_pose(pitches, [0.0] * len(pitches), a.camera_h, "tower_" + time.strftime("%m%d"), min_frames=1, max_spread_deg=1.0,
                         extra={"tower_faces": done, "camera_roll_deg_note": "not measured by the tower registration (roll is noisy on the 50 mm markers)"})
        pose["method"] = "median pitch over the tower faces registered by tools/tower_register.py (position-based, H fixed %.3f m)" % a.camera_h
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        prefix = "camera_pose_tower_%s_" % time.strftime("%m%d")
        numbers = [int(p.stem[len(prefix):]) for p in out.glob(prefix + "*.json") if p.stem[len(prefix):].isdigit()]
        number = max(numbers, default=0) + 1
        while True:
            path = out / (prefix + str(number) + ".json")
            try:
                with path.open("x", encoding="utf-8") as stream:
                    stream.write(json.dumps(pose, indent=1))
                break
            except FileExistsError:
                number += 1
        print("wrote", path, "| pitch %+.2f deg from %d faces (spread between faces %.2f deg)" % (float(np.median(pitches)), len(done), float(np.std(pitches))))
    if len(done) == 4:
        for _ in range(3):
            beep(800, 250); time.sleep(0.1)
        print("THREE beeps: all four faces registered. Next: put it on the floor / floor search (not in this tool)", flush=True)


if __name__ == "__main__":
    main()
