import math

import pytest

from common.protocol import encode_control
from tools.floor_model import FloorSim, load, wheel_model


def test_floor_model_speed_turn_drift_and_latency():
    fm = load()
    m = wheel_model(fm, 11.5)
    v, _ = m.body_speeds(0.55, 0.0)
    assert v == pytest.approx(1.64 * (0.165 - fm["wheel"]["m0_at_11_5"]), rel=1e-6)          # the wheel law at the fitted offset
    assert m.body_speeds(0.0, 0.45)[1] == pytest.approx(fm["turn"]["rate_rad_per_s_at_w_0_45"])  # the measured spin rate
    with pytest.raises(ValueError):
        wheel_model(fm, 10.9)                                                                    # outside the measured battery range
    sim, t, dt = FloorSim(fm, 11.5), 0.0, 0.02
    for i in range(50):                                                                          # 1 s at v = 0.55
        sim.on_packet(encode_control(i, 0.55, 0.0), t)
        sim.step(t, dt)
        t += dt
    assert sim.x == pytest.approx(v, rel=0.02)
    assert sim.theta == pytest.approx(fm["drift"]["sim_rad_per_m"] * v, rel=0.02)             # heading drifts left by the drift per metre
    seen = sim.camera_pose(t)
    assert seen is not None and seen[0] < sim.x and math.isclose(seen[0], v * (1.0 - fm["video"]["sim_latency_s"]), rel_tol=0.05)
