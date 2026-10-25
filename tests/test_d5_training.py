"""T0 tests for correct D5 Week-3 exported-dataset training entrypoint.

No real training or validation is triggered by these unit tests.
"""
from pathlib import Path

import pytest

import tools.train_d5 as train_d5


def _fake_d5_export(tmp_path: Path) -> Path:
    output = tmp_path / "D5 with spaces"
    for split in ("train", "val"):
        (output / "images" / split).mkdir(parents=True)
        (output / "labels" / split).mkdir(parents=True)
        (output / "images" / split / f"sample_{split}.jpg").write_bytes(b"fake image placeholder")
        (output / "labels" / split / f"sample_{split}.txt").write_text(
            "4 0.50 0.50 0.20 0.10\n", encoding="utf-8"
        )
    yaml_file = output / "data.yaml"
    class_names = "\n".join(f"  {i}: {name}" for i, name in enumerate(train_d5.CLASSES))
    yaml_file.write_text(
        f'path: "{output.as_posix()}"\n'
        "train: images/train\nval: images/val\nnames:\n"
        + class_names + "\n", encoding="utf-8"
    )
    return yaml_file


def test_existing_dataset_preflight_is_readonly(tmp_path):
    yaml_path = _fake_d5_export(tmp_path)
    original_bytes = yaml_path.read_bytes()
    info = train_d5.inspect_dataset(yaml_path)
    assert info["train_images"] == 1
    assert info["val_images"] == 1
    assert info["evaluation_tier"].endswith("NOT_T1")
    assert train_d5.prepare_d5_dataset(yaml_path) == yaml_path.resolve()
    assert yaml_path.read_bytes() == original_bytes


def test_rejects_legacy_train_val_dot(tmp_path):
    yaml_path = _fake_d5_export(tmp_path)
    content = yaml_path.read_text(encoding="utf-8")
    yaml_path.write_text(content.replace("train: images/train", "train: ."), encoding="utf-8")
    with pytest.raises(ValueError, match="train: \\."):
        train_d5.inspect_dataset(yaml_path)


def test_rejects_missing_image_label_pair(tmp_path):
    yaml_path = _fake_d5_export(tmp_path)
    (yaml_path.parent / "labels" / "val" / "sample_val.txt").unlink()
    with pytest.raises(ValueError, match="Mismatched val images/labels"):
        train_d5.inspect_dataset(yaml_path)


def test_training_spec_is_not_a_benchmark(tmp_path, monkeypatch):
    yaml_path = _fake_d5_export(tmp_path)
    monkeypatch.setattr(train_d5, "DATASET_YAML", yaml_path)
    out = tmp_path / "plan.json"
    spec = train_d5.write_training_spec(out)
    assert out.exists()
    assert spec["status"] == "TRAINING_HARNESS_READY"
    assert spec["evaluated"] is False
    assert spec["resolutions_to_compare"] == [320, 416, 640]
    assert "mAP50" not in spec
    with pytest.raises(FileExistsError):
        train_d5.write_training_spec(out)
