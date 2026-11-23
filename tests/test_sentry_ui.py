"""TowerWizard says why it does not accept a face (no robot, no camera)."""
import numpy as np

from tools.sentry_ui import TowerWizard, render

K = np.array([[300.0, 0, 320], [0, 300.0, 240], [0, 0, 1]])
SQ = np.array([[100, 100], [140, 100], [140, 140], [100, 140]], float)


def test_rejection_reasons_and_render():
    w = TowerWizard(K)
    w.update([])
    assert w.level == "bad" and "No marker" in w.msg
    w.update([(3, SQ)])
    assert "none is a tower face" in w.msg
    w.update([(10, SQ), (12, SQ)])
    assert "Two tower faces" in w.msg
    w.done[10] = dict(pitch_deg=-11.0, spread_deg=0.1, distance_m=0.3, offset_to_ref_m=None)
    w.update([(10, SQ)])
    assert "already registered" in w.msg
    img = render(np.zeros((480, 640, 3), np.uint8), [(10, SQ)], w, "tower", "x", 20.0, 0.1, True, K, 0.1)
    assert img.shape[1] == 1060 and img.any()
    assert render(None, [], w, "live", "x", 0.0, None, True, K, 0.1).any()
