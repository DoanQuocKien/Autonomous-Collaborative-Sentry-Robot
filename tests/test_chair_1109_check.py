import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest


@pytest.fixture
def chair():
    path = Path(__file__).resolve().parents[1] / "reports/DoanQuocKien/week-06/experiment_B/scripts/chair_1109_check.py"
    spec = importlib.util.spec_from_file_location("chair_1109_check", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_frames(chair, root):
    for tag, tape in chair.SETS:
        folder = root / tag / "frames"
        folder.mkdir(parents=True)
        assert cv2.imwrite(str(folder / "one.jpg"), np.zeros((480, 640, 3), np.uint8))


def test_output_is_explicit_and_existing_evidence_is_never_overwritten(chair, monkeypatch, tmp_path):
    output = tmp_path / "evidence.json"
    original = b'{"historical": true}\n'
    output.write_bytes(original)
    monkeypatch.setattr(chair, "build_model", lambda *args: pytest.fail("must not load model"))
    with pytest.raises(SystemExit):
        chair.main([])
    with pytest.raises(FileExistsError):
        chair.main(["--out", str(output)])
    assert output.read_bytes() == original


@pytest.mark.parametrize("available_sets", [0, 1, 2])
def test_missing_frame_sets_abort_before_model_loading_or_output(chair, monkeypatch, tmp_path, available_sets):
    frames = tmp_path / "frames"
    for tag, tape in chair.SETS[:available_sets]:
        folder = frames / tag / "frames"
        folder.mkdir(parents=True)
        cv2.imwrite(str(folder / "one.jpg"), np.zeros((4, 4, 3), np.uint8))
    output = tmp_path / "result.json"
    monkeypatch.setattr(chair, "build_model", lambda *args: pytest.fail("must validate all input first"))
    with pytest.raises(ValueError, match="no chair frames"):
        chair.main(["--frames-root", str(frames), "--out", str(output)])
    assert not output.exists()


def test_corrupt_frame_does_not_create_output(chair, monkeypatch, tmp_path):
    write_frames(chair, tmp_path / "frames")
    (tmp_path / "frames" / chair.SETS[-1][0] / "frames/one.jpg").write_bytes(b"corrupt")
    output = tmp_path / "result.json"
    monkeypatch.setattr(chair, "build_model", lambda *args: pytest.fail("must validate all images first"))
    with pytest.raises(ValueError, match="unreadable chair frame"):
        chair.main(["--frames-root", str(tmp_path / "frames"), "--out", str(output)])
    assert not output.exists()


@pytest.fixture
def fake_inference(chair, monkeypatch, tmp_path):
    write_frames(chair, tmp_path / "frames")
    model = SimpleNamespace()
    model.cuda = model.eval = lambda: model
    monkeypatch.setattr(chair, "build_model", lambda *args: model)
    geom = SimpleNamespace(undistort=lambda frame: frame, ground_point=lambda u, v: SimpleNamespace(forward_m=1.26, left_m=0.0))
    monkeypatch.setattr(chair.CameraGeometry, "from_files", lambda *args: geom)
    pred = np.ones((720, 960), np.uint8)
    pred[300:350, 450:500] = 2
    monkeypatch.setattr(chair, "predict", lambda *args: pred)
    monkeypatch.setattr(chair, "free_space_segments", lambda *args: [])
    return tmp_path / "frames"


def test_successful_run_writes_new_numeric_results_and_preserves_old_file(chair, fake_inference, tmp_path):
    old = tmp_path / "historical.json"
    old.write_text("old evidence")
    output = tmp_path / "rerun/result.json"
    chair.main(["--frames-root", str(fake_inference), "--out", str(output)])
    result = json.loads(output.read_text())
    assert old.read_text() == "old evidence"
    for tape in ("1.2", "1.8", "2.4"):
        assert result["obstacle"][tape]["frames_with_a_lane_prediction"] == 1
        assert result["obstacle"][tape]["nearest_forward_m_median"] == 1.26
        assert result["freespace"][tape]["frames"] == 1
        assert result["freespace"][tape]["nearest_forward_m_median"] is None


def test_output_created_during_inference_is_not_overwritten(chair, fake_inference, monkeypatch, tmp_path):
    output = tmp_path / "result.json"
    predict = chair.predict
    def competing_write(*args):
        output.write_text("another run's evidence")
        return predict(*args)
    monkeypatch.setattr(chair, "predict", competing_write)
    with pytest.raises(FileExistsError):
        chair.main(["--frames-root", str(fake_inference), "--out", str(output)])
    assert output.read_text() == "another run's evidence"
