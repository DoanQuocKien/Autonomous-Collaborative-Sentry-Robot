import pytest

from sentry.nav.evasion import EvasionOverride


def test_pulse_runs_for_the_duration_then_stops_and_cools_down():
    e = EvasionOverride(-1.0, 0.8, 0.4, 1.0)
    assert e.step(0.0) is None
    assert e.trigger(10.0, obstacle_bearing_rad=None)
    assert e.step(10.0) == (-1.0, 0.8)
    assert e.step(10.39) == (-1.0, 0.8)
    assert e.step(10.4) is None                       # exactly the duration: over
    assert not e.trigger(10.9)                        # cooldown runs from the pulse END (10.4) to 11.4
    assert e.trigger(11.4) and e.count == 2 and e.rejected == 1


def test_second_strike_during_a_pulse_is_ignored_and_does_not_extend_it():
    e = EvasionOverride()
    assert e.trigger(0.0)
    assert not e.trigger(0.2)
    assert e.step(0.41) is None


def test_turns_away_from_the_nearer_obstacle_side():
    e = EvasionOverride(-1.0, 0.8, 0.4, 0.0)
    e.trigger(0.0, obstacle_bearing_rad=0.5)          # obstacle on the left -> yaw right
    assert e.step(0.1) == (-1.0, -0.8)
    e.trigger(1.0, obstacle_bearing_rad=-0.5)         # obstacle on the right -> yaw left
    assert e.step(1.1) == (-1.0, 0.8)


def test_stalled_video_cannot_stretch_the_pulse():
    e = EvasionOverride()
    e.trigger(5.0)
    assert e.step(5.2) is not None
    assert e.step(7.0) is None                        # the next call, a long time later, is already over


@pytest.mark.parametrize("kw", [dict(v=0.5), dict(v=-1.5), dict(w=0.0), dict(w=1.5), dict(duration_s=0.0), dict(duration_s=2.0), dict(cooldown_s=-1.0)])
def test_illegal_values_are_refused(kw):
    with pytest.raises(ValueError):
        EvasionOverride(**kw)


def test_config_values_are_the_state_machines():
    e = EvasionOverride.from_toml()
    assert (e.v, e.w, e.duration_s, e.cooldown_s) == (-1.0, 0.8, 0.4, 1.0)
