"""ESP32 placement handshake test (plan 4.3 row 'ESP32 handshake', T2): does the entrance detector on the ESP32's own frames say "door in view" when the camera faces the door
and "not in view" when it is turned away? Target: 10 of 10 correct accepts and 10 of 10 correct rejects.

  python -m tools.handshake_test ref   --name cafe_arch          # 5 frames of the door view from the ESP32 itself (hold it still, facing the door, about 2 m)
  python -m tools.handshake_test sweep --name cafe_arch          # 25 s moving the camera around the room, door NOT in view (threshold calibration)
  python -m tools.handshake_test trials --name cafe_arch         # 20 segments of 5 s, alternating FACE the door / TURN AWAY, one cue beep each
  python -m tools.handshake_test eval  --name cafe_arch          # enrol, calibrate on the sweep, decide every trial -> data/handshake/<name>/results.json

The ESP32 is held in the hand (USB cable); it reads the OV2640 MJPEG stream on ONE connection (close every other reader). Frames go to data/handshake/<name>/ (git-ignored).
Cues in `trials`: ONE long high beep = face the door (an accept trial), TWO low beeps = turn away somewhere else (a reject trial); 5 s per segment, the first 1.5 s are the
transition and are not scored. A trial is "in view" when at least half of its scored frames are (majority); the sweep frames calibrate the XFeat threshold and are never scored.
A trial that faces something that is not the door but looks like it counts as a reject trial that failed: that is the test.
"""
import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np

from tools.record_d2 import beep, jpegs

SEG_S, SKIP_S = 5.0, 1.5


def decide(flags, min_frac=0.5):
    """flags: per-frame in_view results of one trial's scored frames -> (in_view by majority, fraction). No frames: not in view."""
    if not len(flags):
        return False, 0.0
    f = float(np.mean(flags))
    return f >= min_frac, f


def tally(trials):
    """trials: dicts with kind ('accept' | 'reject') and in_view -> dict with the correct counts."""
    acc = [t for t in trials if t["kind"] == "accept"]
    rej = [t for t in trials if t["kind"] == "reject"]
    return {"accepts": len(acc), "correct_accepts": sum(1 for t in acc if t["in_view"]), "rejects": len(rej), "correct_rejects": sum(1 for t in rej if not t["in_view"])}


def capture(url, seconds, folder, prefix="f", start_after=0.0, step_s=0.0):
    """Save the stream's frames for `seconds` into folder (every frame, or one per step_s). Returns the list of (t_since_start, path)."""
    folder.mkdir(parents=True, exist_ok=True)
    stream = jpegs(url)
    next(stream)
    out, t0, last = [], time.time(), -1e9
    for jpg in stream:
        t = time.time() - t0
        if t >= seconds:
            break
        if t >= start_after and t - last >= step_s:
            p = folder / ("%s%04d.jpg" % (prefix, len(out)))
            p.write_bytes(jpg)
            out.append((round(t, 2), p))
            last = t
    return out


def cmd_ref(a, url, root):
    print("hold the ESP32 still, facing the door, about 2 m; 5 frames, one per second, start in %.0f s" % a.start_delay, flush=True)
    beep(1400, 450, not a.no_beep)
    got = capture(url, 5.5, root / "ref", "r", start_after=0.0, step_s=1.0)
    print("saved %d reference frames" % len(got))


def cmd_sweep(a, url, root):
    print("move the camera slowly around the room, the door NOT in view, for %.0f s" % a.seconds, flush=True)
    beep(1400, 450, not a.no_beep)
    got = capture(url, a.seconds, root / "sweep", "s")
    for _ in range(3):
        beep(500, 250, not a.no_beep)
    print("saved %d sweep frames" % len(got))


