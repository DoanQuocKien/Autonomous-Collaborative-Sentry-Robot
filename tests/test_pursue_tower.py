from sentry.nav.controllers import HoldBehaviorConfig, InterceptionController, PursuitConfig
from sentry.nav.hold_detector import HoldConfig
from sentry.nav.wheel_model import WheelModel
from tools.pursue_live import Pursuit


def make():
    ctl = InterceptionController(PursuitConfig.from_toml(), HoldBehaviorConfig.from_toml(), HoldConfig.from_toml())
    return Pursuit(ctl, WheelModel(), lambda u, v: None, lambda pts: pts, (640, 480))


def test_avoid_rows_move_the_pose_and_the_target_is_forgotten_after():
    p = make()
    p.target_id, p.t_seen = 7, 0.0
    p.avoid_step(0.0, 0.5, 0.0, "SIDESTEP")
    p.avoid_step(0.1, 0.5, 0.0, "SIDESTEP")
    assert p.rows[-1]["mode"] == "TOWER_SIDESTEP" and p.pose[0] > 0.0          # the dead-reckoned pose followed the command
    p.resume_after_avoid(5.0)
    assert p.target_id is None and p.t_seen is None and p.rows[-1]["event"] == "TOWER_RESUME"
    assert p.summary()["frames_tower_avoid"] == 2


def test_search_spins_towards_the_last_side_and_only_when_enabled():
    p = make()
    p.t_seen, p.target_id, p._search_dir = 0.0, 7, -1.0
    assert p.update(0.2, [])[1] == 0.0                       # lost for 0.2 s: still just stopped
    assert p.rows[-1]["mode"] == "NO_TARGET"
    p.search_w = 0.5
    ws = [p.update(1.0 + 0.03 * i, [])[1] for i in range(6)]
    assert p.rows[-1]["mode"] == "SEARCH" and p.target_id is None
    assert any(w == -0.5 for w in ws) and all(w in (0.0, -0.5) for w in ws)        # pulses, right (the person was last seen on the right)
    p.lost_end_s = 5.0
    p.t_seen = 0.0
    p.update(6.0, [])
    assert p.end_reason


def test_run_ends_after_a_handover_when_nobody_is_found():
    p = make()
    p.lost_end_s = 5.0
    p.resume_after_avoid(10.0)
    p.update(12.0, [])
    assert not p.end_reason
    p.update(15.5, [])
    assert p.end_reason                                      # counted from the handover, not never


def test_unknown_strategy_is_refused():
    import dataclasses
    import pytest
    from sentry.nav.tower_avoid import TowerAvoidConfig, make_tower_avoid
    with pytest.raises(ValueError):
        make_tower_avoid(dataclasses.replace(TowerAvoidConfig(), strategy="Steer"))
