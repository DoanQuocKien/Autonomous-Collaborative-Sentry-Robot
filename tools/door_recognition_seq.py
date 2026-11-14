"""Door-camera (ESP32) face recognition test with several people: genuine and impostor scores at taped distances (plan row D2: TAR >= 95 % at FAR <= 1 %).

  python -m tools.door_recognition_seq record --subject HNHL --esp-ip 10.169.60.9        # one person at a time, beep-guided
  python -m tools.door_recognition_seq score --whitelist data/whitelist                   # all subjects, CPU

record: at each mark 1 beep = look at the lens, 2 beeps = turn away (~45 deg) to your right, 2 beeps again = turn away to your left (8 s each), 3 beeps = walk to the next mark (10 s); one long low tone = finished. Distances are measured from the lens along its axis.
Frames go to data/door_recog/<label>/<SUBJECT>/<dist>_<gaze>_NNNN.jpg (data/ is git-ignored: faces never leave the laptop). The ESP32 serves ONE stream client at a time.
score: every frame is scored against every enrolment (max cosine over the enrolment's vectors, InsightFace). Per subject writes <label>/scores_<SUBJECT>.json and frames_<SUBJECT>.csv (numbers only, safe to commit).
TAR = share of the subject's "straight" frames whose face is detected AND >= threshold against their OWN enrolment (a missed face counts as a miss).
FAR = share of detected "straight" frames of a subject that reach the threshold against ANOTHER enrolment (needs >= 2 enrolled subjects). "away" frames are reported apart."""
import argparse
import csv
import json
import socket
import threading
import time
from pathlib import Path

import cv2
import numpy as np

DIST = [1.8, 2.4, 3.0]
CAP_S, MOVE_S = 8.0, 10.0
FRONTAL, TURNED = 0.25, 0.30                     # head-turn QC (tools.enroll_guided.yaw_ratio): a "straight" clip should be frontal, an "away" clip turned
THR = 0.45                                       # whitelist cosine threshold (CLAUDE.md constants)
SOI, EOI = b"\xff\xd8", b"\xff\xd9"


def beep(freq, ms):
    try:
        import winsound
        winsound.Beep(freq, ms)
    except ImportError:
        print("\a", end="", flush=True)


def _reader(ip, frames, stop):
    """Keep the stream open, reconnect on any error (the board's first accept can time out); frames = [(t, jpeg)]."""
    while not stop.is_set():
        try:
            s = socket.create_connection((ip, 81), timeout=8)
            s.settimeout(4)
            s.sendall(b"GET /stream HTTP/1.1\r\nHost: x\r\n\r\n")
            buf = b""
            while not stop.is_set():
                buf += s.recv(65536)
                while True:
                    a = buf.find(SOI)
                    b = buf.find(EOI, a + 2)
                    if a < 0 or b < 0:
                        break
                    frames.append((time.time(), buf[a:b + 2]))
                    buf = buf[b + 2:]
            s.close()
        except Exception as e:
            print("stream error, reconnecting:", repr(e), flush=True)
            time.sleep(1)


