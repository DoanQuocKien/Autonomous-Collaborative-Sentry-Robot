"""Guided enrolment on the ESP32 stream; keep five embeddings privately."""
import argparse
import math
from pathlib import Path
import re
import time

import cv2
import numpy as np

from sentry.app.phase2_live import DoorSettings
from sentry.config import DEFAULT_PATH, load
from sentry.net.mjpeg_rx import MJPEGReceiver
from sentry.perception.face import face_sharpness, face_yaw_ratio, normalize_embedding
from tools.monitor_door import load_door_encoder, private_path


def pose_feedback(face, image, yaw_range, enrol, settings):
    x1, y1, x2, y2 = face["bbox"]
    h, w = image.shape[:2]
    if not 0 <= x1 < x2 <= w or not 0 <= y1 < y2 <= h:
        return "Keep the entire face in the picture"
    if face["confidence"] < settings.min_face_confidence:
        return "Face not clear; look toward the lens"
    if x2 - x1 < enrol["min_face_width"]:
        return "Come closer to the camera"
    if face_sharpness(image, face["bbox"]) < settings.min_sharpness:
        return "Hold still; face is blurry"
    yaw = face_yaw_ratio(face.get("kps"))
    if yaw is None:
        return "Landmarks missing; look toward the lens"
    if yaw_range[0] <= yaw <= yaw_range[1]:
        return None
    if yaw_range[0] < 0 < yaw_range[1]:
        return "Look straight at the lens"
    side = 1 if yaw_range[0] > 0 else -1
    direction = "LEFT" if side > 0 else "RIGHT"
    if yaw * side < 0:
        return "Turn the other way, to YOUR " + direction
    if abs(yaw) < min(abs(v) for v in yaw_range):
        return "Turn a little more to YOUR " + direction
    return "Too far; turn back slightly toward the centre"


def capture(receiver, encoder, settings, enrol, seconds, *, display=False, clock=time.perf_counter):
    if (not math.isfinite(seconds) or seconds <= 0
            or not math.isfinite(enrol["min_face_width"]) or enrol["min_face_width"] <= 0
            or not math.isfinite(enrol["hold_s"]) or enrol["hold_s"] <= 0
            or not all(math.isfinite(enrol[k]) for k in ("turn_min", "turn_max"))
            or not 0 < settings.frontal_yaw < enrol["turn_min"] < enrol["turn_max"]):
        raise ValueError("valid enrolment duration, quality and yaw limits required")
    front = (-settings.frontal_yaw, settings.frontal_yaw)
    poses = [("Look straight", front),
             ("Turn a little to YOUR LEFT", (enrol["turn_min"], enrol["turn_max"])),
             ("Turn a little to YOUR RIGHT", (-enrol["turn_max"], -enrol["turn_min"])),
             ("Look straight, relax", front), ("Look straight again", front)]
    vectors = []
    held_since = best = previous_t = None
    status = None
    start = clock()
    try:
        with receiver as source:
            while len(vectors) < len(poses) and clock() - start < seconds:
                frame = source.read(timeout=.2)
                if frame is None:
                    if previous_t is not None and clock() - previous_t > settings.max_gap_s:
                        held_since = best = None
                    continue
                if clock() - frame.t_rx > settings.max_gap_s:
                    held_since = best = None
                    continue
                if previous_t is not None and frame.t_rx - previous_t > settings.max_gap_s:
                    held_since = best = None
                previous_t = frame.t_rx
                faces = encoder.extract(frame.frame_bgr)
                prompt, yaw_range = poses[len(vectors)]
                reason = "One person facing the camera is required"
                good = False
                if len(faces) == 1:
                    f = faces[0]
                    x1, y1, x2, y2 = f["bbox"]
                    sharp = face_sharpness(frame.frame_bgr, f["bbox"])
                    reason = pose_feedback(f, frame.frame_bgr, yaw_range, enrol, settings)
                    good = reason is None
                    reason = "Hold still" if good else reason
                if good:
                    held_since = frame.t_rx if held_since is None else held_since
                    quality = f["confidence"] * (x2 - x1) * sharp
                    if best is None or quality > best[0]:
                        best = quality, normalize_embedding(f["embedding"])
                    if frame.t_rx - held_since >= enrol["hold_s"]:
                        vectors.append(best[1])
                        print("Captured pose %d/5" % len(vectors), flush=True)
                        held_since = best = None
                        status = None
                        continue
                else:
                    held_since = best = None
                message = "%d/5 %s | %s" % (len(vectors) + 1, prompt, reason)
                if message != status:
                    print(message, flush=True)
                    status = message
                if display:
                    shown = frame.frame_bgr.copy()
                    cv2.putText(shown, "%d/5 %s" % (len(vectors) + 1, prompt),
                                (8, 25), cv2.FONT_HERSHEY_SIMPLEX, .6, (0, 220, 255), 1)
                    cv2.putText(shown, reason, (8, 50), cv2.FONT_HERSHEY_SIMPLEX, .5, (0, 220, 255), 1)
                    if len(faces) == 1:
                        yaw = face_yaw_ratio(f.get("kps"))
                        detail = "Face %d px (need %d), yaw %s" % (x2 - x1, enrol["min_face_width"],
                            "missing" if yaw is None else "%.2f" % yaw)
                        cv2.putText(shown, detail, (8, 75), cv2.FONT_HERSHEY_SIMPLEX, .5, (0, 220, 255), 1)
                    cv2.imshow("ESP32 enrolment", shown)
                    if cv2.waitKey(1) == 27:
                        raise KeyboardInterrupt
        if len(vectors) != 5:
            raise TimeoutError("enrolment incomplete (%d/5); no embeddings saved" % len(vectors))
        return np.stack(vectors)
    finally:
        if display:
            cv2.destroyAllWindows()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", required=True)
    ap.add_argument("--person-id", required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--config", type=Path, default=DEFAULT_PATH)
    ap.add_argument("--seconds", type=float, default=120.)
    ap.add_argument("--display", action="store_true")
    a = ap.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", a.person_id):
        ap.error("use an anonymous ID with letters, digits, _ or -")
    out = private_path(a.out_dir) / (a.person_id + ".npz")
    if out.exists():
        raise FileExistsError("enrolment already exists")
    cfg = load(a.config)
    encoder = load_door_encoder(a.config)
    vectors = capture(MJPEGReceiver(url=a.url, request_timeout_s=2., join_timeout_s=3.), encoder,
                      DoorSettings(**cfg["door_live"]), cfg["door_enrol"], a.seconds, display=a.display)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("xb") as stream:
        np.savez_compressed(stream, embeddings=vectors)
    print("Saved five private embeddings to", out, flush=True)


if __name__ == "__main__":
    main()
