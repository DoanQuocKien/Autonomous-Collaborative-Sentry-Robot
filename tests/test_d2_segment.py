import numpy as np

from tools import d2_segment


def rows(frames, cx=320.0, width=60.0):
    return [{"frame": f, "cx": cx, "width": width} for f in frames]


def test_side_thirds_of_a_640_wide_image():
    assert d2_segment.side(50) == "L" and d2_segment.side(320) == "C" and d2_segment.side(600) == "R"


def test_segment_splits_runs_at_gaps_and_takes_the_first_side():
    r = rows([5, 6, 7, 9]) + rows([30, 31, 32], cx=100.0, width=80.0) + rows([60], cx=580.0)
    e = d2_segment.segment(r, max_gap=3)
    assert [(x["first"], x["last"], x["frames"], x["direction"]) for x in e] == [(5, 9, 4, "C"), (30, 32, 3, "L"), (60, 60, 1, "R")]
    assert e[1]["max_width"] == 80.0


def test_one_frame_is_still_an_entry_and_no_frames_no_entry():
    assert len(d2_segment.segment(rows([12]))) == 1
    assert d2_segment.segment([]) == []


def test_sharpness_is_lower_for_a_blurred_crop():
    import cv2
    rng = np.random.RandomState(0)
    img = (rng.rand(120, 120, 3) * 255).astype(np.uint8)
    blurred = cv2.GaussianBlur(img, (15, 15), 5)
    box = [0, 0, 120, 120]
    assert d2_segment.sharpness(img, box) > d2_segment.sharpness(blurred, box)
