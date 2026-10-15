import random

import numpy as np

from tools.speedfit import fit_start, model, window_speeds
from tools.turn_test import nominal_deg, plan_pulses, servo


def test_fit_recovers_the_steady_speed_and_the_startup_lag_from_noisy_ranges():
    rng = np.random.default_rng(0)
    t = np.arange(0, 9, 1 / 17)
    true = (1.95, 0.22, 0.4, 3.0)                                  # d0, S, tau, t0
    d = model(true, t) + rng.normal(0, 0.01, len(t))
    f = fit_start(t, d)
    assert abs(f["S"] - 0.22) < 0.02 and abs(f["tau"] - 0.4) < 0.25 and abs(f["t0"] - 3.0) < 0.3 and f["rms"] < 0.03
    assert fit_start(t[:5], d[:5]) is None                          # too few samples: no guess
    ws = window_speeds(t, d)
    assert 0.18 < ws[:, 1].max() < 0.26


def test_turn_pulses_are_planned_with_a_deadband_of_half_a_packet_and_converge_on_a_fake_plant():
    nom = nominal_deg(6.48)
    assert abs(nom - 6.19) < 0.05
    assert plan_pulses(2.0, nom) == (0.0, 0) and plan_pulses(4.0, nom)[1] == 1 and plan_pulses(-25.0, nom) == (-0.5, 4)
    for rate, start in ((nom, 25.0), (0.7 * nom, -30.0), (1.3 * nom, 12.0)):
        st, rnd = {"b": start}, random.Random(1)
        cy = servo(lambda: st["b"] + rnd.gauss(0, 0.2), lambda w, n: st.update(b=st["b"] - (1 if w > 0 else -1) * n * rate * (1 + rnd.gauss(0, 0.05))), lambda: None, nom, log=lambda s: None)
        assert abs(st["b"]) < 0.65 * nom and len(cy) <= 6, (rate, start, st)


def test_pulses_the_robot_log_says_did_not_move_are_not_counted():
    nom = nominal_deg(6.48)
    st, calls = {"b": 20.0}, {"n": 0}

    def pulse(w, n):
        calls["n"] += 1
        if calls["n"] == 1:
            return 0.0                                              # R1 not held: the wheels did not move
        st["b"] -= n * nom
        return n / 30.0

    logs = []
    cy = servo(lambda: st["b"], pulse, lambda: None, nom, log=logs.append)
    assert any("R1 not held" in s for s in logs) and all(c[3] > 0.5 * nom for c in cy)


def test_heading_track_follows_a_turn_through_several_markers_without_drift():
    import math
    from tools.turn_trial import heading_track
    dirs = {0: 0.0, 1: 55.0, 2: 110.0, 3: 165.0, 4: 220.0}                  # room directions of 5 markers (deg, left +)
    frames = []
    for k in range(60):                                                      # a left turn of 200 deg in 60 frames, the camera sees +-45 deg
        th = 200.0 * k / 59
        frames.append((k / 17.0, {i: d - th for i, d in dirs.items() if abs(d - th) < 45}))
    out = heading_track(frames)
    assert all(h is not None for _, h, _ in out)
    assert abs(out[-1][1] - 200.0) < 3.0 and max(abs(h - 200.0 * k / 59) for k, (_, h, _) in enumerate(out)) < 3.0
    gap = [(0.0, {0: 10.0}), (0.1, {}), (0.2, {7: 5.0})]                     # all known markers gone, then only an unknown one: no heading is invented
    assert [h for _, h, _ in heading_track(gap)][1:] == [None, None]
