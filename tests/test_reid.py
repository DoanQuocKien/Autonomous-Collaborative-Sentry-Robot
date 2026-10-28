from types import SimpleNamespace

import numpy as np
import pytest

from sentry.config import load
from sentry.perception.obstacle import Detection
from sentry.perception.reid import PersonReID, crop_person, match_gallery, normalize, preprocess


def basis(i):
    return np.eye(512, dtype=np.float32)[i]


@pytest.mark.parametrize('value', [np.zeros(512), np.ones(511), np.full(512, np.nan), np.full(512, np.inf)])
def test_invalid_vectors_rejected(value):
    with pytest.raises(ValueError):
        normalize(value)


def test_max_cosine_gallery_and_unknown_and_tie():
    assert match_gallery(basis(1), {'A': [basis(0), basis(1)], 'B': [basis(2)]}, .7) == ('A', 1.)
    assert match_gallery(basis(3), {'A': [basis(1)]}, .7)[0] is None
    assert match_gallery(basis(1), {'A': [basis(1)], 'B': [basis(1)]}, .7)[0] is None
    assert match_gallery(basis(1), {}, .7) == (None, None)


def test_crop_clips_boxes_and_preserves_input():
    image = np.zeros((100, 80, 3), np.uint8)
    crop = crop_person(image, (-20, -10, 40.2, 90.1))
    assert crop.shape == (91, 41, 3)
    crop[:] = 255
    assert not image.any()
    assert crop_person(image, (100, 100, 200, 200)) is None
    assert crop_person(image, (0, 0, 4, 4)) is None
    with pytest.raises(ValueError):
        crop_person(image, (0, 0, np.nan, 5))


def test_preprocessing_bgr_to_rgb_normalization_and_shape():
    s = load()['reid']
    crop = np.zeros((64, 32, 3), np.uint8)
    crop[..., 2] = 255
    got = preprocess([crop], s)
    assert got.shape == (1, 3, 256, 128)
    assert got[0, :, 0, 0] == pytest.approx((np.array([1, 0, 0]) - s['mean']) / s['std'])
    assert preprocess([], s).shape == (0, 3, 256, 128)


def test_frame_to_reid_dataclass_filter_crop_reject_and_no_global_state():
    s = load()['reid']
    seen = []
    def encode(crops):
        seen.extend(crops)
        return np.stack([basis(1)] * len(crops))
    encoder = SimpleNamespace(encode=encode, model_id='fixture-sha')
    detector = lambda im: [Detection(0, .9, (10, 10, 50, 90)), Detection(0, .8, (0, 0, 2, 2)),
                          Detection(56, .99, (1, 1, 30, 90)), Detection(0, .1, (1, 1, 50, 90))]
    pipeline = PersonReID(detector, encoder, s)
    result = pipeline(np.zeros((100, 80, 3), np.uint8), 12.5)
    assert len(seen) == 1 and len(result.people) == 2 and result.t == 12.5
    assert result.model_id == 'fixture-sha' and np.allclose(result.people[0].embedding, basis(1))
    assert result.people[1].rejection == 'crop_too_small_or_outside'
    with pytest.raises(ValueError):
        pipeline(np.zeros((100, 80, 3), np.uint8), float('nan'))


def test_encoder_count_mismatch_is_an_error():
    pipeline = PersonReID(lambda im: [Detection(0, .9, (0, 0, 50, 80))],
                         SimpleNamespace(encode=lambda crops: [], model_id='fixture'), load()['reid'])
    with pytest.raises(ValueError, match='count'):
        pipeline(np.zeros((100, 80, 3), np.uint8), 0)
