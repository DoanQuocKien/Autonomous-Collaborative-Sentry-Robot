import csv
import json

import cv2
import numpy as np
import pytest

from sentry.nav.gridmap import OCCUPIED, OccupancyGrid
from sentry.perception.obstacle import Detection, ObstacleDetector
from tools.evaluate_w2 import evaluate
from tools.prescan_replay import FIELDS, read_poses, run


def recording(tmp_path):
    d = tmp_path / "recording"
    (d / "jetbot").mkdir(parents=True)
    meta = []
    for i, seq in enumerate([4, 0]):  # source seq can restart; pose join must use frame_index
        name = f"{i}.jpg"
        cv2.imwrite(str(d / "jetbot" / name), np.zeros((480, 640, 3), np.uint8))
        meta.append(dict(file=name, seq=seq, t_cap=100 + i, w=640, h=480))
    (d / "jetbot_meta.jsonl").write_text("\n".join(json.dumps(m) for m in meta))
    poses = tmp_path / "poses.csv"
    poses.write_text("frame_index,x_m,y_m,yaw_rad\n0,0,0,0\n1,1,0,0\n")
    return d, poses


def test_recording_to_detector_to_map_without_network(tmp_path):
    d, poses = recording(tmp_path)
    predictor = lambda image: [Detection(56, 0.9, (280, 150, 300, 300))]
    detector = ObstacleDetector.from_config(predictor=predictor)
    out = tmp_path / "out"
    summary = run(d, poses, out, detector=detector)
    assert summary["frames"] == 2 and summary["motor_commands_sent"] == 0
    assert summary["occupied_cells"] == 2 and summary["unknown_cells"] > 0
    with (out / "observations.csv").open(newline="") as f:
        rows = list(csv.DictReader(f))
    assert [int(row["seq"]) for row in rows] == [4, 0]
    assert float(rows[1]["world_x_m"]) - float(rows[0]["world_x_m"]) == pytest.approx(1)
    g = OccupancyGrid.load(out / "room_map.npz")
    for row in rows:
        cell = g.world_to_cell(float(row["world_x_m"]), float(row["world_y_m"]))
        assert g.cells[cell] == OCCUPIED
    frames = [json.loads(line) for line in (out / "frames.jsonl").read_text().splitlines()]
    assert [f["t_cap"] for f in frames] == [100, 101]


def test_missing_pose_is_rejected_before_outputs(tmp_path):
    d, poses = recording(tmp_path)
    poses.write_text("frame_index,x_m,y_m,yaw_rad\n0,0,0,0\n")
    with pytest.raises(ValueError, match="one pose"):
        run(d, poses, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_floor_json_and_duplicate_pose(tmp_path):
    path = tmp_path / "poses.csv"
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["frame_index", "x_m", "y_m", "yaw_rad", "seen_floor_json"])
        writer.writerow([0, 0, 0, 0, "[[1,0.2]]"])
    assert read_poses(path)[0][1][0].left_m == 0.2
    with path.open("a") as f:
        f.write("0,0,0,0,[]\n")
    with pytest.raises(ValueError, match="unique"):
        read_poses(path)


def measurements(tmp_path, count=20, ratio=1.05, missing=False):
    predictions, truth = tmp_path / "pred.csv", tmp_path / "truth.csv"
    g = OccupancyGrid(0.1, 6, 6, (0, 0))
    with predictions.open("w", newline="") as p, truth.open("w", newline="") as t:
        pw, tw = csv.DictWriter(p, FIELDS), csv.writer(t)
        pw.writeheader()
        tw.writerow(["obstacle_id", "frame_index", "detection_index", "tape_distance_m", "world_x_m", "world_y_m"])
        for i in range(count):
            x, y = 0.25 + (i % 5) * 0.5, 0.25 + (i // 5) * 0.5
            tape = 0.3 + 0.05 * i
            pw.writerow(dict(frame_index=i, detection_index=0, distance_m="" if missing and i == 0 else tape * ratio))
            tw.writerow([i, i, 0, tape, x, y])
            g.cells[g.world_to_cell(x, y)] = OCCUPIED
    path = tmp_path / "map.npz"
    g.save(path)
    return predictions, truth, path


def test_t1_evaluator_synthetic_pass(tmp_path):
    result = evaluate(*measurements(tmp_path))
    assert result["passed"] and result["map_fraction_within_20cm"] == 1
    assert result["distance_median_relative_error"] == pytest.approx(0.05)


@pytest.mark.parametrize("kwargs", [{"ratio": 1.25}, {"missing": True}, {"count": 19}])
def test_t1_evaluator_cannot_hide_failure(tmp_path, kwargs):
    result = evaluate(*measurements(tmp_path, **kwargs))
    assert not result["passed"] and not result["distance_pass"]


def test_map_failure_and_nonfinite_prediction(tmp_path):
    paths = measurements(tmp_path)
    g = OccupancyGrid.load(paths[2])
    g.cells[:] = -1
    g.save(paths[2])
    result = evaluate(*paths)
    assert result["distance_pass"] and not result["map_pass"]
    paths[0].write_text("frame_index,detection_index,distance_m\n0,0,nan\n")
    with pytest.raises(ValueError, match="invalid predicted"):
        evaluate(*paths)


def test_duplicate_matched_annotation_rejected(tmp_path):
    paths = measurements(tmp_path)
    lines = paths[1].read_text().splitlines()
    with paths[1].open("a") as f:
        f.write(lines[1] + "\n")
    with pytest.raises(ValueError, match="only one annotation"):
        evaluate(*paths)


def test_multiple_missed_obstacles_in_same_frame_are_counted(tmp_path):
    paths = measurements(tmp_path)
    rows = list(csv.DictReader(paths[1].read_text().splitlines()))
    with paths[1].open("w", newline="") as f:
        writer = csv.DictWriter(f, rows[0].keys())
        writer.writeheader()
        for row in rows:
            row["frame_index"], row["detection_index"] = "0", "-1"
            writer.writerow(row)
    result = evaluate(*paths)
    assert len(result["missing_distance_ids"]) == 20
    assert result["distance_median_relative_error"] is None
    assert not result["distance_pass"]
