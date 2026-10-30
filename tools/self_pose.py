"""Camera angle SELF-calibration at the start of a session: measure today's pitch (and roll) from ONE ArUco marker on a vertical surface and write a fresh pose file.

  python -m tools.self_pose --marker-m 0.15 --bottom-h 0.132                  # live robot stream: about 40 frames, writes calib/camera_pose_self_<date>_<n>.json
  python -m tools.self_pose --marker-m 0.15 --bottom-h 0.132 --image a.jpg b.jpg
  python -m tools.explore_live --camera-pose calib/camera_pose_self_<...>.json ...      # then use it, like any pose file

The mount is tiltable and is moved whenever the robot is handled (plan risk 22: 1 degree is about 15 % of the ground distance at 1 m with the lens 0.100 m high), so a pose file from another
day must not be trusted: do this at the start of every session, with the robot where it will start. The marker (the black square: --marker-m, default the 150 mm prints) must stand UPRIGHT
(a board on a chair, a wall), about 1-2 m in front of the robot, with its LOWER edge --bottom-h above the floor (the T2 boards have the marker centre at 0.207 m, so the lower edge of a 0.150 m
square is at 0.132 m). The lens height is the mechanical 0.100 m (memory: it is never fitted). The file is refused unless at least --min-frames markers were accepted and their pitch spread
(standard deviation) is under --max-spread-deg: a marker that moves, is not vertical or is mismeasured fails loudly instead of giving a wrong angle that looks plausible.
Everything not measured here (strip marks, rms) stays absent from the file: `method` says it is a marker self-calibration.
"""
import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np

from sentry.perception.camera_pose import TiltFilter
from tools.estimate_camera_tilt import undistorter


def collect(frames, K, undistort, marker_m, bottom_h, camera_h, marker_id=None):
    """frames: iterable of BGR images -> (pitch estimates, roll estimates, TiltFilter). Only accepted estimates (reprojection, distance, jump filters) count."""
    tilt = TiltFilter(max_distance_m=2.5)
    pitches, rolls = [], []
    for img in frames:
        est = tilt.update_frame(undistort(img), K, marker_m, bottom_h, marker_id, camera_h)
        if est and tilt.hist and tilt.hist[-1] is est:            # the filter keeps the very estimate object it accepted; rejected ones (reprojection, distance, jump) are not in the history
            pitches.append(est["pitch_deg"])
            rolls.append(est["roll_deg"])
    return pitches, rolls, tilt


def make_pose(pitches, rolls, camera_h, tag, min_frames=15, max_spread_deg=0.4, extra=None):
    """-> pose dict, or raises ValueError with the reason (too few markers, spread too large)."""
    if len(pitches) < min_frames:
        raise ValueError("only %d usable marker frames (need %d): is the marker upright, 1-2 m away, in view, lower edge height right, id/dictionary 4x4_50?" % (len(pitches), min_frames))
    spread = float(np.std(pitches))
    if spread > max_spread_deg:
        raise ValueError("pitch estimates scatter by %.2f deg (limit %.2f): the marker moves, is not vertical, or its size or height is wrong" % (spread, max_spread_deg))
    pose = {"tag": tag, "H_cam_m": round(camera_h, 4), "H_tape_m": round(camera_h, 4), "pitch_down_deg": round(float(np.median(pitches)), 2),
            "camera_roll_deg": round(float(np.median(rolls)), 2), "passed": True, "pitch_spread_deg": round(spread, 3), "marker_frames": len(pitches),
            "method": "self-calibration from one ArUco marker on a vertical surface (tools/self_pose.py): H fixed at the mechanical %.3f m, pitch = median of the marker position estimates" % camera_h}
    if extra:
        pose.update(extra)
    return pose


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--marker-m", type=float, default=0.15, help="side of the printed black square (m)")
    ap.add_argument("--bottom-h", type=float, required=True, help="height of the marker's LOWER edge above the floor (m)")
    ap.add_argument("--camera-h", type=float, default=0.100)
    ap.add_argument("--id", type=int, default=None)
    ap.add_argument("--frames", type=int, default=45, help="frames to read from the robot")
    ap.add_argument("--min-frames", type=int, default=15)
    ap.add_argument("--max-spread-deg", type=float, default=0.4)
    ap.add_argument("--image", nargs="*")
    ap.add_argument("--camera", default="calib/camera.json")
    ap.add_argument("--ip", default="auto")
    ap.add_argument("--out", default="calib")
    a = ap.parse_args()
    K, und = undistorter(json.load(open(a.camera)))

    def stream():
        if a.image:
            for p in a.image:
                yield cv2.imread(p)
            return
        from sentry.net.discover import resolve
        from sentry.net.zmq_rx import ZMQReceiver
        with ZMQReceiver(ip=resolve(a.ip)) as rx:
            n, t0 = 0, time.time()
            while n < a.frames and time.time() - t0 < 60:
                f = rx.read(timeout=3)
                if f is None:
                    continue
                n += 1
                yield f.frame_bgr

    pitches, rolls, tilt = collect(stream(), K, und, a.marker_m, a.bottom_h, a.camera_h, a.id)
    print("%d accepted marker frames, %d rejected as outliers" % (len(pitches), tilt.rejected))
    if pitches:
        print("pitch %+.2f deg (positive = looking down), spread %.2f deg, roll %+.2f deg" % (float(np.median(pitches)), float(np.std(pitches)), float(np.median(rolls))))
    try:
        pose = make_pose(pitches, rolls, a.camera_h, "self_" + time.strftime("%m%d"), a.min_frames, a.max_spread_deg)
    except ValueError as e:
        raise SystemExit("NOT WRITTEN: %s" % e)
    out = Path(a.out)
    n = 1 + len(list(out.glob("camera_pose_self_%s_*.json" % time.strftime("%m%d"))))
    path = out / ("camera_pose_self_%s_%d.json" % (time.strftime("%m%d"), n))
    path.write_text(json.dumps(pose, indent=1))
    print("wrote", path)


if __name__ == "__main__":
    main()
