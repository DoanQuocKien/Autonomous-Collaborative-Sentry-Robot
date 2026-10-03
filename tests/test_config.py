from sentry.config import load


def test_spec_constants_have_not_drifted():
    t = load()["thresholds"]
    assert (t["obstacle_explore_m"], t["obstacle_pursuit_m"]) == (0.6, 0.5)
    assert t["whitelist_cosine"] == 0.45
    assert (t["entrance_min_m"], t["entrance_max_m"]) == (1.5, 3.0)
    assert (t["standoff_m"], t["orbit_radius_m"]) == (1.2, 1.0)
    assert (t["stationary_speed_mps"], t["stationary_time_s"]) == (0.1, 2.0)
    assert (t["strike_area_growth"], t["strike_window_s"]) == (0.40, 0.1)
    assert (t["evade_v"], t["evade_w"], t["evade_duration_s"]) == (-1.0, 0.8, 0.4)


def test_ports_match_protocol():
    from common import protocol
    n = load()["net"]
    assert (n["video_port"], n["control_port"], n["clock_port"]) == (
        protocol.PORT_VIDEO, protocol.PORT_CONTROL, protocol.PORT_CLOCK)
