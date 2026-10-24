"""Tests for D5 dataset and fine-tuning benchmarks (Week 3, HNHL)."""
from pathlib import Path
import pytest

from tools.train_d5 import CLASSES, benchmark_resolutions, generate_d5_yaml


def test_d5_yaml_generation(tmp_path):
    yaml_file = tmp_path / "test_d5.yaml"
    generate_d5_yaml(yaml_file)

    assert yaml_file.exists()
    content = yaml_file.read_text(encoding="utf-8")
    for cls in CLASSES:
        assert cls in content


def test_benchmark_resolutions_metrics():
    bench = benchmark_resolutions()
    assert "yolov8n_320" in bench["models"]
    assert "yolov8n_416" in bench["models"]
    assert "yolov8n_640" in bench["models"]

    # 320 meets Jetson Nano target (< 20ms)
    m320 = bench["models"]["yolov8n_320"]
    assert m320["jetson_nano_latency_ms"] < 20.0
    assert m320["mAP50"] > 0.75

    # 640 has highest accuracy
    m640 = bench["models"]["yolov8n_640"]
    assert m640["mAP50"] >= m320["mAP50"]
