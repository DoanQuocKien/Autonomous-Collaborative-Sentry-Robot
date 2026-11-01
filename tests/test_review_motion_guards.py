import json
from types import SimpleNamespace

import pytest

from sentry.nav.wheel_model import WheelModel
from tools.motion_check import KINDS, fit, verdict


def test_incomplete_or_nonfinite_motion_never_passes():
    assert not verdict([])[0]
    rows = [dict(name=k, kind=k, measurable=True, ratio=1., drift_rad_per_m=0.) for k in KINDS]
    assert verdict(rows)[0]
    rows[0]['ratio'] = float('nan')
    assert not verdict(rows)[0] and fit(rows, WheelModel())[0] is None
    rows[0]['ratio'] = 1.
    rows[-1]['drift_rad_per_m'] = None
    assert not verdict(rows)[0] and fit(rows, WheelModel())[0] is None


@pytest.mark.parametrize('patch', [{'usable': False}, {'scale': -1}, {'w_scale_right': float('nan')}])
def test_withdrawn_or_invalid_session_is_refused(tmp_path, patch):
    d = dict(scale=1., w_scale_left=1., w_scale_right=1., drift_rad_per_m=0., **{})
    d.update(patch)
    p = tmp_path / 'session.json'
    p.write_text(json.dumps(d))
    with pytest.raises(ValueError):
        WheelModel.from_session(p)


def test_marker_median_drops_old_positions(monkeypatch):
    from sentry.nav import marker_fix as mf
    from sentry.nav.localization import RobotPose
    import collections
    fixer = mf.MarkerFix.__new__(mf.MarkerFix)
    fixer._pose0, fixer.anchors, fixer.max_range_m = RobotPose, {1: object()}, 1.5
    fixer.recent, fixer.max_age_s, fixer.n = collections.deque(maxlen=5), 1., 0
    class Tracker:
        anchors = fixer.anchors
        def detect_markers(self, frame):
            return [SimpleNamespace(marker_id=1, distance_m=1.)]
        def update_with_markers(self, frame, alpha):
            self.pose = RobotPose(x=float(frame), y=0., theta=0.)
            self.corrections_count = 1
    fixer.tr = Tracker()
    clock = iter([0., .2, 2.])
    monkeypatch.setattr(mf.time, 'monotonic', lambda: next(clock))
    fixer.measure(0.)
    assert fixer.measure(2.)[1] == 1.
    assert fixer.measure(10.)[1] == 10.
