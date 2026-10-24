import cv2
import numpy as np
import pytest

from tools.enroll_whitelist import enroll


class FakeEncoder:
    def __init__(self):
        self.count = 0

    def extract(self, image):
        self.count += 1
        vector = np.zeros(512, dtype=np.float32)
        vector[self.count] = 2.0
        return [{"embedding": vector}]


def test_enroll_keeps_all_embeddings(tmp_path):
    images = []

    for i in range(3):
        path = tmp_path / f"photo{i}.jpg"
        cv2.imwrite(str(path), np.zeros((64, 64, 3), np.uint8))
        images.append(path)

    output = tmp_path / "member01.npz"

    enroll("member01", images, output, encoder=FakeEncoder())

    with np.load(output, allow_pickle=False) as data:
        embeddings = data["embeddings"]

    assert embeddings.shape == (3, 512)
    np.testing.assert_allclose(
        np.linalg.norm(embeddings, axis=1),
        np.ones(3),
    )
    assert not np.array_equal(embeddings[0], embeddings[1])


def test_rejects_insufficient_photos(tmp_path):
    with pytest.raises(ValueError):
        enroll("member01", ["a.jpg"], tmp_path / "member01.npz")

from sentry.perception.face import FaceVerifier, load_whitelist


def test_saved_enrollment_can_be_verified(tmp_path):
    image_paths = []

    for i in range(3):
        path = tmp_path / f"photo{i}.jpg"
        cv2.imwrite(
            str(path),
            np.zeros((64, 64, 3), dtype=np.uint8),
        )
        image_paths.append(path)

    folder = tmp_path / "whitelist"

    enroll(
        "member01",
        image_paths,
        folder / "member01.npz",
        encoder=FakeEncoder(),
    )

    whitelist = load_whitelist(folder)
    verifier = FaceVerifier(whitelist, threshold=0.45)

    query = np.zeros(512, dtype=np.float32)
    query[2] = 1.0

    person_id, score, authorized = verifier.verify(query)

    assert authorized
    assert person_id == "member01"
    assert score == pytest.approx(1.0)


def test_rejects_invalid_whitelist_shape(tmp_path):
    folder = tmp_path / "whitelist"
    folder.mkdir()

    np.savez_compressed(
        folder / "invalid.npz",
        embeddings=np.zeros((2, 512), dtype=np.float32),
    )

    with pytest.raises(ValueError):
        load_whitelist(folder)
