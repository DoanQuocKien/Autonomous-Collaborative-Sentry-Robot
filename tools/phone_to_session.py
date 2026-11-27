"""Phone clip -> a `tools.record`-style session, so `tools.detect_lunges` and `tools.label_events --align` can run on it.

    python -m tools.phone_to_session clip.mp4 --out data/D4/phone_01 --clap-s 3.2 --clap-t 1764150000.123

For the case where the robot camera is down. The frames come from a PHONE, not from the robot's fisheye lens at 0.10 m: say so in any report.
Clock: video time `s` (seconds from the first frame) maps to the laptop clock as t_local = t0 + s, with t0 = clap-t - clap-s
(clap-t = the laptop time.time() of the `c` key press in tools.label_events, clap-s = the clap's time in the video), or give --t0 directly.
Frame time is index / fps, so a variable-frame-rate clip is not corrected (slow-motion and normal clips are constant-rate).
Frames are decimated to --fps (default 30: the detector's window is 100 ms) and resized to --width keeping the aspect ratio.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

import cv2

from sentry.config import DEFAULT_PATH

ROOT = DEFAULT_PATH.parent


def convert(video, out_dir, t0, fps=30.0, width=640, data_root=None):
    data_root = (ROOT / "data" if data_root is None else Path(data_root)).resolve()
    out_dir = Path(out_dir).resolve()
    if not out_dir.is_relative_to(data_root):
        raise ValueError("a private recording must stay under data/")
    if out_dir.exists():
        raise FileExistsError("choose a new output directory")
    if not (math.isfinite(t0) and math.isfinite(fps) and fps > 0 and type(width) is int and width > 0):
        raise ValueError("finite t0, positive fps and integer width required")
    cap = cv2.VideoCapture(str(video))
    src_fps = cap.get(cv2.CAP_PROP_FPS)
    if not cap.isOpened() or not (math.isfinite(src_fps) and src_fps > 0):
        raise ValueError("cannot read the video or its frame rate: %s" % video)
    (out_dir / "jetbot").mkdir(parents=True)
    step, next_t, index, seq = 1.0 / fps, 0.0, 0, 0
    with (out_dir / "jetbot_meta.jsonl").open("x", encoding="utf-8") as meta:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            t = index / src_fps
            index += 1
            if t + 1e-9 < next_t:
                continue
            next_t = t + step
            h, w = frame.shape[:2]
            height = max(1, round(h * width / w))
            frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
            name = "%06d.jpg" % seq
            cv2.imwrite(str(out_dir / "jetbot" / name), frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
            meta.write(json.dumps({"seq": seq, "t_cap": t, "w": width, "h": height, "laptop_clock": "phone_video",
                                   "t_local": t0 + t, "file": name, "source": "phone"}) + "\n")
            seq += 1
    cap.release()
    if seq == 0:
        raise ValueError("no frames read from the video")
    info = dict(source="phone video, NOT the robot camera", video=str(video), video_sha256=hashlib.sha256(Path(video).read_bytes()).hexdigest(),
                src_fps=src_fps, out_fps=fps, width=width, frames=seq, t0=t0, clock="t_local = t0 + index/src_fps")
    (out_dir / "phone_session.json").write_text(json.dumps(info, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return info


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", type=Path)
    ap.add_argument("--out", type=Path, required=True, help="new folder under data/")
    ap.add_argument("--t0", type=float, help="laptop time.time() at video time 0")
    ap.add_argument("--clap-s", type=float, help="video time (s) of the clap")
    ap.add_argument("--clap-t", type=float, help="laptop time.time() of the clap key press")
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--width", type=int, default=640)
    a = ap.parse_args()
    if a.t0 is None:
        if a.clap_s is None or a.clap_t is None:
            ap.error("give --t0, or both --clap-s and --clap-t")
        a.t0 = a.clap_t - a.clap_s
    print(json.dumps(convert(a.video, a.out, a.t0, a.fps, a.width), indent=2))


if __name__ == "__main__":
    main()
