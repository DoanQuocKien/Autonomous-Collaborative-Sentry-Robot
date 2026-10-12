from pathlib import Path

import pytest

from tools.check_w2 import run


@pytest.mark.gpu
def test_real_local_yolo_and_calibrated_projection(tmp_path, monkeypatch):
    if not Path("data/models/yolov8n.pt").is_file():
        pytest.skip("needs fetched local YOLO weights")
    settings_dir = tmp_path / "ultralytics"
    settings_dir.mkdir()
    monkeypatch.setenv("YOLO_CONFIG_DIR", str(settings_dir))
    result = run("calib/camera_pose_nowedge_raw.jpg", tmp_path / "smoke.json", warmup=0, iterations=1)
    assert result["passed"] and result["actual_device"].startswith("cuda")
    assert len(result["weights_sha256"]) == 64 and result["motor_commands_sent"] == 0
    assert result["latency_p95_ms"] > 0
    assert result["precision"] == "FP32"