def cmd_trials(a, url, root):
    kinds = ["accept", "reject"] * (a.trials // 2)
    stream = jpegs(url)
    next(stream)
    meta = []
    print("%d trials of %.0f s: long high beep = FACE the door, two low beeps = TURN AWAY" % (len(kinds), SEG_S), flush=True)
    time.sleep(a.start_delay)
    for k, kind in enumerate(kinds, 1):
        folder = root / "trials" / ("t%02d_%s" % (k, kind))
        folder.mkdir(parents=True, exist_ok=True)
        if kind == "accept":
            beep(1400, 450, not a.no_beep)
        else:
            beep(500, 200, not a.no_beep)
            beep(500, 200, not a.no_beep)
        t0, n = time.time(), 0
        while time.time() - t0 < SEG_S:
            jpg = next(stream)
            t = time.time() - t0
            (folder / ("f%03d_%.2f.jpg" % (n, t))).write_bytes(jpg)
            n += 1
        meta.append({"trial": k, "kind": kind, "frames": n})
        print("trial %02d %s: %d frames" % (k, kind, n), flush=True)
    (root / "trials.json").write_text(json.dumps(meta, indent=1))
    for _ in range(3):
        beep(900, 200, not a.no_beep)


def cmd_eval(a, root, detector=None):
    from sentry.perception.entrance import EntranceConfig, EntranceDetector
    det = detector or EntranceDetector(None, EntranceConfig())
    refs = [cv2.imread(str(p)) for p in sorted((root / "ref").glob("r*.jpg"))]
    sweep = [cv2.imread(str(p)) for p in sorted((root / "sweep").glob("s*.jpg"))]
    det.enroll_esp32(refs)
    thr = det.calibrate(sweep[::2] if len(sweep) > 60 else sweep)
    print("enrolled %d reference frames, calibrated on %d sweep frames: xfeat threshold %s, dino %s" % (len(refs), len(sweep[::2] if len(sweep) > 60 else sweep), thr[0], thr[1]), flush=True)
    trials = []
    for folder in sorted((root / "trials").glob("t*")):
        kind = folder.name.split("_", 1)[1]
        files = sorted(folder.glob("f*.jpg"))
        scored = [p for p in files if float(p.stem.split("_")[1]) >= SKIP_S]
        flags, inl = [], []
        for p in scored:
            r = det.detect(cv2.imread(str(p)))
            flags.append(r.in_view)
            inl.append(r.inliers)
        inv, frac = decide(flags)
        trials.append({"trial": folder.name, "kind": kind, "frames_scored": len(scored), "fraction_in_view": round(frac, 3), "in_view": inv,
                       "correct": inv == (kind == "accept"), "median_inliers": int(np.median(inl)) if inl else 0})
        print("%-12s %2d frames, in view %3.0f %%, inliers median %3d -> %s %s" % (folder.name, len(scored), 100 * frac, trials[-1]["median_inliers"], "IN VIEW" if inv else "not in view",
                                                                              "ok" if trials[-1]["correct"] else "WRONG"), flush=True)
    res = {"xfeat_threshold": thr[0], "dino_threshold": thr[1], "refs": len(refs), "sweep_frames": len(sweep), "trials": trials, **tally(trials)}
    (root / "results.json").write_text(json.dumps(res, indent=1))
    print("correct accepts %d/%d, correct rejects %d/%d" % (res["correct_accepts"], res["accepts"], res["correct_rejects"], res["rejects"]))
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("phase", choices=["ref", "sweep", "trials", "eval"])
    ap.add_argument("--name", required=True, help="the door / session, e.g. cafe_arch or class_door")
    ap.add_argument("--ip", default="auto", help="the ESP32-CAM address, or auto (found on the network)")
    ap.add_argument("--out", default="data/handshake")
    ap.add_argument("--seconds", type=float, default=25.0, help="sweep length")
    ap.add_argument("--trials", type=int, default=20)
    ap.add_argument("--start-delay", type=float, default=8.0)
    ap.add_argument("--no-beep", action="store_true")
    a = ap.parse_args()
    root = Path(a.out) / a.name
    if a.ip == "auto" and a.phase != "eval":
        from sentry.net.discover import find_esp32
        a.ip = find_esp32()
        if a.ip is None:
            raise SystemExit("no ESP32 found on this network (is it powered and on the hotspot? give --ip)")
        print("ESP32 found at %s" % a.ip, flush=True)
    url = "http://%s:81/stream" % a.ip
    if a.phase == "eval":
        cmd_eval(a, root)
        return
    time.sleep(a.start_delay if a.phase != "trials" else 0.0)
    {"ref": cmd_ref, "sweep": cmd_sweep, "trials": cmd_trials}[a.phase](a, url, root)


if __name__ == "__main__":
    main()
