import math

import pytest

from sentry.nav.tower_avoid import TowerAvoid, TowerAvoidConfig
from sentry.nav.wheel_model import WheelModel


def run(tower_xy, period=1 / 30, y0=0.0, obstacle_at=None, seconds=30.0):
    """Robot from (0, y0, 0) drives forward (the caller's command) until the manoeuvre starts; returns (TowerAvoid, pose at the end, closest tower distance)."""
    m, ta = WheelModel(), TowerAvoid()
    x, y, yaw, t, cmd, closest = 0.0, y0, 0.0, 0.0, (0.5, 0.0), 9.0
    prev_t = 0.0
    while t < seconds:
        dx, dy = tower_xy[0] - x, tower_xy[1] - y
        rng = math.hypot(dx, dy)
        brg = math.degrees(math.atan2(dy, dx) - yaw)
        brg = (brg + 180) % 360 - 180
        closest = min(closest, rng)
        seen = (rng, brg) if rng <= 1.3 and abs(brg) <= 75 else None
        obs = 0.2 if (obstacle_at is not None and ta.phase == obstacle_at) else None
        out = ta.step(t, seen, obs)
        if out is None:
            if ta.count or ta.aborted:
                break
            cmd = (0.5, 0.0)
        else:
            cmd = out[:2]
        # what the robot does until the next frame: the command stays on the wire 0.25 s (a yaw-only one 0.08 s)
        fresh = 0.08 if (cmd[0] == 0.0 and cmd[1] != 0.0) else 0.25
        v_m, w_r = m.body_speeds(*cmd)
        t_next = t + period
        for k in range(int(min(period, fresh) / 0.005)):
            x += v_m * math.cos(yaw) * 0.005
            y += v_m * math.sin(yaw) * 0.005
            yaw += w_r * 0.005
            closest = min(closest, math.hypot(tower_xy[0] - x, tower_xy[1] - y))
        t = t_next
    return ta, (x, y, math.degrees(yaw)), closest


@pytest.mark.parametrize("period", [1 / 30, 0.15])
@pytest.mark.parametrize("y_tower", [0.0, 0.1, -0.1])
def test_passes_and_returns_to_heading(period, y_tower):
    ta, (x, y, yaw), closest = run((1.2, y_tower), period)
    assert ta.count == 1 and not ta.aborted
    assert abs(yaw) < 8.0                                  # back on the original heading
    assert closest > 0.6                                   # never nearer than the pursuit keep-out plus margin
    assert [e["event"] for e in ta.events] == ["TURN_AWAY", "SIDESTEP", "TURN_BACK", "CLEAR", "DONE"]


def test_turns_away_from_the_tower_side():
    left = run((1.2, 0.3))[0].events[0]                    # tower to the left -> turn right (negative)
    right = run((1.2, -0.3))[0].events[0]
    assert left["turn_deg"] < 0 < right["turn_deg"]
    assert abs(left["turn_deg"]) < 90 and abs(right["turn_deg"]) < 90        # 90 deg minus the bearing


def test_obstacle_aborts_with_a_stop():
    ta, _, _ = run((1.2, 0.0), obstacle_at="SIDESTEP")
    assert ta.aborted and ta.events[-1]["event"] == "ABORT" and ta.count == 0


def test_one_noisy_frame_does_not_start():
    ta = TowerAvoid()
    assert ta.step(0.0, (0.5, 5.0)) is None and ta.step(0.03, None) is None and ta.step(0.06, (0.5, 5.0)) is None


def test_dead_zone_command_refused():
    with pytest.raises(ValueError):
        TowerAvoid(TowerAvoidConfig(drive_v=0.2))
