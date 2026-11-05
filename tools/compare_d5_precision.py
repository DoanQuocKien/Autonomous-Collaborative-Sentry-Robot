"""Paired native PyTorch CUDA FP32/FP16 D5 development comparison (F18).

Runs each precision in a fresh process; never trains, changes live config, or
claims independent T1, RTX4050, TensorRT, re-ID, or robot acceptance. Original
images/labels/checkpoint are read-only; validator caches go to a private copy.
"""
import argparse
import csv
from datetime import datetime, timezone
import gc
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from unittest.mock import patch

import numpy as np

from tools.freeze_d5 import dataset_provenance, sha256
from tools.train_d5 import CLASSES, inspect_dataset


def precision_options(bits, defaults):
    if bits not in (16, 32):
        raise ValueError('only FP16 and FP32 supported')
    return {'quantize': bits} if 'quantize' in defaults else {'half': bits == 16}


def summarize_latency(samples):
    values = np.asarray(samples, dtype=float)
    if values.ndim != 1 or not len(values) or not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError('nonempty finite positive latency samples required')
    return dict(samples=len(values), fps=1000 / float(values.mean()),
                mean_ms=float(values.mean()), p50_ms=float(np.percentile(values, 50)),
                p95_ms=float(np.percentile(values, 95)))


def delta(fp32, fp16):
    return dict(predict_speedup=fp32['latency']['mean_ms'] / fp16['latency']['mean_ms'],
                map50_change_pp=100 * (fp16['accuracy']['map50'] - fp32['accuracy']['map50']),
                map50_95_change_pp=100 * (fp16['accuracy']['map50_95'] - fp32['accuracy']['map50_95']),
                torch_peak_allocated_change_mib=fp16['torch_peak_allocated_mib'] - fp32['torch_peak_allocated_mib'])


def prepare_copy(yaml_path, work):
    """Copy exactly the manifest's validation split; reject stale/mismatched exports."""
    import yaml
    from tools.prepare_d5_yolo_dev import validate_label
    info = inspect_dataset(yaml_path)
    root = Path(info['dataset_root'])
    rows = list(csv.DictReader((root / 'split_manifest.csv').open(encoding='utf-8-sig', newline='')))
    selected = sorted((r for r in rows if r['split'] == 'val'), key=lambda r: r['new_image'])
    image_dir = root / 'images/val'
    actual = {p.resolve() for p in image_dir.iterdir() if p.suffix.lower() in ('.jpg', '.jpeg', '.png')}
    if not selected or len(selected) != info['val_images']:
        raise ValueError('validation split manifest count mismatch')
    seen, registry = set(), []
    for row in selected:
        image, label = ((root / row[k]).resolve() for k in ('new_image', 'new_label'))
        if (not image.is_relative_to(root) or not label.is_relative_to(root)
                or image not in actual or image in seen
                or label != root / 'labels/val' / (image.stem + '.txt')):
            raise ValueError('invalid or duplicate validation image/label pair')
        seen.add(image)
        validate_label(label)
        registry.append(dict(image=row['new_image'], image_sha256=sha256(image),
                             label=row['new_label'], label_sha256=sha256(label), session=row['session']))
    if seen != actual:
        raise ValueError('validation manifest coverage mismatch')
    for row in registry:
        for key in ('image', 'label'):
            dest = work / row[key]
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / row[key], dest)
            if sha256(dest) != row[key + '_sha256']:
                raise ValueError('copied input hash differs')
    config = work / 'data.yaml'
    config.write_text(yaml.safe_dump(dict(path=str(work.resolve()), train='images/val', val='images/val', names=CLASSES)), encoding='utf-8')
    return config, registry


