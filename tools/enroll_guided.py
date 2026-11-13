"""Guided face enrolment: tells the person which pose to take, grabs a frame by itself when the pose and the quality are right.

    python -m tools.enroll_guided --person-id DQK            # laptop webcam, writes data/whitelist/DQK.npz
    python -m tools.enroll_guided --person-id DQK --camera 1 --min-width 110

Poses (yaw only, from the 5 landmarks of the detector): look straight, turn the head a little to your left, a little to your right,
then straight again twice (relax the face / smile, take glasses off or on). Each capture needs one face, confidence, width and sharpness
above the limits and the pose held for HOLD_S seconds. No photo is stored; only the 512-D embeddings (same .npz format as tools.enroll_whitelist).
Esc quits without saving. Poses are checked on the raw (unmirrored) frame; the preview is mirrored so it behaves like a mirror."""
import argparse
import re
import time
from pathlib import Path

import cv2
import numpy as np

from sentry.perception.face import InsightFaceEncoder, normalize_embedding

# (prompt, yaw_ratio range). yaw_ratio = (nose_x - eye_mid_x) / eye_distance on the raw image: about 0 straight, positive when the
# person turns to THEIR left (the nose moves to the image's right), negative to their right.
POSES = [
    ("Look straight at the camera", (-0.12, 0.12)),
    ("Turn your head a little to YOUR LEFT, keep your eyes on the camera", (0.20, 0.45)),
    ("Turn your head a little to YOUR RIGHT, keep your eyes on the camera", (-0.45, -0.20)),
    ("Look straight again and relax your face (a small smile is fine)", (-0.12, 0.12)),
    ("Look straight once more; glasses off or on, whichever you do not wear most", (-0.12, 0.12)),
]
HOLD_S = 0.8
MIN_CONF, MIN_SHARP = 0.6, 25.0


def yaw_ratio(kps):
    """Head turn from the landmarks: nose offset from the eye midpoint, in eye distances."""
    (lx, _), (rx, _), (nx, _) = kps[0], kps[1], kps[2]
    d = abs(rx - lx)
    return 0.0 if d < 1e-6 else float((nx - (lx + rx) / 2.0) / d)


def turn_hint(yr, rng):
    """What to tell the person when the head turn yr is outside rng."""
    if rng[0] < 0 < rng[1]:                      # straight pose
        return "look straight at the camera"
    side = 1.0 if rng[1] > 0 else -1.0
    if yr * side < 0:
        return "turn the other way"
    return "turn a little more" if abs(yr) < abs(min(rng, key=abs)) else "turn a little less"


def check(face, image, yaw_range, min_width):
    """None if this face is good for the pose, else the short reason shown to the person."""
    x0, y0, x1, y1 = face["bbox"]
    h, w = image.shape[:2]
    if face["confidence"] < MIN_CONF:
        return "face not clear"
    if x1 - x0 < min_width:
        return "come closer (face %d px, need %d)" % (x1 - x0, min_width)
    if x0 < 5 or y0 < 5 or x1 > w - 5 or y1 > h - 5:
        return "keep the whole face inside the picture"
    if face.get("kps") is None:
        return "no landmarks"
    yr = yaw_ratio(face["kps"])
    if not yaw_range[0] <= yr <= yaw_range[1]:
        return turn_hint(yr, yaw_range)
    crop = cv2.cvtColor(image[int(y0):int(y1), int(x0):int(x1)], cv2.COLOR_BGR2GRAY)
    if cv2.Laplacian(crop, cv2.CV_64F).var() < MIN_SHARP:
        return "hold still (blurry)"
    return None


def save(person_id, vectors, out_dir):
    path = Path(out_dir) / ("%s.npz" % person_id)
    if path.exists():
        raise FileExistsError("Enrolment already exists: %s (delete it to redo)" % path)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, embeddings=np.stack(vectors).astype(np.float32))
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--person-id", required=True)
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--min-width", type=int, default=100)
    ap.add_argument("--out-dir", default="data/whitelist")
    ap.add_argument("--device", default="cpu", choices=["cpu", "cuda"])
    a = ap.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", a.person_id):
        raise SystemExit("Use an anonymous ID with letters, digits, _ or -")
    if (Path(a.out_dir) / ("%s.npz" % a.person_id)).exists():
        raise SystemExit("Enrolment already exists for %s; delete it to redo" % a.person_id)
    enc = InsightFaceEncoder(device=a.device)
    cap = cv2.VideoCapture(a.camera, cv2.CAP_DSHOW)
    if not cap.isOpened():
        raise SystemExit("cannot open camera %d" % a.camera)
    vectors, k, since, best = [], 0, None, None
    try:
        while k < len(POSES):
            ok, img = cap.read()
            if not ok:
                continue
            prompt, rng = POSES[k]
            faces = enc.extract(img)
            msg = "no face"
            if len(faces) == 1:
                msg = check(faces[0], img, rng, a.min_width)
            elif len(faces) > 1:
                msg = "only one person please"
            if msg is None:
                since = since or time.time()
                if best is None or faces[0]["confidence"] > best["confidence"]:
                    best = faces[0]
                if time.time() - since >= HOLD_S:
                    vectors.append(normalize_embedding(best["embedding"]))
                    print("pose %d/%d captured" % (k + 1, len(POSES)), flush=True)
                    k, since, best = k + 1, None, None
                    time.sleep(0.6)             # a pause so the next pose is a new movement
                    continue
            else:
                since, best = None, None
            show = cv2.flip(img, 1)
            cv2.putText(show, "%d/%d  %s" % (k + 1, len(POSES), prompt), (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            cv2.putText(show, "OK, hold..." if msg is None else msg, (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0) if msg is None else (0, 165, 255), 2)
            cv2.imshow("enrol", show)
            if cv2.waitKey(1) == 27:
                raise SystemExit("cancelled, nothing saved")
    finally:
        cap.release()
        cv2.destroyAllWindows()
    print("saved", save(a.person_id, vectors, a.out_dir))


if __name__ == "__main__":
    main()
