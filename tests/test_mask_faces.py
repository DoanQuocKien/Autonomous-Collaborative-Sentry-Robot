from tools.mask_faces import head_box


def test_head_patch_covers_the_top_of_a_person_and_not_the_legs():
    x1, y1, x2, y2 = 100, 40, 160, 180
    hb = head_box((x1, y1, x2, y2), 640, 480)
    assert hb[1] == y1 and hb[3] < y1 + 0.5 * (y2 - y1)      # legs start at about half the box
    assert hb[0] < x1 and hb[2] > x2


def test_boxes_that_are_not_a_standing_head_are_skipped():
    assert head_box((100, 2, 160, 180), 640, 480) is None      # cut by the top border
    assert head_box((100, 40, 120, 60), 640, 480) is None      # too small (a shoe)
    assert head_box((100, 300, 300, 400), 640, 480) is None    # wider than tall (lying leg)
