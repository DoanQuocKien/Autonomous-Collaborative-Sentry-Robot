"""Optional real-model integration; skip explicitly when offline assets are absent."""
from pathlib import Path

import cv2
import pytest


@pytest.mark.gpu
def test_issue43_optional_models_execute_offline_on_cuda(monkeypatch):
    torch = pytest.importorskip('torch')
    pytest.importorskip('transformers')
    if not torch.cuda.is_available():
        pytest.skip('CUDA required for the Issue #43 runtime evidence')
    for name in ('data/models/segformer-b0-ade/model.safetensors', 'data/models/obstacles-world.pt'):
        if not Path(name).is_file():
            pytest.skip('fetch optional weights with tools.fetch_floor_model --world')
    import requests
    import urllib.request
    from sentry.perception.obstacle import ObstacleDetector

    def forbidden(*args, **kwargs):
        raise AssertionError('inference attempted a network download')

    monkeypatch.setattr(urllib.request, 'urlopen', forbidden)
    monkeypatch.setattr(requests.sessions.Session, 'request', forbidden)
    detector = ObstacleDetector.from_config(
        camera_pose_path='assets/d1/obstacles_2026-10-15/camera_pose_classroom_1015.json',
        floor_type='glossy', semantic_floor=True, open_vocabulary=True)
    image = cv2.imread('assets/d1/obstacles_2026-10-15/chairs_a/000030.jpg')
    result = detector(image, 1)
    assert result.ground_points
    assert any(o.contact and o.contact.method == 'semantic_floor_edge' for o in result.obstacles)
    assert str(next(detector.floor.predictor.model.parameters()).device).startswith('cuda')
    assert str(detector.world.model.predictor.model.device).startswith('cuda')
    assert next(detector.floor.predictor.model.parameters()).dtype == torch.float32
    assert not detector.world.model.predictor.model.fp16