def record(a):
    out = Path(a.out) / a.label / a.subject
    if out.exists() and any(out.iterdir()):
        raise SystemExit("%s already has frames; use another --label or delete it" % out)
    out.mkdir(parents=True, exist_ok=True)
    frames, stop = [], threading.Event()
    print("starting in %.0f s: stand at the first mark" % a.start_delay_s, flush=True)
    time.sleep(a.start_delay_s)
    th = threading.Thread(target=_reader, args=(a.esp_ip, frames, stop), daemon=True)
    th.start()
    t_w = time.time()
    while len(frames) < 10 and time.time() - t_w < 20:
        time.sleep(0.2)
    if len(frames) < 10:
        stop.set()
        raise SystemExit("no frames from the ESP32 after 20 s, nothing recorded")
    windows = []                                  # (label, t0, t1); both look-away clips share the label "<dist>_away"
    poses = [("straight", 1, "look at the lens"), ("away", 2, "turn away to YOUR RIGHT"), ("away", 2, "turn away to YOUR LEFT")]
    for k, d in enumerate(a.distances):
        for gaze, n_beeps, what in poses:         # 1 beep = lens, 2 beeps = change pose (right, then left again 2 beeps)
            for i in range(n_beeps):
                beep(1000, 200)
                time.sleep(0.2)
            time.sleep(a.lead_s)
            t0 = time.time()
            time.sleep(a.cap_s)
            windows.append(("%.1f_%s" % (d, gaze), t0, time.time()))
            print("captured %.1f m: %s" % (d, what), flush=True)
            time.sleep(a.gap_s)
        if k < len(a.distances) - 1:              # 3 beeps: this mark is done, walk to the next one
            for _ in range(3):
                beep(1400, 200)
                time.sleep(0.2)
            time.sleep(MOVE_S)
    beep(500, 1500)
    stop.set()
    th.join(timeout=3)
    n = {}
    for label, t0, t1 in windows:
        fr = [j for t, j in frames if t0 <= t <= t1]
        for j in fr:
            (out / ("%s_%04d.jpg" % (label, n.get(label, 0)))).write_bytes(j)
            n[label] = n.get(label, 0) + 1
        print("%s: +%d frames (%.1f fps)" % (label, len(fr), len(fr) / (t1 - t0)))


def summarize(rows, subject, thr=THR):
    """rows: [{"window": "1.8_straight", "scores": {enrolled_id: cosine or None (no face detected)}}] for ONE subject -> dict of TAR/FAR per distance and overall.
    Pure function (no images): the part worth testing."""
    def rate(num, den):
        return None if den == 0 else round(num / den, 4)

    res = {"subject": subject, "threshold": thr, "per_distance": {}}
    tot = {"gen": 0, "gen_hit": 0, "imp": 0, "imp_hit": 0}
    for dist in sorted({r["window"].split("_")[0] for r in rows}):
        straight = [r for r in rows if r["window"] == dist + "_straight"]
        away = [r for r in rows if r["window"] == dist + "_away"]
        gen_hit = sum(1 for r in straight if (r["scores"].get(subject) or -1) >= thr)
        det = [r for r in straight if any(v is not None for v in r["scores"].values())]
        imp = [v for r in det for k, v in r["scores"].items() if k != subject and v is not None]
        imp_hit = sum(v >= thr for v in imp)
        res["per_distance"][dist] = {
            "straight_frames": len(straight), "straight_detected": len(det), "tar": rate(gen_hit, len(straight)),
            "impostor_scores": len(imp), "far": rate(imp_hit, len(imp)), "impostor_max": round(max(imp), 3) if imp else None,
            "straight_frontal": sum(r.get("yaw") is not None and abs(r["yaw"]) <= FRONTAL for r in straight),
            "away_turned": sum(r.get("yaw") is not None and abs(r["yaw"]) >= TURNED for r in away),
            "away_frames": len(away), "away_detected": sum(any(v is not None for v in r["scores"].values()) for r in away),
            "away_own_ge_thr": sum((r["scores"].get(subject) or -1) >= thr for r in away)}
        tot["gen"] += len(straight)
        tot["gen_hit"] += gen_hit
        tot["imp"] += len(imp)
        tot["imp_hit"] += imp_hit
    res["tar"], res["far"] = rate(tot["gen_hit"], tot["gen"]), rate(tot["imp_hit"], tot["imp"])
    res["impostor_scores"] = tot["imp"]
    return res