def worker(args):
    import cv2
    import torch
    from ultralytics import YOLO
    from ultralytics.cfg import DEFAULT_CFG_DICT
    from tools.gpu_baseline import gpu_snapshot, package_versions
    from tools.profile_pipeline import MemorySampler
    import requests
    import urllib.request

    if not torch.cuda.is_available():
        raise RuntimeError('CUDA required; no CPU fallback')
    torch.cuda.set_device(0)
    torch.manual_seed(532)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    expected = torch.float16 if args.bits == 16 else torch.float32
    calls = []
    def observe(module, inputs):
        param = next(module.parameters())
        image = inputs[0]
        if param.device.type != 'cuda' or image.device.type != 'cuda' or param.dtype != expected or image.dtype != expected:
            raise RuntimeError('requested precision/device not actually executed')
        calls.append(dict(input_dtype=str(image.dtype), parameter_dtype=str(param.dtype), device=str(image.device)))
    def forbidden(*a, **kw):
        raise RuntimeError('prepare cached assets first; network forbidden during comparison')
    images = [cv2.imread(str(p)) for p in sorted((args.work_dir / 'images/val').iterdir())]
    if not images or any(x is None for x in images):
        raise ValueError('all validation images must decode')
    options = dict(imgsz=args.imgsz, device=0, batch=1, rect=False, conf=.25, iou=.7,
                   max_det=300, verbose=False, save=False, augment=False, **precision_options(args.bits, DEFAULT_CFG_DICT))
    before = gpu_snapshot()
    with patch.object(urllib.request, 'urlopen', forbidden), patch.object(requests.sessions.Session, 'request', forbidden):
        model = YOLO(str(args.weights))
        names = [model.names[i] for i in range(len(model.names))]
        if names != CLASSES:
            raise ValueError('checkpoint D5 class order mismatch')
        handle = model.model.register_forward_pre_hook(observe)
        for i in range(args.warmup):
            model.predict(images[i % len(images)], **options)
        torch.cuda.synchronize()
        torch.cuda.reset_peak_memory_stats()
        times = []
        with MemorySampler(.01) as memory:
            for _ in range(args.repeats):
                for image in images:
                    torch.cuda.synchronize()
                    start = time.perf_counter()
                    model.predict(image, **options)
                    torch.cuda.synchronize()
                    times.append((time.perf_counter() - start) * 1000)
        allocated = torch.cuda.max_memory_allocated() / 2**20
        reserved = torch.cuda.max_memory_reserved() / 2**20
        predict_calls = len(calls)
        if not predict_calls or memory.errors:
            raise RuntimeError('missing dtype observations or failed memory sampler')
        handle.remove()
        del model
        gc.collect()
        torch.cuda.empty_cache()
        # Separate fresh model: accuracy thresholds differ from deployment-speed timings.
        model = YOLO(str(args.weights))
        handle = model.model.register_forward_pre_hook(observe)
        metrics = model.val(data=str(args.work_dir / 'data.yaml'), split='val', batch=1,
            imgsz=args.imgsz, device=0, workers=0, rect=False, conf=.001, iou=.7, max_det=300,
            augment=False, plots=False, save_json=False, save_txt=False, verbose=False,
            project=str(args.work_dir / 'validation'), name='fp' + str(args.bits),
            exist_ok=False, **precision_options(args.bits, DEFAULT_CFG_DICT))
        handle.remove()
        if len(calls) <= predict_calls:
            raise RuntimeError('validator precision not observed')
        classes = {CLASSES[int(c)]: dict(precision=float(metrics.box.p[i]), recall=float(metrics.box.r[i]),
                   map50=float(metrics.box.ap50[i]), map50_95=float(metrics.box.ap[i].mean()))
                   for i, c in enumerate(metrics.box.ap_class_index)}
        result = dict(bits=args.bits, gpu=torch.cuda.get_device_name(), versions=package_versions(),
            actual_execution=calls[0], predict_forward_calls=predict_calls,
            validation_forward_calls=len(calls) - predict_calls,
            weights_sha256=sha256(args.weights), latency=summarize_latency(times), latency_ms=times,
            torch_peak_allocated_mib=allocated, torch_peak_reserved_mib=reserved,
            nvml_device_used_peak_mib=max(memory.samples) / 2**20, nvml_samples=len(memory.samples),
            memory_scope='predict only; Torch allocator and sampled NVML whole-device usage reported separately',
            accuracy=dict(images=len(images), precision=float(metrics.box.mp), recall=float(metrics.box.mr),
                          map50=float(metrics.box.map50), map50_95=float(metrics.box.map), classes=classes),
            gpu_before=before, gpu_after=gpu_snapshot())
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def run(args):
    if not args.weights.is_file():
        raise FileNotFoundError('existing local checkpoint required')
    if args.work_dir.exists() or args.out.exists():
        raise FileExistsError('use new work/output paths; historical evidence is immutable')
    provenance = dataset_provenance(args.data)
    args.work_dir.mkdir(parents=True)
    _, registry = prepare_copy(args.data, args.work_dir)
    (args.work_dir / 'inputs.json').write_text(json.dumps(registry, indent=2), encoding='utf-8')
    weights_sha = sha256(args.weights)
    results = {}
    for bits in (32, 16):
        output = args.work_dir / ('fp%d.json' % bits)
        command = [sys.executable, '-m', 'tools.compare_d5_precision', '--worker', '--bits', str(bits),
                   '--weights', str(args.weights.resolve()), '--work-dir', str(args.work_dir.resolve()),
                   '--out', str(output.resolve()), '--imgsz', str(args.imgsz), '--warmup', str(args.warmup), '--repeats', str(args.repeats)]
        log = args.work_dir / ('fp%d.log' % bits)
        with log.open('w', encoding='utf-8') as stream:
            subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=True)
        results[str(bits)] = json.loads(output.read_text(encoding='utf-8'))
        if results[str(bits)]['weights_sha256'] != weights_sha:
            raise ValueError('checkpoint changed during experiment')
    for row in registry:
        for key in ('image', 'label'):
            if sha256(args.work_dir / row[key]) != row[key + '_sha256']:
                raise ValueError('copied dataset changed during experiment')
    report = dict(snapshot_date=args.date, timestamp_utc=datetime.now(timezone.utc).isoformat(),
        scope='native PyTorch CUDA single-model FP32/FP16, D5 same-session development only',
        weights_sha256=weights_sha, provenance=provenance, validation_inputs=registry,
        protocol=dict(imgsz=args.imgsz, batch=1, rect=False, warmup=args.warmup, repeats=args.repeats,
                      order=[32, 16], seed=532, tf32=False, power_source='unspecified',
                      predict_conf=.25, accuracy_conf=.001, nms_iou=.7, max_det=300,
                      accuracy_operating_point='Ultralytics P/R at validation best-F1; not a frozen deployment threshold',
                      latency_scope='decoded BGR in memory -> predict preprocessing/inference/NMS/results; synchronized wall time, excludes disk IO'),
        precisions=results, comparison=delta(results['32'], results['16']),
        independent_t1_passed=False, rtx4050_verified=False, tensorrt_measured=False,
        full_pipeline_measured=False, robot_trials=False, motor_commands_sent=0,
        limitations=['single development session reused for model selection; not independent accuracy',
                     'one FP32 then FP16 process; thermal/order effects and power source uncontrolled',
                     'D5 detector only; no face/re-ID/tracking/map/transport/control acceptance',
                     'FP16 is an experiment, not a change to deployment config',
                     'sampled NVML may miss short peaks and includes unrelated GPU processes'])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(report['comparison'], indent=2))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--weights', type=Path, required=True)
    ap.add_argument('--data', type=Path)
    ap.add_argument('--work-dir', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--imgsz', type=int, default=640, choices=(320, 416, 640))
    ap.add_argument('--warmup', type=int, default=10)
    ap.add_argument('--repeats', type=int, default=3)
    ap.add_argument('--date', default='2026-11-05', help='client-local evidence date')
    ap.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    ap.add_argument('--bits', type=int, choices=(16, 32), help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.warmup < 1 or args.repeats < 1 or (args.worker and args.bits is None) or (not args.worker and args.data is None):
        ap.error('positive warmup/repeats and data (or worker bits) required')
    os.environ.setdefault('YOLO_CONFIG_DIR', str(Path('data/ultralytics').resolve()))
    os.environ['YOLO_AUTOINSTALL'] = 'false'
    (worker if args.worker else run)(args)


if __name__ == '__main__':
    main()
