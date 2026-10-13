"""Offline Week 2 inference/map export. Never opens a control socket.

python -m tools.prescan_replay --recording data/D1 --poses data/D1/poses.csv --out data/w2
Pose rows: frame_index,x_m,y_m,yaw_rad[,seen_floor_json]. frame_index is zero-based
ReplayStream order (survives seq resets). seen_floor_json is optional [[forward,left],...]
confirmed floor, NOT derived from YOLO absence. All recording frames need a pose.
"""
import argparse
import csv
from dataclasses import asdict
import json
import math
from pathlib import Path

from sentry.config import DEFAULT_PATH
from sentry.nav.gridmap import OccupancyGrid, Pose2D
from sentry.nav.prescan import PreScanner
from sentry.nav.vantage import VantageSelector
from sentry.perception.camera import GroundPoint
from sentry.perception.obstacle import ObstacleDetector
from tools.replay import ReplayStream

FIELDS = ["frame_index", "seq", "t_cap", "detection_index", "class_id", "confidence",
          "x1", "y1", "x2", "y2", "rejection", "forward_m", "left_m", "distance_m", "world_x_m", "world_y_m"]


def read_poses(path):
    poses = {}
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            index = int(row["frame_index"])
            if index < 0 or index in poses:
                raise ValueError("pose frame_index must be unique and nonnegative")
            pose = Pose2D(*(float(row[k]) for k in ("x_m", "y_m", "yaw_rad")))
            floor = tuple(GroundPoint(*p) for p in json.loads(row.get("seen_floor_json") or "[]"))
            poses[index] = (pose, floor)
    return poses


def run(recording, poses_path, out, config_path=DEFAULT_PATH, door_xy=None, detector=None):
    stream = ReplayStream(recording)
    if not stream.frames:
        raise ValueError("recording has no JetBot frames")
    poses = read_poses(poses_path)
    if set(poses) != set(range(len(stream.frames))):
        raise ValueError("one pose per recorded frame required; no extrapolation/default pose")
    if door_xy is not None and (len(door_xy) != 2 or not all(math.isfinite(q) for q in door_xy)):
        raise ValueError("door must be finite world coordinates")
    scanner = PreScanner(detector if detector is not None else ObstacleDetector.from_config(config_path),
                         OccupancyGrid.from_config(config_path), VantageSelector.from_config(config_path), door_xy)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    count, unresolved = 0, 0
    last = None
    with (out / "observations.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(FIELDS)
        with (out / "frames.jsonl").open("w", encoding="utf-8") as log:
            for index in range(len(stream.frames)):
                frame = stream.read()
                pose, floor = poses[index]
                last = scanner(frame.frame_bgr, frame.t_cap, pose, floor)
                obs = last.observations
                unresolved += int(obs.unresolved)
                log.write(json.dumps(dict(frame_index=index, seq=frame.seq, t_cap=frame.t_cap,
                                          pose=asdict(pose), nearest_m=obs.nearest_m,
                                          repulsive_w=obs.repulsive_w, unresolved=obs.unresolved,
                                          vantage=asdict(last.vantage) if last.vantage else None), allow_nan=False) + "\n")
                for oi, o in enumerate(obs.obstacles):
                    d, p = o.detection, o.ground
                    ground = [p.forward_m, p.left_m, p.distance_m, *scanner.grid.ground_to_world(pose, p)] if p else [""] * 5
                    writer.writerow([index, frame.seq, frame.t_cap, oi, d.class_id, d.confidence,
                                     *d.xyxy, o.rejection or "", *ground])
                count += 1
    scanner.grid.save(out / "room_map.npz")
    summary = dict(frames=count, unresolved_frames=unresolved, motor_commands_sent=0,
                   occupied_cells=int((scanner.grid.cells == 1).sum()),
                   free_cells=int((scanner.grid.cells == 0).sum()),
                   unknown_cells=int((scanner.grid.cells == -1).sum()),
                   vantage=asdict(last.vantage) if last and last.vantage else None)
    (out / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False), encoding="utf-8")
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--recording", required=True)
    ap.add_argument("--poses", required=True)
    ap.add_argument("--out", default="data/w2")
    ap.add_argument("--config", default=str(DEFAULT_PATH))
    ap.add_argument("--door", type=float, nargs=2, metavar=("X_M", "Y_M"))
    a = ap.parse_args()
    try:
        print(json.dumps(run(a.recording, a.poses, a.out, a.config, a.door), indent=2))
    except (ValueError, FileNotFoundError) as e:
        ap.error(str(e))


if __name__ == "__main__":
    main()
