"""F18 accounting/input guards, without loading GPU models."""
import csv
from pathlib import Path

import pytest
import yaml

from tools.compare_d5_precision import prepare_copy, summarize_latency
from tools.train_d5 import CLASSES


@pytest.mark.parametrize('values', [[], [0], [-1], [float('nan')], [float('inf')]])
def test_invalid_timings_never_produce_fps(values):
    with pytest.raises(ValueError):
        summarize_latency(values)


def test_fps_uses_total_wall_time_rather_than_average_instantaneous_fps():
    result = summarize_latency([10, 30])
    assert result['fps'] == 50 and result['samples'] == 2


def dataset(tmp_path):
    root = tmp_path / 'original'
    for split in ('train', 'val'):
        for kind, ext, content in [('images', 'jpg', b'image'), ('labels', 'txt', b'0 0.5 0.5 0.2 0.2\n')]:
            path = root / kind / split / ('one.' + ext)
            path.parent.mkdir(parents=True)
            path.write_bytes(content)
    config = root / 'data.yaml'
    config.write_text(yaml.safe_dump(dict(path=str(root), train='images/train', val='images/val', names=CLASSES)))
    manifest = root / 'split_manifest.csv'
    with manifest.open('w', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=['split', 'new_image', 'new_label', 'session'])
        writer.writeheader()
        writer.writerow(dict(split='val', new_image='images/val/one.jpg', new_label='labels/val/one.txt', session='1024'))
    return root, config, manifest


def test_validation_copy_preserves_originals_and_uses_only_manifest_val(tmp_path):
    root, config, _ = dataset(tmp_path)
    originals = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
    copied_config, registry = prepare_copy(config, tmp_path / 'copy')
    assert len(registry) == 1 and copied_config.exists()
    assert (tmp_path / 'copy/images/val/one.jpg').read_bytes() == b'image'
    assert not (tmp_path / 'copy/images/train').exists()
    assert all(path.read_bytes() == content for path, content in originals.items())


def test_manifest_cannot_omit_or_duplicate_validation_images(tmp_path):
    _, config, manifest = dataset(tmp_path)
    with manifest.open('a') as fh:
        fh.write('val,images/val/one.jpg,labels/val/one.txt,1024\n')
    with pytest.raises(ValueError, match='count mismatch'):
        prepare_copy(config, tmp_path / 'copy')
