from tools.label_background_legs import iou, leg_box


def test_standing_person_gives_the_lower_part_as_legs():
    lb = leg_box((100, 40, 160, 180), 640, 480)     # 60 x 140: standing
    assert lb[0] == 100 and lb[2] == 160 and lb[3] == 180 and lb[1] > 40 + 0.5 * 140


def test_seated_cut_small_boxes_are_skipped():
    assert leg_box((100, 40, 220, 160), 640, 480) is None     # wider than 1 / 1.8 of its height: seated
    assert leg_box((100, 2, 160, 180), 640, 480) is None      # cut by the top border
    assert leg_box((100, 40, 120, 70), 640, 480) is None      # too small
    assert iou((0, 0, 10, 10), (5, 5, 15, 15)) < 0.2
