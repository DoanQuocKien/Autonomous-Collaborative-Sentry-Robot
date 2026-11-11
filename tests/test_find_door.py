import math

from tools.find_door import dominant_bearing


def test_dominant_cluster_beats_the_median_of_false_sightings():
    true = [(math.radians(-48 + d), 30) for d in (-2, -1, 0, 1, 2, 0, 1)]                 # the door, seen at several stops
    false = [(math.radians(a), 28) for a in (140, 262, 175, 100)]                           # the detector firing elsewhere
    b, n, total, second = dominant_bearing(true + false)
    assert abs(b - (-48)) < 2 and n == 7 and total == 11 and second <= 1


def test_wraps_around_180_and_handles_none():
    d = [(math.radians(a), 30) for a in (178, -179, 179, -178)]
    b, n, _, _ = dominant_bearing(d)
    assert n == 4 and abs(abs(b) - 180) < 2
    assert dominant_bearing([]) == (None, 0, 0, 0)
