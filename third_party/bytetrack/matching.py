import numpy as np
from scipy.optimize import linear_sum_assignment


def linear_assignment(cost_matrix, thresh):
    if cost_matrix.size == 0:
        return (
            np.empty((0, 2), dtype=int),
            tuple(range(cost_matrix.shape[0])),
            tuple(range(cost_matrix.shape[1])),
        )

    # Use scipy linear_sum_assignment (always available, standard SciPy)
    # If lap.lapjv is installed, we can optionally use it, but scipy is identical and robust.
    row_ind, col_ind = linear_sum_assignment(cost_matrix)
    matches = []
    unmatched_a = list(range(cost_matrix.shape[0]))
    unmatched_b = list(range(cost_matrix.shape[1]))

    for r, c in zip(row_ind, col_ind):
        if cost_matrix[r, c] <= thresh:
            matches.append([r, c])
            if r in unmatched_a:
                unmatched_a.remove(r)
            if c in unmatched_b:
                unmatched_b.remove(c)

    if len(matches) == 0:
        matches = np.empty((0, 2), dtype=int)
    else:
        matches = np.asarray(matches, dtype=int)

    return matches, tuple(unmatched_a), tuple(unmatched_b)


def ious(atlbrs, btlbrs):
    """Compute pairwise IoU between two sets of [x1, y1, x2, y2] boxes."""
    ious_mat = np.zeros((len(atlbrs), len(btlbrs)), dtype=np.float32)
    if ious_mat.size == 0:
        return ious_mat

    atlbrs = np.ascontiguousarray(atlbrs, dtype=np.float32)
    btlbrs = np.ascontiguousarray(btlbrs, dtype=np.float32)

    for i in range(len(atlbrs)):
        box_a = atlbrs[i]
        area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
        if area_a <= 0:
            continue

        ix1 = np.maximum(box_a[0], btlbrs[:, 0])
        iy1 = np.maximum(box_a[1], btlbrs[:, 1])
        ix2 = np.minimum(box_a[2], btlbrs[:, 2])
        iy2 = np.minimum(box_a[3], btlbrs[:, 3])

        iw = np.maximum(0.0, ix2 - ix1)
        ih = np.maximum(0.0, iy2 - iy1)
        inter = iw * ih

        area_b = (btlbrs[:, 2] - btlbrs[:, 0]) * (btlbrs[:, 3] - btlbrs[:, 1])
        union = area_a + area_b - inter
        union = np.maximum(union, 1e-6)
        ious_mat[i, :] = inter / union

    return ious_mat


def iou_distance(atracks, btracks):
    """Compute cost matrix based on 1 - IoU."""
    if (len(atracks) > 0 and isinstance(atracks[0], np.ndarray)) or (
        len(btracks) > 0 and isinstance(btracks[0], np.ndarray)
    ):
        atlbrs = atracks
        btlbrs = btracks
    else:
        atlbrs = [track.tlbr for track in atracks]
        btlbrs = [track.tlbr for track in btracks]

    _ious = ious(atlbrs, btlbrs)
    cost_matrix = 1.0 - _ious
    return cost_matrix


def fuse_score(cost_matrix, detections):
    if cost_matrix.size == 0:
        return cost_matrix
    iou_sim = 1.0 - cost_matrix
    det_scores = np.array([det.score for det in detections])
    det_scores = np.expand_dims(det_scores, axis=0).repeat(cost_matrix.shape[0], axis=0)
    fuse_sim = iou_sim * det_scores
    fuse_cost = 1.0 - fuse_sim
    return fuse_cost