def score(a):
    from sentry.perception.face import InsightFaceEncoder, load_whitelist
    from tools.enroll_guided import yaw_ratio
    wl = {k: np.asarray(v) for k, v in load_whitelist(a.whitelist).items()}
    base = Path(a.out) / a.label
    if a.device == "auto":
        import torch
        a.device = "cuda" if torch.cuda.is_available() else "cpu"
    enc = InsightFaceEncoder(device=a.device)
    for folder in sorted(p for p in base.iterdir() if p.is_dir()):
        if folder.name not in wl:
            print("skip %s: no enrolment in %s" % (folder.name, a.whitelist))
            continue
        rows = []
        for img_path in sorted(folder.glob("*.jpg")):
            faces = enc.extract(cv2.imread(str(img_path)))
            if faces:                                          # the largest face is the person; a second face in the background must not count
                f = max(faces, key=lambda r: (r["bbox"][2] - r["bbox"][0]) * (r["bbox"][3] - r["bbox"][1]))
                scores = {k: float(np.max(v @ f["embedding"])) for k, v in wl.items()}
                yaw = None if f["kps"] is None else yaw_ratio(f["kps"])
            else:
                scores, yaw = {k: None for k in wl}, None
            rows.append({"window": img_path.name.rsplit("_", 1)[0], "scores": scores, "yaw": yaw, "file": img_path.name,
                         "width": None if not faces else round(f["bbox"][2] - f["bbox"][0], 1), "conf": None if not faces else round(f["confidence"], 3)})
        with open(base / ("frames_%s.csv" % folder.name), "w", newline="") as fh:     # every frame's numbers (no image): lets the TAR be re-cut by threshold, pose or size later
            w = csv.writer(fh)
            w.writerow(["file", "window", "yaw", "width_px", "conf"] + ["cos_" + k for k in sorted(wl)])
            for r in rows:
                w.writerow([r["file"], r["window"], "" if r["yaw"] is None else round(r["yaw"], 3), r["width"], r["conf"]] + ["" if r["scores"][k] is None else round(r["scores"][k], 4) for k in sorted(wl)])
        res = summarize(rows, folder.name, a.threshold)
        res.update(label=a.label, enrolled=sorted(wl), frames=len(rows))
        (base / ("scores_%s.json" % folder.name)).write_text(json.dumps(res, indent=1))
        print("%s: TAR %s  FAR %s  (%d impostor scores, %d frames)" % (folder.name, res["tar"], res["far"], res["impostor_scores"], len(rows)), flush=True)
        for dist, d in res["per_distance"].items():              # QC: a cue slip (turned head in a "straight" clip) must not pass as a recognition failure
            bad = d["straight_frontal"] < 0.8 * d["straight_frames"] or d["away_turned"] < 0.8 * d["away_frames"]
            print("   %s m: straight frontal %d/%d, away turned %d/%d%s" % (dist, d["straight_frontal"], d["straight_frames"], d["away_turned"], d["away_frames"],
                                                                         "   <-- poses off the cues: re-record this mark" if bad else ""), flush=True)
    print("D2 needs >= 2 enrolled subjects for a FAR; threshold %.2f is not validated until this has run." % a.threshold)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("record")
    r.add_argument("--subject", required=True, help="anonymous ID, the same as the enrolment file name (data/whitelist/<ID>.npz)")
    r.add_argument("--esp-ip", required=True)
    r.add_argument("--label", default="door_1114")
    r.add_argument("--distances", type=float, nargs="+", default=DIST)
    r.add_argument("--cap-s", type=float, default=CAP_S)
    r.add_argument("--lead-s", type=float, default=2.0, help="pause after the cue beeps, to take the pose")
    r.add_argument("--gap-s", type=float, default=2.0, help="pause between clips")
    r.add_argument("--start-delay-s", type=float, default=15.0)
    r.add_argument("--out", default="data/door_recog")
    r.set_defaults(fn=record)
    s = sub.add_parser("score")
    s.add_argument("--label", default="door_1114")
    s.add_argument("--whitelist", default="data/whitelist")
    s.add_argument("--threshold", type=float, default=THR)
    s.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"], help="auto: the GPU when torch sees one (about 10x faster than the CPU), else the CPU")
    s.add_argument("--out", default="data/door_recog")
    s.set_defaults(fn=score)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
