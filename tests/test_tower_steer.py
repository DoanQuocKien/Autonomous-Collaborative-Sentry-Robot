import math

import pytest

from sentry.nav.tower_avoid import TowerAvoid, TowerAvoidConfig, TowerSteer
from sentry.nav.wheel_model import WheelModel


def run(tower_xy, period=1 / 30, drift=0.0, miss=0.0, seed=1, obstacle=None):
    """Robot from (0, 0, 0) drives forward (caller command) until TowerSteer takes over. drift: rad/s of yaw the floor adds. miss: probability a frame loses the marker."""
    import random
    rnd = random.Random(seed)
    m, ts = WheelModel(), TowerSteer(TowerAvoidConfig())
    x = y = yaw = t = 0.0
    cmd, closest = (0.5, 0.0), 9.0
    while t < 30.0:
        dx, dy = tower_xy[0] - x, tower_xy[1] - y
        rng = math.hypot(dx, dy)
        brg = (math.degrees(math.atan2(dy, dx) - yaw) + 180) % 360 - 180
        seen = (rng, brg) if rng <= 1.3 and abs(brg) <= 78 and rnd.random() >= miss else None
        out = ts.step(t, seen, obstacle)
        if out is None:
            if ts.count or ts.aborted:
                break
            cmd = (0.5, 0.0)
        else:
            cmd = out[:2]
        fresh = 0.08 if (cmd[0] == 0.0 and cmd[1] != 0.0) else 0.25
        v_m, w_r = m.body_speeds(*cmd)
        for _ in range(int(min(period, fresh) / 0.005)):
            x += v_m * math.cos(yaw) * 0.005
            y += v_m * math.sin(yaw) * 0.005
            yaw += (w_r + drift) * 0.005
            closest = min(closest, math.hypot(tower_xy[0] - x, tower_xy[1] - y))
        t += period
    return ts, (x, y, math.degrees(yaw)), closest


@pytest.mark.parametrize("period", [1 / 30, 0.15])
@pytest.mark.parametrize("y_tower", [0.0, 0.08, -0.08, 0.2])
@pytest.mark.parametrize("drift", [0.0, 0.15, -0.15])      # 0.15 rad/s ~ the 40-70 deg per 1.3 m veer of the dorm floor
def test_passes_the_tower(period, y_tower, drift):
    ts, (x, y, yaw), closest = run((1.4, y_tower), period, drift)
    assert ts.count == 1 and not ts.aborted
    assert closest > 0.28                                # clearance 0.35 m minus what the last frame's lag allows
    h = math.radians(yaw)
    assert (1.4 - x) * math.cos(h) + (y_tower - y) * math.sin(h) < 0      # the tower is behind the robot along its final heading (it ends turned away, pursuit re-locks the person)


def test_marker_dropouts():
    ts, _, closest = run((1.4, 0.1), miss=0.5)
    assert ts.count == 1 and closest > 0.25


def test_side_follows_the_tower_side():
    ts, (_, y, _), _ = run((1.4, 0.15))
    assert ts.events[0]["tower_side"] == "left" and y < 0.15 - 0.2
    ts, (_, y, _), _ = run((1.4, -0.15))
    assert ts.events[0]["tower_side"] == "right" and y > -0.15 + 0.2


def test_obstacle_aborts():
    ts, _, _ = run((1.4, 0.1), obstacle=0.2)
    assert ts.aborted and not ts.count


@pytest.mark.parametrize('strategy', [TowerAvoid, TowerSteer])
def test_critical_obstacle_stops_the_trigger_frame(strategy):
    avoid = strategy()
    assert avoid.step(0.0, (0.8, 0.0), 0.2) is None
    assert avoid.step(0.1, (0.8, 0.0), 0.2) == (0.0, 0.0, 'ABORT')
    assert avoid.aborted and avoid.count == 0
