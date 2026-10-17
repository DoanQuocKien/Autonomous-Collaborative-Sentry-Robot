"""Issue #43 paired benchmark, matching manually annotated boxes, never tape range.

Annotations JSON: list of {clip, obstacle_id, xyxy}; boxes use rectified pixels
and remain fixed only for these stationary clips. Private image roots/annotations
stay in data/. Output contains metrics/hashes, never input images or bbox arrays.
"""
import argparse
import csv
import importlib.metadata
import json
import math
from pathlib import Path
import time

import cv2
import numpy as np

from sentry.config import DEFAULT_PATH, load
from sentry.perception.obstacle import ObstacleDetector
from sentry.perception.world import box_iou
from tools.fetch_floor_model import sha256


def match_boxes(annotations, observations, minimum_iou):
    """Greedy one-to-one image-space assignment, no distance/ground-truth leakage."""
    candidates = sorted(((box_iou(a['xyxy'], o.detection.xyxy), ai, oi)
                         for ai, a in enumerate(annotations) for oi, o in enumerate(observations)), reverse=True)
    used, matched = set(), {}
    for overlap, ai, oi in candidates:
        if overlap >= minimum_iou and ai not in matched and oi not in used:
            matched[ai] = oi
            used.add(oi)
    return matched


def summarize_id(rows, tape):
    estimates = [r['forward_m'] for r in rows if r['forward_m'] is not None]
    errors = [abs(v - tape) / tape for v in estimates]
    return dict(frames=len(rows), detected_frames=sum(r['matched'] for r in rows),
                distance_frames=len(estimates), tape_forward_m=tape,
                median_forward_m=float(np.median(estimates)) if estimates else None,
                median_relative_error=float(np.median(errors)) if errors else None,
                rejections=sorted({r['rejection'] for r in rows if r['rejection']}),
                sources=sorted({r['source'] for r in rows if r['source']}))


