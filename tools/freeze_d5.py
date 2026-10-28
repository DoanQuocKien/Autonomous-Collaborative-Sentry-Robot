"""Freeze a development checkpoint/class list and export ONNX opset 11.

The artifact remains development-only until independent D5 T1 and robot T2 pass.
This command does not change the live obstacle configuration or build TRT engines.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np

from tools.train_d5 import CLASSES, inspect_dataset


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dataset_provenance(yaml_path):
    info = inspect_dataset(yaml_path)
    root = Path(info['dataset_root'])
    manifest = root / 'split_manifest.csv'
    rows = list(csv.DictReader(manifest.open(encoding='utf-8-sig', newline='')))
    if not rows or any(not r.get('session') for r in rows):
        raise ValueError('capture sessions required in split_manifest.csv')
    image_hashes, label_hashes, counts = [], [], {}
    digest = hashlib.sha256()
    for row in sorted(rows, key=lambda r: r['new_image']):
        image, label = ((root / row[k]).resolve() for k in ('new_image', 'new_label'))
        if not image.is_relative_to(root) or not label.is_relative_to(root):
            raise ValueError('split manifest path outside dataset')
        ih, lh = sha256(image), sha256(label)
        image_hashes.append(ih)
        label_hashes.append(lh)
        digest.update((row['new_image'] + ':' + ih + ':' + lh + ':' + row['session']).encode())
        counts[row['split']] = counts.get(row['split'], 0) + 1
    return dict(capture_sessions=sorted({r['session'] for r in rows}), images=len(rows), split_counts=counts,
                image_sha256=image_hashes, labels_sha256=label_hashes,
                dataset_sha256=digest.hexdigest(), split_manifest_sha256=sha256(manifest),
                evaluation_tier='INTERNAL_DEVELOPMENT_SAME_SESSION_NOT_T1')


def run(weights, yaml_path, out_dir, imgsz=640, export=True):
    from ultralytics import YOLO
    weights, out_dir = Path(weights), Path(out_dir)
    if out_dir.exists():
        raise FileExistsError('choose a new artifact directory; frozen releases are immutable')
    provenance = dataset_provenance(yaml_path)
    model = YOLO(str(weights))
    names = model.names
    names = list(names.values()) if isinstance(names, dict) else list(names)
    if names != CLASSES:
        raise ValueError('checkpoint class list/order differs from D5')
    if imgsz not in (320, 416, 640):
        raise ValueError('expected one of the compared model input sizes')
    out_dir.mkdir(parents=True)
    frozen = out_dir / 'd5_candidate.pt'
    shutil.copyfile(weights, frozen)
    manifest = dict(status='FROZEN_DEVELOPMENT_CANDIDATE_NOT_DEPLOYMENT', deployment_ready=False,
                    classes=CLASSES, input_size=imgsz, weights_sha256=sha256(frozen),
                    provenance=provenance, independent_t1_passed=False, trt_parity_passed=False,
                    limitations=['wire target not met', 'no independent D5 session', 'no hardware T2'],
                    motor_commands_sent=0)
    if export:
        import onnx
        import onnxruntime as ort
        import torch
        from ultralytics.cfg import DEFAULT_CFG_DICT
        precision = {'quantize': 32} if 'quantize' in DEFAULT_CFG_DICT else {'half': False}
        exported = YOLO(str(frozen)).export(format='onnx', imgsz=imgsz, batch=1, opset=11,
                                           dynamic=False, simplify=False, nms=False, device='cpu', **precision)
        exported = Path(exported)
        graph = onnx.load(str(exported))
        onnx.checker.check_model(graph)
        if max(i.version for i in graph.opset_import if i.domain in ('', 'ai.onnx')) > 11:
            raise ValueError('TensorRT7 recipe requires opset <=11')
        session = ort.InferenceSession(str(exported), providers=['CPUExecutionProvider'])
        network = YOLO(str(frozen)).model.cpu().float().eval()
        rng = np.random.default_rng(532)
        parity = []
        for image in (np.zeros((1, 3, imgsz, imgsz), np.float32), rng.random((1, 3, imgsz, imgsz), dtype=np.float32)):
            with torch.inference_mode():
                reference = network(torch.from_numpy(image))
            reference = reference[0] if isinstance(reference, tuple) else reference
            reference = reference.cpu().numpy()
            actual = session.run(None, {session.get_inputs()[0].name: image})[0]
            if reference.shape != actual.shape or not np.isfinite(actual).all():
                raise ValueError('ONNX output shape/finite mismatch')
            a, b = reference.astype(np.float64).ravel(), actual.astype(np.float64).ravel()
            cosine = float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))
            max_abs = float(np.max(np.abs(a - b)))
            parity.append(dict(cosine=cosine, max_abs=max_abs))
            if cosine < .999:
                raise RuntimeError('PyTorch/ONNX export parity failed')
        manifest.update(onnx_sha256=sha256(exported), onnx_opset=11,
                        export_smoke_parity=parity,
                        export_scope='two synthetic inputs; not D1/real-image or TRT decoded-box parity')
    (out_dir / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--weights', required=True)
    ap.add_argument('--data', required=True)
    ap.add_argument('--out-dir', required=True)
    ap.add_argument('--imgsz', type=int, choices=(320, 416, 640), default=640)
    a = ap.parse_args()
    manifest = run(a.weights, a.data, a.out_dir, a.imgsz)
    print(json.dumps({k: manifest[k] for k in ('status', 'deployment_ready', 'weights_sha256')}, indent=2))


if __name__ == '__main__':
    main()
