import numpy as np
import pytest

from sentry.perception.face import FaceVerifier, normalize_embedding


def vector(index):
    v = np.zeros(512, dtype=np.float32)
    v[index] = 1.0
    return v


def test_normalize_embedding():
    v = normalize_embedding(vector(0) * 5)
    assert np.linalg.norm(v) == pytest.approx(1.0)


def test_known_face():
    verifier = FaceVerifier({
        "person_A": [vector(0), vector(1)],
        "person_B": [vector(2)],
    })

    person_id, score, authorized = verifier.verify(vector(1))

    assert authorized
    assert person_id == "person_A"
    assert score == pytest.approx(1.0)


def test_unknown_face():
    verifier = FaceVerifier({"person_A": [vector(0)]})

    person_id, score, authorized = verifier.verify(vector(3))

    assert not authorized
    assert person_id is None
    assert score == pytest.approx(0.0)


def test_invalid_embedding():
    with pytest.raises(ValueError):
        normalize_embedding(np.zeros(512))
from types import SimpleNamespace

from sentry.perception.face import InsightFaceEncoder


def test_extract_face_with_fake_backend():
    class FakeApp:
        def get(self, image):
            return [
                SimpleNamespace(
                    bbox=np.array([10, 20, 100, 120]),
                    det_score=0.95,
                    embedding=vector(0) * 5,
                )
            ]

    encoder = InsightFaceEncoder(app=FakeApp())
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    faces = encoder.extract(frame)

    assert len(faces) == 1
    assert faces[0]["confidence"] == pytest.approx(0.95)
    assert len(faces[0]["embedding"]) == 512
    assert np.linalg.norm(faces[0]["embedding"]) == pytest.approx(1.0)


def test_extract_rejects_invalid_image():
    encoder = InsightFaceEncoder(app=object())

    with pytest.raises(ValueError):
        encoder.extract(np.zeros((480, 640), dtype=np.uint8))