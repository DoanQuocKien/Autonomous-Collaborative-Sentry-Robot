import numpy as np

from tools.bench_entrance import auc, inliers, logistic


def test_auc_perfect_chance_and_ties():
    assert auc(np.array([3.0, 4.0]), np.array([1.0, 2.0])) == 1.0
    assert auc(np.array([1.0, 2.0]), np.array([3.0, 4.0])) == 0.0
    assert auc(np.array([1.0, 1.0]), np.array([1.0, 1.0])) == 0.5          # all tied: chance
    assert abs(auc(np.array([1.0, 3.0]), np.array([2.0, 2.5])) - 0.5) < 1e-9


def test_inliers_counts_a_consistent_homography_and_ignores_outliers():
    rng = np.random.default_rng(0)
    p0 = rng.uniform(0, 600, (60, 2))
    p1 = p0 + [12.0, -7.0]
    p1[:10] = rng.uniform(0, 600, (10, 2))                                 # 10 wrong matches
    assert 45 <= inliers(p0, p1) <= 52
    assert inliers(p0[:5], p1[:5]) == 2.0                                  # too few matches to fit: half of them, as a weak score


def test_logistic_probe_separates_two_clouds_and_generalises_to_new_points():
    import torch
    rng = np.random.default_rng(1)
    x = np.vstack([rng.normal(1, 1, (80, 8)), rng.normal(-1, 1, (160, 8))])   # unbalanced classes
    y = np.array([True] * 80 + [False] * 160)
    xt = np.vstack([rng.normal(1, 1, (50, 8)), rng.normal(-1, 1, (50, 8))])
    s = logistic(torch, x, y, xt)
    assert auc(s[:50], s[50:]) > 0.95
