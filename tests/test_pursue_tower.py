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
