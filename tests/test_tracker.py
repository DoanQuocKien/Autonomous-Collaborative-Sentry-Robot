from types import SimpleNamespace

import numpy as np
import pytest

from sentry.config import load
from sentry.perception.tracker import ByteTrackBackend, PersonTrack, PersonTracker, TargetLock


def vec(index=0):
    a = np.zeros(512, np.float32)
    a[index] = 1
    return a


def person(tid, embedding, epoch=0):
    return PersonTrack(tid, epoch, (0, 0, 30, 60), .9, embedding)


def test_lock_requires_model_identity_confirmation_and_current_appearance():
    lock = TargetLock('model:a', load()['tracking'])
    assert lock.update([person(1, vec())], 0)[1] == 'UNSET'
    with pytest.raises(ValueError, match='model/hash'):
        lock.set_target(vec(), 'model:b')
    lock.set_target(vec(), 'model:a')
    assert lock.update([person(1, vec())], 0)[0] is None
    assert lock.update([person(1, vec())], .1)[0].track_id == 1
    # Same ByteTrack ID was assigned to someone else: do not trust its ID.
    assert lock.update([person(1, vec(1))], .2)[0] is None
    # Reacquire a changed ID after occlusion only with fresh appearance and confirmation.
    assert lock.update([], .3)[1] == 'LOST'
    assert lock.update([], 4)[1] == 'SEARCHING'
    assert lock.update([person(9, vec())], 4.1)[0] is None
    assert lock.update([person(9, vec())], 4.2)[0].track_id == 9
    lock.clear()
    assert lock.update([person(9, vec())], 5)[1] == 'UNSET'


def test_ambiguous_people_never_win_by_order_and_same_id_reacquisition_is_confirmed():
    lock = TargetLock('m', dict(load()['tracking'], lock_margin=0.))
    lock.set_target(vec(), 'm')
    for t in range(4):
        assert lock.update([person(1, vec()), person(2, vec())], t)[0] is None
    assert lock.update([person(1, vec())], 5)[0] is None
    assert lock.update([person(1, vec())], 6)[0] is not None
    lock.update([], 6.1)
    assert lock.update([person(1, vec())], 6.2)[0] is None


def test_real_bytetrack_uses_low_confidence_matches_and_does_not_emit_lost_predictions():
    backend = ByteTrackBackend(load()['tracking'])
    first = backend.update([[10, 10, 40, 80, .9, 0]], (100, 100))
    assert len(first) == 1
    low = backend.update([[11, 10, 41, 80, .15, 0]], (100, 100))
    assert len(low) == 1 and low[0][4] == first[0][4]
    assert len(backend.update([], (100, 100))) == 0
    back = backend.update([[12, 10, 42, 80, .9, 0]], (100, 100))
    assert len(back) == 1 and back[0][4] == first[0][4]


def test_pipeline_clips_boxes_retains_low_scores_and_resets_stream_epoch():
    cfg = load()
    class Encoder:
        model_id = 'e:hash'
        def encode(self, crops):
            return np.stack([vec() for _ in crops])
    class Backend:
        resets = 0
        def reset(self):
            self.resets += 1
        def update(self, rows, shape):
            assert len(rows) == 1 and rows[0][:4] == [0., 0., 40, 70]
            assert rows[0][4] == .15
            return [[*rows[0][:4], 1, .15, 0, 0]]
    backend = Backend()
    detector = lambda img: [SimpleNamespace(class_id=0, confidence=.15, xyxy=(-5, -3, 40, 70)),
                            SimpleNamespace(class_id=0, confidence=.9, xyxy=(0, 0, 1, 1)),
                            SimpleNamespace(class_id=1, confidence=.9, xyxy=(0, 0, 40, 70))]
    tracker = PersonTracker(detector, Encoder(), cfg['tracking'], cfg['reid'], backend)
    with pytest.raises(ValueError, match='real Phase2'):
        tracker.set_target_record(SimpleNamespace(appearance_vector=vec(), metadata={'appearance_simulated': True}))
    tracker.set_target_record(SimpleNamespace(appearance_vector=vec(), metadata={
        'appearance_simulated': False, 'appearance_model_id': 'e:hash'}))
    image = np.zeros((100, 100, 3), np.uint8)
    assert tracker(image, 0).target is None
    assert tracker(image, .1).target.track_id == 1
    for t in (.1, 0, float('nan')):
        with pytest.raises(ValueError, match='timestamps'):
            tracker(image, t)
    gap = tracker(image, 3)
    assert gap.epoch == 1 and gap.target is None and backend.resets == 1
    assert tracker(image, 3.1).target.key == (1, 1)
    tracker.reset()
    assert tracker(image, 0).epoch == 2


@pytest.mark.parametrize('patch', [{'max_frame_gap_s': float('inf')}, {'track_low_thresh': .9},
                                  {'confirm_frames': 0}, {'lock_similarity': float('nan')}])
def test_invalid_tracking_settings_rejected(patch):
    cfg = load()
    cfg['tracking'].update(patch)
    with pytest.raises(ValueError):
        PersonTracker(None, SimpleNamespace(model_id='m'), cfg['tracking'], cfg['reid'], object())
