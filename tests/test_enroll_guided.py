import numpy as np

from tools.enroll_guided import POSES, check, save, turn_hint, yaw_ratio


def kps(nose_dx):
    """Eyes 40 px apart at y=100, nose offset nose_dx px from the midpoint, mouth below."""
    return np.array([[80, 100], [120, 100], [100 + nose_dx, 125], [85, 150], [115, 150]], dtype=float)


def face(nose_dx=0.0, width=120, conf=0.9):
    return {"bbox": (50, 50, 50 + width, 50 + width), "confidence": conf, "kps": kps(nose_dx)}


def textured():
    return np.random.RandomState(0).randint(0, 255, (300, 400, 3)).astype(np.uint8)


def test_yaw_ratio_sign_and_scale():
    assert yaw_ratio(kps(0)) == 0.0
    assert yaw_ratio(kps(10)) == 0.25           # nose to the image's right = person's left
    assert yaw_ratio(kps(-10)) == -0.25


def test_pose_gates():
    img, straight, left = textured(), POSES[0][1], POSES[1][1]
    assert check(face(0), img, straight, 100) is None
    assert "closer" in check(face(0, width=80), img, straight, 100)
    assert check(face(0, conf=0.3), img, straight, 100) == "face not clear"
    assert check(face(10), img, left, 100) is None          # 0.25 is inside the left-turn range
    assert check(face(0), img, left, 100) == "turn a little more"
    assert check(face(-10), img, left, 100) == "turn the other way"
    assert check(face(25), img, left, 100) == "turn a little less"
    assert check(face(10), img, straight, 100) == "look straight at the camera"


def test_save_is_loadable_and_never_overwrites(tmp_path):
    from sentry.perception.face import load_whitelist
    vec = [np.eye(512, dtype=np.float32)[i] for i in range(5)]
    save("TEST", vec, tmp_path)
    assert list(load_whitelist(tmp_path)) == ["TEST"]
    try:
        save("TEST", vec, tmp_path)
        assert False, "second save must refuse"
    except FileExistsError:
        pass
