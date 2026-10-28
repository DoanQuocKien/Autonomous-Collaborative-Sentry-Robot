"""Measure frozen D5 PyTorch/ONNX raw and decoded parity on local real images.

Not a TensorRT/robot test, nor ground-truth accuracy. Uses the same input blob
and Python-3.6 Jetson decoder for both runtimes. Does not save private frames.
"""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from jetson.yolo_post import decode, letterbox
from sentry.perception.world import box_iou
from tools.freeze_d5 import sha256


def decoded_agreement(reference, candidate, iou_limit=.9):
    boxes_a, _, classes_a, _ = reference
    boxes_b, _, classes_b, _ = candidate
    matches = []
    for i, a in enumerate(boxes_a):
        for j, b in enumerate(boxes_b):
            if int(classes_a[i]) == int(classes_b[j]):
                matches.append((box_iou(a, b), i, j))
    used_a, used_b = set(), set()
    for iou, i, j in sorted(matches, reverse=True):
        if iou >= iou_limit and i not in used_a and j not in used_b:
            used_a.add(i)
            used_b.add(j)
    return dict(reference_boxes=len(boxes_a), candidate_boxes=len(boxes_b), matched=len(used_a),
                same_count=len(boxes_a) == len(boxes_b),
                fraction=len(used_a) / max(len(boxes_a), len(boxes_b)) if max(len(boxes_a), len(boxes_b)) else 1.)


def run(artifact_dir, images_dir, out, device='cuda:0'):
    import torch
    import onnxruntime as ort
    from ultralytics import YOLO
    artifact_dir = Path(artifact_dir)
    manifest = json.loads((artifact_dir / 'manifest.json').read_text())
    weights, onnx_path = artifact_dir / 'd5_candidate.pt', artifact_dir / 'd5_candidate.onnx'
    if sha256(weights) != manifest['weights_sha256'] or sha256(onnx_path) != manifest['onnx_sha256']:
        raise ValueError('frozen model hash mismatch')
    images = sorted(p for p in Path(images_dir).iterdir() if p.suffix.lower() in ('.jpg', '.png', '.jpeg'))
    if not images:
        raise ValueError('real parity images required')
    network = YOLO(str(weights)).model.float().to(device).eval()
    session = ort.InferenceSession(str(onnx_path), providers=['CPUExecutionProvider'])
    rows, hashes = [], []
    for path in images:
        image = cv2.imread(str(path))
        if image is None:
            raise ValueError('unreadable parity image')
        blob, scale, px, py = letterbox(image, manifest['input_size'])
        with torch.inference_mode():
            expected = network(torch.from_numpy(blob).to(device))
        expected = expected[0] if isinstance(expected, tuple) else expected
        expected = expected.cpu().numpy()
        actual = session.run(None, {session.get_inputs()[0].name: blob})[0]
        if expected.shape != actual.shape or not np.isfinite(actual).all():
            raise ValueError('raw output shape/finite mismatch')
        a, b = expected.astype(np.float64).ravel(), actual.astype(np.float64).ravel()
        cosine = float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))
        agreement = decoded_agreement(decode(expected, scale, px, py), decode(actual, scale, px, py))
        rows.append(dict(cosine=cosine, max_abs=float(np.max(np.abs(a - b))), **agreement))
        hashes.append(sha256(path))
    report = dict(scope='real-image PyTorch FP32 / ONNX Runtime CPU parity only, not TensorRT or accuracy',
                  frames=len(rows), frame_sha256=hashes, manifest_sha256=sha256(artifact_dir / 'manifest.json'),
                  pytorch_device=str(next(network.parameters()).device), onnx_provider=session.get_providers()[0],
                  cosine_min=min(r['cosine'] for r in rows), max_abs=max(r['max_abs'] for r in rows),
                  total_reference_boxes=sum(r['reference_boxes'] for r in rows),
                  same_count_frames=sum(r['same_count'] for r in rows),
                  box_fraction_min=min(r['fraction'] for r in rows),
                  passed=all(r['cosine'] >= .999 and r['same_count'] and r['fraction'] >= .95 for r in rows)
                         and any(r['reference_boxes'] for r in rows),
                  thresholds=dict(cosine=.999, iou=.9, matched_fraction=.95, confidence=.25),
                  trt_parity_passed=False, motor_commands_sent=0)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--artifact-dir', required=True)
    ap.add_argument('--images-dir', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    report = run(a.artifact_dir, a.images_dir, a.out)
    print(json.dumps({k: report[k] for k in ('frames', 'cosine_min', 'same_count_frames', 'passed')}, indent=2))
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
