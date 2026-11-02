"""Profile models resident together on the laptop GPU, with an explicit workload.

Sequential per-frame tracker+OSNet, pose, InsightFace, XFeat, optionally DINOv2.
Body/face work is padded to profile_people with synthetic crops when detections
are absent. This exercises every model, but is not real D3 accuracy or a live
network/control benchmark. NVML device-used includes ORT and other processes.
All model assets must be cached before execution; inference cannot download.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import threading
import time

import cv2
import numpy as np

from sentry.config import load


class MemorySampler:
    def __init__(self, interval):
        import pynvml
        self.nvml = pynvml
        pynvml.nvmlInit()
        self.handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        self.interval, self.samples, self.errors = interval, [], []
        self.done = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def sample(self):
        self.samples.append(int(self.nvml.nvmlDeviceGetMemoryInfo(self.handle).used))

    def _run(self):
        while not self.done.wait(self.interval):
            try:
                self.sample()
            except Exception as exc:
                self.errors.append(type(exc).__name__)
                return

    def __enter__(self):
        self.sample()
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.done.set()
        self.thread.join(timeout=2)
        self.sample()


def summarize(times, memory_bytes, settings, complete):
    if not times or not memory_bytes or not np.isfinite(times).all() or min(times) <= 0:
        raise ValueError('positive timing and device memory samples required')
    fps = 1 / float(np.mean(times))
    peak_bytes = max(memory_bytes)
    peak = peak_bytes / 2 ** 30
    return dict(fps=fps, p50_ms=float(np.percentile(times, 50) * 1000),
                p95_ms=float(np.percentile(times, 95) * 1000), device_used_peak_gib=peak,
                fps_limit_met=fps >= settings['min_fps'], vram_limit_met=peak_bytes <= settings['max_vram_bytes'],
                measured_workload_budget_met=fps >= settings['min_fps'] and peak_bytes <= settings['max_vram_bytes'],
                full_model_mix=complete, target_rtx4050_verified=False, t1_accepted=False)


def run(manifest, out, entrance_mode='both', iterations=None, door_hz=None):
    import torch  # CUDA DLLs before ORT
    from ultralytics import YOLO
    from ultralytics.cfg import DEFAULT_CFG_DICT
    from insightface.app import FaceAnalysis
    from sentry.perception.tracker import PersonTracker
    from sentry.perception.entrance import XFeatMatcher, DinoDescriber, DINO_REPO
    from tools.gpu_baseline import gpu_snapshot, package_versions
    cfg = load()
    s = cfg['pipeline_profile'].copy()
    if iterations is not None:
        s['iterations'] = iterations
    if s['iterations'] < 1 or s['warmup'] < 0 or s['profile_people'] < 1:
        raise ValueError('valid profiling iterations/warmup/person count required')
    if door_hz is not None and (not np.isfinite(door_hz) or door_hz <= 0):
        raise ValueError('positive finite door frequency required')
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA required')
    torch.cuda.set_device(0)
    os.environ['TORCH_HOME'] = str(Path(s['torch_home']).resolve())
    manifest = Path(manifest)
    inputs = json.loads(manifest.read_text(encoding='utf-8'))['frames']
    if not inputs:
        raise ValueError('nonempty input manifest required')
    images = [cv2.imread(str(manifest.parent / r['image'])) for r in inputs]
    from sentry.perception.reid import validate_image
    for image in images:
        validate_image(image)
    # Fail before model creation if cached assets are missing. Patch network for
    # the full inference lifetime to also catch hidden upstream downloads.
    pose_path = Path(s['pose_weights'])
    face_root = Path(s['face_root']).resolve()
    face_files = [face_root / 'models/buffalo_s' / name for name in ('det_500m.onnx', 'w600k_mbf.onnx')]
    assets = [pose_path, Path(cfg['reid']['person_weights']), Path('weights/xfeat.pt'), *face_files]
    for path in assets:
        if not path.is_file():
            raise FileNotFoundError('prepare model asset first: ' + str(path))
    hub = Path(torch.hub.get_dir())
    if entrance_mode == 'both':
        if not list((hub / 'checkpoints').glob('dinov2_vitb14_pretrain.pth')):
            raise FileNotFoundError('prepare pinned DINOv2-B with tools.fetch_models.fetch_dino before profiling')
        assets.extend((hub / 'checkpoints').glob('dinov2_vitb14_pretrain.pth'))
    import urllib.request
    import requests
    from unittest.mock import patch
    def forbidden(*args, **kwargs):
        raise RuntimeError('profiling attempted network I/O: cache assets before running')
    with patch.object(urllib.request, 'urlopen', forbidden), patch.object(requests.sessions.Session, 'request', forbidden):
        tracker = PersonTracker.from_config()
        pose = YOLO(str(pose_path))
        face = FaceAnalysis(name='buffalo_s', root=str(face_root), allowed_modules=['detection', 'recognition'],
                            providers=['CUDAExecutionProvider', 'CPUExecutionProvider'])
        face.prepare(ctx_id=0, det_size=(640, 640))
        for model in face.models.values():
            if model.session.get_providers()[0] != 'CUDAExecutionProvider':
                raise RuntimeError('InsightFace CUDA provider unavailable')
        matcher = XFeatMatcher(device='cuda')
        ref = matcher.features(images[0])
        dino = DinoDescriber('b', device='cuda') if entrance_mode == 'both' else None
        if dino:
            dino.ref = dino.describe([images[0]])
        precision = dict(quantize=32) if 'quantize' in DEFAULT_CFG_DICT else dict(half=False)
        dummy_body = np.random.default_rng(532).integers(0, 256, (256, 128, 3), np.uint8)
        dummy_face = np.zeros((112, 112, 3), np.uint8)
        counts, stage_times = [], {k: [] for k in ('tracking_osnet', 'pose', 'face', 'entrance')}
        t = 0.
        next_door = 0.
        def frame_step(image, record=False):
            nonlocal t, next_door
            t += .05
            begin = time.perf_counter()
            tracks = tracker(image, t)
            actual_body = sum(p.embedding is not None for p in tracks.tracks)
            pad_body = max(0, s['profile_people'] - actual_body)
            if pad_body:
                tracker.encoder.encode([dummy_body] * pad_body)
            torch.cuda.synchronize()
            a = time.perf_counter()
            pose.predict(image, imgsz=s['imgsz'], device=0, verbose=False, **precision)
            torch.cuda.synchronize()
            b = time.perf_counter()
            door_due = door_hz is None or b >= next_door
            faces, pad_face = [], 0
            if door_due:
                if door_hz:
                    next_door = b + 1 / door_hz
                faces = face.get(image)
                pad_face = max(0, s['profile_people'] - len(faces))
                for _ in range(pad_face):
                    face.models['recognition'].get_feat(dummy_face)
            torch.cuda.synchronize()
            c = time.perf_counter()
            if door_due:
                feats = matcher.features(image)
                p0, p1 = matcher.match(ref, feats)
                if len(p0) >= 4:
                    cv2.findHomography(p0, p1, cv2.RANSAC, cfg['entrance']['ransac_px'])
                if dino:
                    descriptor = dino.describe([image])
                    float((descriptor @ dino.ref.T).max())
            torch.cuda.synchronize()
            end = time.perf_counter()
            if record:
                counts.append(dict(observed_bodies=actual_body, padded_bodies=pad_body, observed_faces=len(faces), padded_faces=pad_face, door_ran=door_due))
                for key, value in zip(stage_times, (a - begin, b - a, c - b, end - c)):
                    stage_times[key].append(value * 1000)
            return end - begin
        for i in range(s['warmup']):
            frame_step(images[i % len(images)])
        tracker.reset()
        next_door = 0.
        torch.cuda.reset_peak_memory_stats()
        before = gpu_snapshot()
        with MemorySampler(s['nvml_sample_s']) as memory:
            times = [frame_step(images[i % len(images)], True) for i in range(s['iterations'])]
        result = summarize(times, memory.samples, s, entrance_mode == 'both')
        result.update(settings=s, entrance_mode=entrance_mode, gpu=torch.cuda.get_device_name(),
                      requested_door_hz=door_hz, actual_door_hz=sum(c['door_ran'] for c in counts) / sum(times),
                      model_id=tracker.encoder.model_id, versions=package_versions(),
                      memory_samples=len(memory.samples), memory_errors=memory.errors,
                      memory_scope='NVML device-used sampled; includes ORT, torch, driver and unrelated processes, sampling may miss short spikes',
                      torch_peak_allocated_mib=torch.cuda.max_memory_allocated() / 2**20,
                      torch_peak_reserved_mib=torch.cuda.max_memory_reserved() / 2**20,
                      gpu_before=before, gpu_after=gpu_snapshot(), latency_s=times,
                      stage_p50_ms={k: float(np.median(v)) for k, v in stage_times.items()}, workload=counts,
                      weights_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in assets},
                      config_sha256=hashlib.sha256(Path('config.toml').read_bytes()).hexdigest(),
                      input_manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
                      input_image_sha256=[hashlib.sha256((manifest.parent / r['image']).read_bytes()).hexdigest() for r in inputs],
                      dino_repo=DINO_REPO if dino else None, dino_precision='FP16' if dino else None,
                      other_torch_precision='FP32', network_access=False, motor_commands_sent=0,
                      limitations=['runtime workload only, padded synthetic embeddings are not accuracy evidence',
                                   'one supplied frame serves robot and door models; no live dual-stream transport or motor loop',
                                   'all selected models resident; sequential stages; optional door frequency is wall-clock scheduled without backlog',
                                   'RTX5060 evidence does not substitute for RTX4050 acceptance', 'power source not user-confirmed'])
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--manifest', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--entrance-mode', choices=['xfeat', 'both'], default='both')
    ap.add_argument('--iterations', type=int)
    ap.add_argument('--door-hz', type=float, help='optional wall-clock rate for face/entrance; default every frame')
    a = ap.parse_args()
    r = run(a.manifest, a.out, a.entrance_mode, a.iterations, a.door_hz)
    print(json.dumps({k: r[k] for k in ('gpu', 'fps', 'p95_ms', 'device_used_peak_gib', 'measured_workload_budget_met', 't1_accepted')}, indent=2))


if __name__ == '__main__':
    main()
