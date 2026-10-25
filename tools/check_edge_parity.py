"""Edge Conversion Parity Evaluation Harness (Week 3, HNHL).

Defines the mathematical validation functions (cosine similarity, box IoU)
and parity test harness for evaluating ONNX / TensorRT engines against
PyTorch / ONNX Runtime FP32 baselines across the 200-frame D1 obstacle parity set.
(Implementation Plan line 251, §4.3).
"""
import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional
import numpy as np

ROOT = Path(__file__).resolve().parent.parent


def compute_cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two feature arrays."""
    a_flat = a.flatten().astype(np.float32)
    b_flat = b.flatten().astype(np.float32)
    norm_a = np.linalg.norm(a_flat)
    norm_b = np.linalg.norm(b_flat)
    if norm_a < 1e-12 or norm_b < 1e-12:
        return 0.0
    return float(np.dot(a_flat, b_flat) / (norm_a * norm_b))


def compute_iou(box1: tuple, box2: tuple) -> float:
    """Compute Intersection-over-Union (IoU) between two bounding boxes."""
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area1 = max(0.0, box1[2] - box1[0]) * max(0.0, box1[3] - box1[1])
    area2 = max(0.0, box2[2] - box2[0]) * max(0.0, box2[3] - box2[1])
    union = area1 + area2 - intersection
    return float(intersection / union) if union > 0 else 0.0


def collect_parity_images(max_frames=200) -> List[Path]:
    """Collect 200 real obstacle frames without faces from D1 session 1015."""
    images = []
    d1_dir = ROOT / "data" / "dqk-obstacles-2026-10-15"
    if d1_dir.is_dir():
        for sub in ("chairs_a", "chairs_b", "chairs_c", "empty_1", "set2", "set3", "set4"):
            folder = d1_dir / sub
            if folder.is_dir():
                images.extend(sorted(folder.glob("*.jpg")))
                if len(images) >= max_frames:
                    break
    return images[:max_frames]


def write_parity_harness_spec(out_path: Optional[Path] = None) -> Dict:
    """Generate specification for Edge Conversion Parity verification."""
    parity_frames = collect_parity_images(200)

    spec = {
        "status": "HARNESS_READY_PENDING_ENGINE_BUILD",
        "evaluated_on_real_engines": False,
        "parity_frames_collected": len(parity_frames),
        "target_thresholds": {
            "cosine_similarity": 0.999,
            "detector_box_iou": 0.90,
            "box_match_min_fraction": 0.95,
        },
        "models_to_evaluate": [
            "yolov8n_320.onnx",
            "scrfd_2.5g_320.onnx",
            "w600k_mbf.onnx",
            "osnet_x0_25_256x128.onnx",
            "xfeat_backbone_480x640.onnx",
        ],
        "note": "Parity evaluation tooling and frame sampling are ready. Real comparison requires building TensorRT engines on the Jetson Nano using tools.export_edge_onnx exports.",
    }

    if out_path:
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(spec, indent=2), encoding="utf-8")
        print(f"Parity specification written to {out}")

    return spec


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="reports/HuynhNguyenHoaiLoc/week-03/edge_parity_metrics.json")
    args = parser.parse_args()
    write_parity_harness_spec(Path(args.out))


if __name__ == "__main__":
    main()
