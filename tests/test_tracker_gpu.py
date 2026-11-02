from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


@pytest.mark.gpu
def test_real_yolo_bytetrack_osnet_pipeline_runs_offline_cuda(monkeypatch):
    torch = pytest.importorskip('torch')
    if not torch.cuda.is_available() or not Path('data/models/yolov8n.pt').is_file() or not Path('weights/osnet_ain_x1_0_dg.pth').is_file():
        pytest.skip('CUDA and local model assets required')
    import urllib.request
    import requests
    def forbidden(*a, **kw):
        raise AssertionError('inference must not download')
    monkeypatch.setattr(urllib.request, 'urlopen', forbidden)
    monkeypatch.setattr(requests.sessions.Session, 'request', forbidden)
    from sentry.perception.tracker import PersonTracker
    tracker = PersonTracker.from_config()
    image = np.random.default_rng(532).integers(0, 256, (480, 640, 3), np.uint8)
    result = tracker(image, 0.)  # real YOLO forward
    assert result.model_id == tracker.encoder.model_id
    assert str(tracker.detector.model.predictor.model.device).startswith('cuda')
    # Deterministic observed box exercises real ByteTrack+OSNet regardless of
    # whether the detector finds a person in synthetic noise; no accuracy claim.
    tracker.reset()
    tracker.detector = lambda im: [SimpleNamespace(class_id=0, confidence=.9, xyxy=(20, 20, 148, 276))]
    first = tracker(image, .1)
    assert len(first.tracks) == 1 and first.tracks[0].embedding.shape == (512,)
    tracker.set_target(first.tracks[0].embedding, first.model_id)
    assert tracker(image, .2).target is None
    assert tracker(image, .3).target is not None
    assert str(next(tracker.encoder.model.parameters()).device).startswith('cuda')
