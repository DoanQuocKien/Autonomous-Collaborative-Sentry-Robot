from sentry.perception import tower_markers as tm


def test_tower_heights_and_tilt():
    assert set(tm.TOWER) == {10, 11, 12, 13}
    assert abs(tm.bottom_h(12) - 0.008) < 1e-9 and abs(tm.bottom_h(11) - 0.0045) < 1e-9
    assert tm.tilt_deg(13) == 0.0 and tm.tilt_deg(12) > 4.0 and tm.tilt_deg(11) < 0.0


def test_placement_gate_needs_a_steady_in_window_marker():
    g = tm.PlacementGate(range_m=(0.2, 0.3), bearing_deg=15.0, hold_s=1.0)
    for k in range(20):                                   # 2 s at 10 Hz, inside the window
        g.update(k * 0.1, (0.25, -8.0))
        if k < 9:
            assert not g.ok(k * 0.1)                      # not yet held for 1 s
    assert g.ok(1.9)
    assert not g.ok(3.0)                                  # no longer seen: stale
    g2 = tm.PlacementGate()
    for k in range(30):
        g2.update(k * 0.1, (0.25, -8.0) if k % 5 else None)   # one dropout (no marker) in five does not break the 0.7 s freshness
    assert g2.ok(2.9)
    g3 = tm.PlacementGate()
    for k in range(30):
        g3.update(k * 0.1, (0.45, 0.0))                   # too far
    assert not g3.ok(2.9)
    g4 = tm.PlacementGate()
    for k in range(13):
        g4.update(k * 0.1, (0.25, -8.0))
    assert g4.ok(1.2)
    g4.update(1.3, (0.6, 40.0))                           # seen, but knocked out of the window: revoked at once
    assert not g4.ok(1.3)


def test_the_front_marker_is_rotated_180_and_its_corners_are_reordered():
    c = [(0, 0), (1, 0), (1, 1), (0, 1)]
    assert tm.upright(10, c).tolist() == [list(p) for p in c]                 # upright faces are untouched
    assert tm.upright(11, c).tolist() == [[1, 1], [0, 1], [0, 0], [1, 0]]    # id 11: rotated by two
