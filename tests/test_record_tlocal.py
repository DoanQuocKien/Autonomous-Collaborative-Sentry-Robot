from tools.record import strictly_after


def test_same_clock_tick_still_strictly_increases():
    a = strictly_after(None, 100.0)
    b = strictly_after(a, 100.0)          # same tick
    c = strictly_after(b, 99.9)           # clock stepped back
    d = strictly_after(c, 101.0)
    assert a < b < c < d == 101.0
