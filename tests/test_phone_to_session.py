import json

import cv2
import numpy as np
import pytest

from tools.phone_to_session import convert
from tools.prepare_d3_recording import audit


def _clip(path, n=60, fps=60.0, size=(160, 90)):
    w = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), fps, size)
    for i in range(n):
        w.write(np.full((size[1], size[0], 3), i * 4 % 255, np.uint8))
    w.release()


def test_converts_to_an_auditable_session_with_the_clock_mapped(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    clip = tmp_path / "c.avi"
    _clip(clip)
    info = convert(clip, data / "s", t0=1000.0, fps=30.0, width=80, data_root=data)
    assert info["frames"] == 30                                  # 60 frames at 60 fps, decimated to 30 fps
    rows = [json.loads(line) for line in (data / "s" / "jetbot_meta.jsonl").read_text().splitlines()]
    assert rows[0]["t_local"] == 1000.0 and rows[0]["w"] == 80 and rows[0]["h"] == 45
    assert rows[5]["t_local"] == pytest.approx(1000.0 + 5 / 30.0) and rows[5]["t_cap"] == pytest.approx(5 / 30.0)
    _, _, epochs = audit(data / "s", data)                       # the same audit detect_lunges runs
    assert len(epochs) == 1 and len(epochs[0]) == 30


def test_refuses_outside_data_and_existing_output(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    clip = tmp_path / "c.avi"
    _clip(clip, n=6)
    with pytest.raises(ValueError):
        convert(clip, tmp_path / "elsewhere", 0.0, data_root=data)
    convert(clip, data / "s", 0.0, data_root=data)
    with pytest.raises(FileExistsError):
        convert(clip, data / "s", 0.0, data_root=data)
