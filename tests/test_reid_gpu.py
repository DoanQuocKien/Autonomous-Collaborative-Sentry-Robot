from pathlib import Path

import numpy as np
import pytest


@pytest.mark.gpu
def test_real_osnet_weights_offline_cuda(monkeypatch):
    torch = pytest.importorskip('torch')
    pytest.importorskip('torchreid')
    if not torch.cuda.is_available():
        pytest.skip('CUDA required')
    for file in ('osnet_ain_x1_0_dg.pth', 'osnet_x0_25_market1501.pth'):
        if not (Path('weights') / file).is_file():
            pytest.skip('fetch local re-ID weights first')
    import urllib.request
    import requests
    from sentry.perception.reid import ARCHITECTURES, OSNetEncoder
    def forbidden(*a, **kw):
        raise AssertionError('OSNet inference attempted a download')
    monkeypatch.setattr(urllib.request, 'urlopen', forbidden)
    monkeypatch.setattr(requests.sessions.Session, 'request', forbidden)
    crop = np.random.default_rng(532).integers(0, 256, (256, 128, 3), np.uint8)
    for architecture in ARCHITECTURES:
        encoder = OSNetEncoder.from_config(architecture)
        first = encoder.encode([crop, crop])
        assert first.shape == (2, 512)
        assert np.isfinite(first).all()
        assert np.linalg.norm(first, axis=1) == pytest.approx([1, 1], abs=1e-5)
        assert np.allclose(first[0], first[1], atol=1e-5)
        assert str(next(encoder.model.parameters()).device).startswith('cuda')
