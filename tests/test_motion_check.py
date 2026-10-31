import json
import math

from sentry.nav.wheel_model import WheelModel
from tools import motion_check as mc

TRUE = WheelModel(scale=0.8, w_scale_left=0.9, w_scale_right=1.2, drift_rad_per_m=-0.10)      # an unlevel floor: slow, uneven turns, bends right


def make_run(seq):
    """Commands at 30 Hz for the plan, and the marker poses a robot that behaves like TRUE would show at every rest."""
    cmds, segments, poses, t, pose = [], [], [(0.0, 0.0, 0.0)], 0.0, (0.0, 0.0, 0.0)
    for name, kind, v, w, seconds in seq:
        t0 = t
        for _ in range(int(seconds * 30)):
            cmds.append((t, v, w))
            t += 1 / 30.0
        segments.append(dict(name=name, kind=kind, t0=t0, t1=t))
        f, l, th = mc.dr_delta(cmds, TRUE, t0, t)
        c, s = math.cos(pose[2]), math.sin(pose[2])
        pose = (pose[0] + f * c - l * s, pose[1] + f * s + l * c, mc.wrap(pose[2] + th))
        poses.append(pose)
        t += 2.5
    return cmds, segments, poses


def test_the_fit_recovers_the_floor_and_the_corrected_model_then_passes_the_check(tmp_path):
    cmds, segments, poses = make_run(mc.plan(2, 0.45, 1.5, 0.55, 3.0))
    rows = mc.analyse(segments, poses, cmds, WheelModel())
    assert not mc.verdict(rows)[0]                                                            # the default model is off by 20 %: the check fails
    session, problems = mc.fit(rows, WheelModel())
    assert not problems and abs(session["scale"] - 0.8) < 0.03 and abs(session["w_scale_right"] - 1.2) < 0.05 and abs(session["w_scale_left"] - 0.9) < 0.05
    assert abs(session["drift_rad_per_m"] + 0.10) < 0.02
    p = tmp_path / "s.json"
    p.write_text(json.dumps(session))
    corrected = WheelModel.from_session(p)
    assert mc.verdict(mc.analyse(segments, poses, cmds, corrected))[0]                         # with the correction the same run matches within 10 %


def test_unmeasurable_segments_do_not_count_and_a_missing_kind_refuses_the_fit():
    cmds, segments, poses = make_run(mc.plan(1, 0.45, 1.5, 0.55, 3.0))
    poses[2] = None                                                                           # no board in view after the right spin: spin_right and the drive after it are lost
    rows = mc.analyse(segments, poses, cmds, WheelModel())
    assert [r["measurable"] for r in rows] == [True, False, False]
    session, problems = mc.fit(rows, WheelModel())
    assert session is None and any("spin_right" in p for p in problems)
