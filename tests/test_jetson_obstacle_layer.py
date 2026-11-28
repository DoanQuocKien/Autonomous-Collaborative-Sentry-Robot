"""T0 tests for Stage A CPU-only module (`jetson/obstacle_layer.py`) and laptop fallback (`sentry/app/edge_fallback.py`)."""
import ast
import json
from pathlib import Path
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "jetson"))

import obstacle_layer as edge_obs  # noqa: E402
from common.mixing import mix  # noqa: E402
from sentry.app.edge_fallback import EdgeFallbackController  # noqa: E402
from sentry.nav.explore import Command as ExploreCmd, ExploreSettings, Explorer, legal  # noqa: E402
from sentry.perception.camera import CameraGeometry  # noqa: E402
from sentry.perception.obstacle import Detection, ObstacleDetector, repulsive_w as laptop_repulsive_w  # noqa: E402


def test_jetson_obstacle_layer_is_python36_stdlib_and_numpy_only():
    path = ROOT / "jetson" / "obstacle_layer.py"
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(path), feature_version=(3, 6))
    allowed_roots = {"json", "math", "os", "numpy"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root in allowed_roots, f"unexpected import {alias.name!r} in jetson/obstacle_layer.py"
        elif isinstance(node, ast.ImportFrom):
            mod = (node.module or "").split(".")[0]
            assert mod in allowed_roots, f"unexpected import from {node.module!r} in jetson/obstacle_layer.py"


def test_camera_undistort_and_ground_distance_parity_with_opencv():
    cam_path = ROOT / "calib" / "camera.json"
    pose_path = ROOT / "calib" / "camera_pose_nowedge.json"
    laptop_geo = CameraGeometry.from_files(cam_path, pose_path)
    edge_cam = edge_obs.EdgeCameraModel.from_files(str(cam_path), str(pose_path))

    # Compare undistort_points and ground_point across realistic floor pixels (lower half of 640x480)
    raw_pts = np.array([
        [320.0, 260.0],
        [320.0, 320.0],
        [200.0, 300.0],
        [450.0, 310.0],
        [140.0, 380.0],
        [500.0, 380.0],
        [292.0, 326.0],
    ])
    laptop_rect = laptop_geo.undistort_points(raw_pts)
    edge_rect = edge_cam.undistort_points(raw_pts)
    assert np.allclose(edge_rect, laptop_rect, atol=1e-4)

    rel_errors = []
    for (lu, lv), (eu, ev) in zip(laptop_rect, edge_rect):
        lg = laptop_geo.ground_point(float(lu), float(lv))
        eg = edge_cam.ground_point(float(eu), float(ev))
        assert (lg is None) == (eg is None)
        if lg is not None:
            assert eg["forward_m"] == pytest.approx(lg.forward_m, abs=1e-5)
            assert eg["left_m"] == pytest.approx(lg.left_m, abs=1e-5)
            rel_errors.append(abs(eg["distance_m"] - lg.distance_m) / lg.distance_m)
    assert rel_errors and max(rel_errors) < 1e-4  # well inside 2 percentage points


def test_repulsion_and_explorer_parity_between_edge_and_laptop():
    cam_path = ROOT / "calib" / "camera.json"
    pose_path = ROOT / "calib" / "camera_pose_nowedge.json"
    laptop_geo = CameraGeometry.from_files(cam_path, pose_path)
    edge_cam = edge_obs.EdgeCameraModel.from_files(str(cam_path), str(pose_path))

    # Matte chair on the left at ~0.48 m (< 0.6 m explore threshold, < 0.55 m stop_m)
    # Use a rectified box and compare raw/rectified outputs identically
    raw_boxes = [
        (56, 0.90, (180.0, 220.0, 260.0, 355.0)),   # left chair
        (56, 0.85, (410.0, 230.0, 480.0, 315.0)),   # farther right chair
    ]
    det_laptop = ObstacleDetector.from_config(
        config_path=ROOT / "config.toml",
        predictor=lambda _img: [Detection(c, p, b) for c, p, b in raw_boxes],
        camera_pose_path=pose_path,
        camera_path=cam_path,
        floor_type="matte",
    )
    edge_layer = edge_obs.EdgeObstacleLayer(edge_cam, {"floor_type": "matte"})

    blank = np.zeros((480, 640, 3), dtype=np.uint8)
    # Note: ObstacleDetector undistorts the image first, so pass rectified=True with the same boxes
    l_res = det_laptop(blank, t=1.0, mode="explore", floor_type="matte")
    e_res = edge_layer.process_detections(raw_boxes, t=1.0, mode="explore", rectified=True, floor_type="matte")

    assert e_res["repulsive_w"] == pytest.approx(l_res.repulsive_w, abs=1e-5)
    if l_res.nearest_m is not None:
        assert e_res["nearest_m"] == pytest.approx(l_res.nearest_m, abs=1e-5)

    # Also test yolo_post.decode()-shaped array tuple and legal Explore commands
    decode_tuple = (
        np.array([b for _, _, b in raw_boxes], dtype=np.float32),
        np.array([p for _, p, _ in raw_boxes], dtype=np.float32),
        np.array([c for c, _, _ in raw_boxes], dtype=np.int64),
    )
    step_out = edge_layer.step(decode_tuple, t=1.1, dt=0.05, mode="explore", rectified=True, floor_type="matte")
    assert step_out["legal"] is True
    assert legal(ExploreCmd(step_out["v"], step_out["w"], step_out["state"], step_out["reason"]), ExploreSettings())
    # Left near obstacle must either turn right (w < 0) or steer right
    assert step_out["w"] < 0.0

    # Status packet encode/decode round-trip
    pkt = edge_obs.encode_edge_status(7, step_out)
    dec = edge_obs.decode_edge_status(pkt)
    assert dec["seq"] == 7 and dec["v"] == pytest.approx(step_out["v"]) and dec["w"] == pytest.approx(step_out["w"])


def test_unresolved_low_box_blocks_forward_and_keeps_commands_legal():
    cam_path = ROOT / "calib" / "camera.json"
    pose_path = ROOT / "calib" / "camera_pose_nowedge.json"
    edge_cam = edge_obs.EdgeCameraModel.from_files(str(cam_path), str(pose_path))
    edge_layer = edge_obs.EdgeObstacleLayer(edge_cam, {"floor_type": "unknown"})

    # Low box on the right side (bottom 380 >= 0.55 * 480 = 264) -> must spin LEFT (+w)
    out = edge_layer.step([(56, 0.8, (420.0, 220.0, 520.0, 380.0))], t=0.5, dt=0.05)
    assert out["blocked"] is True and out["state"] == "TURN" and out["v"] == 0.0 and out["w"] > 0.0
    assert legal(ExploreCmd(out["v"], out["w"], out["state"], out["reason"]), ExploreSettings())

    # After 6 clear frames, resumes FORWARD cleanly
    for i in range(1, 7):
        out = edge_layer.step([], t=0.5 + i * 0.05, dt=0.05)
    assert out["state"] == "FORWARD" and out["v"] > 0.40


def test_fallback_switch_takes_over_within_1s_on_switchoff_timeout_and_error():
    sw = edge_obs.FallbackSwitch(timeout_s=0.5, recovery_frames=3, enabled=True)
    laptop_cmd = {"v": 0.0, "w": 0.45, "state": "TURN", "reason": "blocked"}
    edge_cmd = {"v": 0.55, "w": -0.10, "state": "FORWARD", "reason": "steer"}

    # 1. Edge healthy -> edge owns control
    sw.on_edge_result(edge_cmd, now=1.0)
    sel = sw.select(now=1.1, laptop_result=laptop_cmd)
    assert sel["source"] == "edge" and sel["fallback_active"] is False and sel["v"] == pytest.approx(0.55)

    # 2. Switch edge OFF -> laptop takes over immediately (0.0 s <= 1.0 s)
    sw.set_edge_enabled(False, now=1.2)
    sel_off = sw.select(now=1.2, laptop_result=laptop_cmd)
    assert sel_off["source"] == "laptop" and sel_off["fallback_active"] is True
    assert sel_off["takeover_latency_s"] <= 1.0
    assert sel_off["v"] == 0.0 and sel_off["w"] == pytest.approx(0.45)

    # 3. Re-enable edge + 3 healthy frames -> recovers edge; then edge goes silent -> timeout <= 1.0 s
    sw.set_edge_enabled(True, now=2.0)
    for k in range(3):
        sw.on_edge_result(edge_cmd, now=2.05 + k * 0.05)
    assert sw.select(now=2.20, laptop_result=laptop_cmd)["source"] == "edge"

    # Still within timeout at 2.60 (elapsed 0.45 <= 0.5)
    assert sw.select(now=2.60, laptop_result=laptop_cmd)["source"] == "edge"
    # Past timeout at 2.70 (elapsed 0.55 > 0.50, <= 1.0 s) -> laptop takes over
    sel_to = sw.select(now=2.70, laptop_result=laptop_cmd)
    assert sel_to["source"] == "laptop" and sel_to["fallback_reason"] == "edge_timeout"
    assert sel_to["takeover_latency_s"] <= 1.0

    # 4. Recover edge (3 valid frames), then non-finite edge command triggers immediate fallback
    for k in range(3):
        sw.on_edge_result(edge_cmd, now=2.75 + k * 0.05)
    assert sw.select(now=2.85, laptop_result=laptop_cmd)["source"] == "edge"
    sw.on_edge_result({"v": float("nan"), "w": 0.0}, now=2.90)
    sel_err = sw.select(now=2.90, laptop_result=laptop_cmd)
    assert sel_err["source"] == "laptop" and sel_err["fallback_reason"] == "non_finite_edge_command"
    assert sel_err["takeover_latency_s"] == 0.0
    sw.on_edge_result(edge_cmd, now=2.95)
    sw.on_edge_result(edge_cmd, now=3.00)
    assert sw.select(now=3.00, laptop_result=laptop_cmd)["source"] == "laptop"  # only 2/3 recovery frames
    sw.on_edge_result(edge_cmd, now=3.05)
    assert sw.select(now=3.05, laptop_result=laptop_cmd)["source"] == "edge"

    # 5. Bad timeout_s > 1.0 s is refused at construction
    with pytest.raises(ValueError):
        edge_obs.FallbackSwitch(timeout_s=1.2)


def test_laptop_fallback_controller_seamless_handover_with_real_explorer():
    cam_path = ROOT / "calib" / "camera.json"
    pose_path = ROOT / "calib" / "camera_pose_nowedge.json"
    det_laptop = ObstacleDetector.from_config(
        config_path=ROOT / "config.toml",
        predictor=lambda _img: [Detection(56, 0.9, (180.0, 220.0, 260.0, 380.0))],
        camera_pose_path=pose_path,
        camera_path=cam_path,
        floor_type="unknown",
    )
    blank = np.zeros((480, 640, 3), dtype=np.uint8)
    ctrl = EdgeFallbackController(Explorer(ExploreSettings(), det_laptop.geometry.size), timeout_s=0.4)

    # Edge active at t=1.0
    obs1 = det_laptop(blank, t=1.0, mode="explore", floor_type="unknown")
    r1 = ctrl.step(
        now=1.0,
        dt=0.05,
        pose=(0.0, 0.0, 0.0),
        laptop_obs=obs1,
        edge_result={"v": 0.55, "w": 0.0, "state": "FORWARD", "reason": "clear"},
    )
    assert r1["source"] == "edge"

    # Edge drops out -> at t=1.45 (> 0.4 s) laptop Explorer takes over and still blocks on the low left box
    obs2 = det_laptop(blank, t=1.45, mode="explore", floor_type="unknown")
    r2 = ctrl.step(now=1.45, dt=0.05, pose=(0.0, 0.0, 0.0), laptop_obs=obs2, edge_result=None)
    assert r2["source"] == "laptop" and r2["fallback_active"] is True
    assert r2["takeover_latency_s"] <= 1.0
    assert r2["state"] == "TURN" and r2["v"] == 0.0 and r2["w"] < 0.0


def test_decode_raw_yolo_matches_stage_a_parity_class_aware_nms():
    """Verify jetson.obstacle_layer.decode_raw_yolo matches tools.stage_a_parity.decode (class-aware NMS, clipping)."""
    from tools import stage_a_parity as stage

    raw = np.zeros((84, 2100), np.float32)
    raw[:4, :3] = np.array([[160, 160, 160], [160, 160, 160], [50, 50, 50], [80, 80, 80]])
    raw[4 + 56, 0] = 0.90  # chair
    raw[4 + 56, 1] = 0.80  # duplicate chair -> suppressed by NMS
    raw[4 + 57, 2] = 0.70  # overlapping couch -> must survive class-aware NMS

    frame = {"letterbox": [0.5, 0, 40], "size": [640, 480]}
    settings = {"confidence": 0.25, "class_ids": [56, 57], "nms_iou": 0.7}
    expected = stage.decode(raw, frame, settings)
    actual = edge_obs.decode_raw_yolo(raw[None], scale=0.5, px=0, py=40, image_size=(640, 480), classes=[56, 57])

    assert [d["class_id"] for d in actual] == [d.class_id for d in expected] == [56, 57]
    for a, e in zip(actual, expected):
        assert a["xyxy"] == pytest.approx(e.xyxy)
        assert a["confidence"] == pytest.approx(e.confidence)

    # step_raw consumes raw TensorRT (1, 84, 2100) end-to-end and outputs legal commands
    cam_path = ROOT / "calib" / "camera.json"
    pose_path = ROOT / "calib" / "camera_pose_nowedge.json"
    layer = edge_obs.EdgeObstacleLayer(edge_obs.EdgeCameraModel.from_files(str(cam_path), str(pose_path)), {"floor_type": "unknown"})
    out = layer.step_raw(raw[None], (0.5, 0, 40), t=1.0, dt=0.05)
    assert out["legal"] is True and out["blocked"] is True and out["state"] == "TURN"

