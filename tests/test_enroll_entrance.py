from tools.enroll_entrance import split_manifest


def row(pos, visible):
    return {"position_id": str(pos), "door_visible": visible}


def test_split_manifest_drops_the_reference_position_and_calibrates_on_the_first_negative_positions():
    rows = [row(2, "yes")] * 3 + [row(3, "yes")] * 2 + [row(14, "no")] * 2 + [row(15, "no")] + [row(16, "no")] * 2 + [row(17, "no")]
    calib, test = split_manifest(rows)
    assert {r["position_id"] for r in calib} == {"14", "15"}
    assert {r["position_id"] for r in test} == {"3", "16", "17"}              # position 2 (the reference) is in neither
