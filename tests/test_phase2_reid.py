import numpy as np
import pytest

from sentry.app.phase2_pipeline import OSNetAppearanceExtractor, Phase2Pipeline
from sentry.app.state_machine import State


def test_missing_real_appearance_does_not_queue_synthetic_target():
    pipeline = Phase2Pipeline()
    with pytest.raises(RuntimeError, match='provide OSNet'):
        pipeline.process_entry('missing', [])
    assert len(pipeline.target_queue.all_history()) == 0
    assert pipeline.state_machine.state == State.STANDBY


def test_phase2_adapter_uses_shared_encoder_and_preserves_provenance(monkeypatch):
    from sentry.perception.reid import OSNetEncoder
    vector = np.zeros(512, np.float32)
    vector[10] = 1
    class Encoder:
        model_id = 'osnet_test:sha256'
        def encode(self, crops):
            assert len(crops) == 1 and crops[0].shape == (256, 128, 3)
            return vector[None]
    monkeypatch.setattr(OSNetEncoder, 'from_config', lambda *a, **kw: Encoder())
    extractor = OSNetAppearanceExtractor()
    pipeline = Phase2Pipeline(appearance_extractor=extractor)
    with pytest.raises(ValueError, match='uint8 BGR'):
        pipeline.process_entry('no_crop', [])
    assert not pipeline.target_queue.all_history()
    result = pipeline.process_entry('valid', [], person_crop_bgr=np.ones((256, 128, 3), np.uint8))
    assert np.array_equal(result.record.appearance_vector, vector)
    assert result.record.metadata['appearance_model_id'] == extractor.model_id
    assert result.record.metadata['appearance_simulated'] is False
    assert pipeline.target_queue.active_target.id == 'valid'


def test_real_model_failure_is_propagated(monkeypatch):
    from sentry.perception.reid import OSNetEncoder
    def missing(*a, **kw):
        raise FileNotFoundError('missing checkpoint')
    monkeypatch.setattr(OSNetEncoder, 'from_config', missing)
    with pytest.raises(FileNotFoundError):
        OSNetAppearanceExtractor()