def run(annotations_path, out, mode='semantic', dataset='assets/d1/obstacles_2026-10-15',
        private_root=None, clips=None, every=1, minimum_iou=0.3, config_path=DEFAULT_PATH):
    if mode not in ('baseline', 'all80', 'semantic', 'hybrid') or every < 1 or not 0 < minimum_iou <= 1:
        raise ValueError('invalid benchmark mode/stride/IoU')
    dataset, out = Path(dataset), Path(out)
    config_digest = sha256(config_path)
    source_hashes = {str(p): sha256(p) for p in (
        Path('sentry/perception/obstacle.py'), Path('sentry/perception/floor.py'), Path('sentry/perception/world.py'))}
    annotations = json.loads(Path(annotations_path).read_text(encoding='utf-8-sig'))
    truth = {r['obstacle_id']: r for r in csv.DictReader((dataset / 'obstacles_2026-10-15.csv').open(encoding='utf-8-sig'))}
    if not annotations:
        raise ValueError('nonempty independent box annotations required')
    keys = [(a['clip'], str(a['obstacle_id'])) for a in annotations]
    if len(set(keys)) != len(keys):
        raise ValueError('duplicate annotation ID within clip')
    for a in annotations:
        a['obstacle_id'] = str(a['obstacle_id'])
        if a['obstacle_id'] not in truth or truth[a['obstacle_id']]['clip'] != a['clip']:
            raise ValueError('annotation ID/clip must match the tape manifest')
        b = a['xyxy']
        if len(b) != 4 or not all(math.isfinite(v) for v in b) or not 0 <= b[0] < b[2] <= 640 or not 0 <= b[1] < b[3] <= 480:
            raise ValueError('invalid rectified annotation box')
    clips = clips or sorted({a['clip'] for a in annotations})
    detector = ObstacleDetector.from_config(config_path, camera_pose_path=dataset / 'camera_pose_classroom_1015.json',
                                            floor_type='glossy', semantic_floor=mode in ('semantic', 'hybrid'),
                                            open_vocabulary=mode == 'hybrid')
    if mode == 'all80':
        detector.class_ids = frozenset(range(80))
        detector.predictor.settings = dict(detector.predictor.settings, class_ids=list(range(80)))
    import torch
    evidence, timings, frames_hash = {}, [], {}
    torch.cuda.reset_peak_memory_stats() if torch.cuda.is_available() else None
    for clip in clips:
        labels = [a for a in annotations if a['clip'] == clip]
        if not labels:
            raise ValueError('missing box annotations for clip: ' + clip)
        folder = dataset / clip
        if not folder.is_dir():
            if private_root is None:
                raise FileNotFoundError('private clip required; pass --private-root: ' + clip)
            folder = Path(private_root) / clip
        frames = sorted(folder.glob('*.jpg'))[::every]
        if not frames:
            raise ValueError('empty clip: ' + clip)
        rows = {a['obstacle_id']: [] for a in labels}
        frames_hash[clip] = [sha256(p) for p in frames]
        for _ in range(3):
            detector(cv2.imread(str(frames[0])), 0)
        for index, path in enumerate(frames):
            image = cv2.imread(str(path))
            start = time.perf_counter()
            result = detector(image, float(index))
            timings.append((time.perf_counter() - start) * 1000)
            matches = match_boxes(labels, result.obstacles, minimum_iou)
            for ai, a in enumerate(labels):
                o = result.obstacles[matches[ai]] if ai in matches else None
                rows[a['obstacle_id']].append(dict(matched=o is not None,
                    forward_m=float(o.ground.forward_m) if o and o.ground else None,
                    rejection=o.rejection if o else 'missed_detection', source=o.detection.source if o else None))
        evidence[clip] = {oid: summarize_id(values, float(truth[oid]['tape_distance_m'])) for oid, values in rows.items()}
    summaries = [s for ids in evidence.values() for s in ids.values()]
    errors = [s['median_relative_error'] for s in summaries if s['median_relative_error'] is not None]
    config = load(config_path)
    if sha256(config_path) != config_digest or any(sha256(p) != digest for p, digest in source_hashes.items()):
        raise RuntimeError('code/config changed during benchmark; rerun with a fixed version')
    model_hashes = {'yolo': sha256(Path(config_path).resolve().parent / config['obstacle']['weights'])}
    if mode in ('semantic', 'hybrid'):
        model_hashes['segformer'] = sha256(Path(config_path).resolve().parent / config['floor_segmentation']['model_path'] / 'model.safetensors')
    if mode == 'hybrid':
        model_hashes['world'] = sha256(Path(config_path).resolve().parent / config['open_vocabulary']['weights'])
    report = dict(mode=mode, floor='glossy', clips=evidence, obstacle_ids=len(summaries),
        detected_ids=sum(s['detected_frames'] > 0 for s in summaries), distance_ids=len(errors),
        stable_detected_ids=sum(s['detected_frames'] >= .5 * s['frames'] for s in summaries),
        stable_distance_ids=sum(s['distance_frames'] >= .5 * s['frames'] for s in summaries),
        stable_definition='matched/valid in at least half of the annotated clip frames',
        detection_frame_coverage=sum(s['detected_frames'] for s in summaries) / sum(s['frames'] for s in summaries),
        distance_frame_coverage=sum(s['distance_frames'] for s in summaries) / sum(s['frames'] for s in summaries),
        distance_median_relative_error=float(np.median(errors)) if errors else None,
        distance_p90_relative_error=float(np.percentile(errors, 90)) if errors else None,
        evaluated_frames=len(timings), latency_p50_ms=float(np.median(timings)),
        latency_p95_ms=float(np.percentile(timings, 95)), image_inference_fps=1000 / float(np.mean(timings)),
        actual_yolo_device=str(detector.predictor.model.predictor.model.device),
        gpu=torch.cuda.get_device_name() if torch.cuda.is_available() else None,
        torch_peak_allocated_mib=torch.cuda.max_memory_allocated() / 2**20 if torch.cuda.is_available() else None,
        torch_peak_reserved_mib=torch.cuda.max_memory_reserved() / 2**20 if torch.cuda.is_available() else None,
        model_sha256=model_hashes, config_sha256=config_digest, source_sha256=source_hashes,
        versions={name: importlib.metadata.version(name) for name in ('torch', 'numpy', 'opencv-python', 'ultralytics')},
        actual_segmentation_device=str(next(detector.floor.predictor.model.parameters()).device) if detector.floor else None,
        actual_world_device=str(detector.world.model.predictor.model.device) if detector.world else None,
        precision='FP32', warmup_per_clip=3,
        annotations_sha256=sha256(annotations_path), frame_sha256=frames_hash,
        camera_pose_sha256=sha256(dataset / 'camera_pose_classroom_1015.json'),
        matching='one-to-one rectified box IoU; no tape used in association', minimum_iou=minimum_iou,
        uncertainty='session pitch +/-1 degree, unmeasured drift; point estimates only',
        formal_t1_passed=False, missing_floor_types=['matte'], motor_commands_sent=0,
        limitations=['static clip box annotations; not independent camera viewpoints',
                     'matched-subset errors do not replace missing-ID counts',
                     'subset object annotations do not establish full-image precision',
                     'not RTX4050 baseline, map validation, HIL or whole-pipeline FPS'])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--annotations', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--dataset', default='assets/d1/obstacles_2026-10-15')
    ap.add_argument('--private-root')
    ap.add_argument('--clips', nargs='+')
    ap.add_argument('--every', type=int, default=1)
    ap.add_argument('--minimum-iou', type=float, default=.3)
    ap.add_argument('--mode', choices=('baseline', 'all80', 'semantic', 'hybrid'), default='semantic')
    ap.add_argument('--config', default=str(DEFAULT_PATH))
    a = ap.parse_args()
    result = run(a.annotations, a.out, a.mode, a.dataset, a.private_root, a.clips, a.every, a.minimum_iou, a.config)
    print(json.dumps({k: result[k] for k in ('mode', 'detected_ids', 'distance_ids', 'latency_p95_ms', 'formal_t1_passed')}, indent=2))


if __name__ == '__main__':
    main()
