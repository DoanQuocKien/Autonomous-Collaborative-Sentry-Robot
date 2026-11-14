from tools.door_recognition_seq import summarize


def row(window, a, b=None):
    return {"window": window, "scores": {"A": a, "B": b}}


def test_tar_far_and_misses():
    rows = [row("1.8_straight", 0.6, 0.1), row("1.8_straight", 0.5, 0.5),   # genuine hit; second frame: impostor B also passes
            row("1.8_straight", None, None),                                  # no face: a TAR miss, no impostor score
            row("1.8_away", 0.2, 0.1), row("2.4_straight", 0.3, 0.0)]         # 2.4 m: own score below the threshold
    r = summarize(rows, "A", 0.45)
    d18, d24 = r["per_distance"]["1.8"], r["per_distance"]["2.4"]
    assert d18["tar"] == round(2 / 3, 4) and d18["straight_detected"] == 2
    assert d18["far"] == 0.5 and d18["impostor_scores"] == 2 and d18["impostor_max"] == 0.5
    assert d18["away_frames"] == 1 and d18["away_detected"] == 1 and d18["away_own_ge_thr"] == 0
    assert d24["tar"] == 0.0
    assert r["tar"] == 0.5 and r["far"] == round(1 / 3, 4)


def test_single_subject_has_no_far():
    r = summarize([{"window": "1.8_straight", "scores": {"A": 0.7}}], "A")
    assert r["tar"] == 1.0 and r["far"] is None


def test_pose_qc_counts():
    rows = [{"window": "1.8_straight", "scores": {"A": 0.6}, "yaw": 0.05}, {"window": "1.8_straight", "scores": {"A": 0.6}, "yaw": 0.7},
            {"window": "1.8_away", "scores": {"A": 0.1}, "yaw": -0.5}, {"window": "1.8_away", "scores": {"A": None}, "yaw": None}]
    d = summarize(rows, "A")["per_distance"]["1.8"]
    assert d["straight_frontal"] == 1 and d["away_turned"] == 1
