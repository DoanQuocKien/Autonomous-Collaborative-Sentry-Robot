"""W8 D1 parity: laptop prepare, then compare Nano raw outputs with ONNX FP32.

Private inputs/predictions stay under data/. Reports contain aggregate metrics,
per-ID coverage and hashes. TensorRT must be run separately on the Nano; neither
ONNX parity nor this laptop contact adapter certifies KR's future robot module.
"""
import argparse
import csv
import importlib.metadata
import json
import math
from pathlib import Path

import cv2
import numpy as np

from jetson.parity_run import yolo_canvas
from jetson.stage_a_parity_run import SCHEMA, blob, load_inputs, sha256
from jetson.yolo_post import nms
from sentry.config import DEFAULT_PATH, load
from sentry.perception.obstacle import Detection, ObstacleDetector
from sentry.perception.world import box_iou
from tools.bench_obstacles import match_boxes, summarize_id

ROOT = DEFAULT_PATH.parent
CHAIRS = ('chairs_a', 'chairs_b', 'chairs_c')


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(value, indent=2, allow_nan=False)+'\n')


def decode(raw, frame, settings):
    """COCO best-class/conf filter, class-aware NMS, original rectified pixels.

    Fixed square input, no auto/rect padding. Clipping and max_det match the
    laptop's Ultralytics path; legacy yolo_post.decode uses class-agnostic NMS.
    """
    if raw.shape != (84, 2100) or not np.isfinite(raw).all():
        raise ValueError('expected finite raw 84x2100 output')
    pred = raw.T
    cls = pred[:, 4:].argmax(axis=1)
    scores = pred[np.arange(len(pred)), cls+4]
    selected = (scores > settings['confidence']) & np.isin(cls, settings['class_ids'])
    pred, cls, scores = pred[selected], cls[selected], scores[selected]
    boxes = np.concatenate((pred[:, :2]-pred[:, 2:4]/2, pred[:, :2]+pred[:, 2:4]/2), axis=1)
    kept = []
    for label in sorted(set(cls)):
        ids = np.flatnonzero(cls == label)
        kept.extend(ids[nms(boxes[ids], scores[ids], settings['nms_iou'])])
    kept = sorted(kept, key=lambda i: (-float(scores[i]), int(i)))[:300]
    scale, px, py = frame['letterbox']
    width, height = frame['size']
    detections = []
    for i in kept:
        b = boxes[i].copy()
        b[[0, 2]] = np.clip((b[[0, 2]]-px)/scale, 0, width)
        b[[1, 3]] = np.clip((b[[1, 3]]-py)/scale, 0, height)
        detections.append(Detection(int(cls[i]), float(scores[i]), tuple(map(float, b))))
    return tuple(detections)


def box_stats(reference, candidate, minimum_iou=.9):
    pairs = sorted(((box_iou(a.xyxy, b.xyxy), i, j)
                    for i, a in enumerate(reference) for j, b in enumerate(candidate)
                    if a.class_id == b.class_id), reverse=True)
    a_used, b_used = set(), set()
    for overlap, i, j in pairs:
        if overlap >= minimum_iou and i not in a_used and j not in b_used:
            a_used.add(i)
            b_used.add(j)
    return dict(reference=len(reference), candidate=len(candidate), matched=len(a_used),
                same_count=len(reference) == len(candidate))


def raw_stats(reference, candidate):
    if reference.shape != candidate.shape or reference.ndim != 3 or not len(reference):
        raise ValueError('raw output shapes/count differ')
    if not np.isfinite(reference).all() or not np.isfinite(candidate).all():
        raise ValueError('nonfinite raw output')
    cosines = []
    for a, b in zip(reference, candidate):
        a, b = a.ravel().astype(np.float64), b.ravel().astype(np.float64)
        denominator = np.linalg.norm(a)*np.linalg.norm(b)
        cosines.append(float(np.clip(a @ b / denominator, -1, 1)) if denominator else 0.0)
    return dict(min_cosine=min(cosines), frames_below_0999=sum(c < .999 for c in cosines),
                max_abs_diff=float(np.max(np.abs(reference-candidate))))


def distance_stats(reference, candidate):
    """ID-first tape errors; absence is not a zero-error or passing observation."""
    ids = sorted(reference)
    if ids != sorted(candidate):
        raise ValueError('distance ID sets differ')
    valid = lambda values: [k for k in ids if values[k]['median_relative_error'] is not None]
    ref_ids, cand_ids = valid(reference), valid(candidate)
    paired = sorted(set(ref_ids) & set(cand_ids))
    median = lambda values, keys: float(np.median([values[k]['median_relative_error'] for k in keys])) if keys else None
    ref_error, cand_error = median(reference, paired), median(candidate, paired)
    delta = None if not paired else 100*(cand_error-ref_error)
    # Diagnostic on the shared subset. A gate also needs >=20 independent IDs
    # with no missing estimates; these nine stationary chairs cannot close T1.
    complete = len(paired) == len(ids) and len(ids) >= 20
    return dict(annotated_ids=len(ids), reference_distance_ids=len(ref_ids), candidate_distance_ids=len(cand_ids),
        paired_distance_ids=len(paired), reference_missing_ids=sorted(set(ids)-set(ref_ids)),
        candidate_missing_ids=sorted(set(ids)-set(cand_ids)),
        paired_reference_median_error=ref_error, paired_candidate_median_error=cand_error,
        reference_median_error_on_available_ids=median(reference, ref_ids),
        candidate_median_error_on_available_ids=median(candidate, cand_ids),
        reference_p90_error_on_available_ids=float(np.percentile([reference[k]['median_relative_error'] for k in ref_ids], 90)) if ref_ids else None,
        candidate_p90_error_on_available_ids=float(np.percentile([candidate[k]['median_relative_error'] for k in cand_ids], 90)) if cand_ids else None,
        candidate_minus_reference_percentage_points=delta,
        diagnostic_within_2_percentage_points=None if delta is None else abs(delta) <= 2,
        sufficient_coverage_for_gate=complete,
        passed=None if not complete else abs(delta) <= 2)


def summarize_rows(rows, labels):
    return {oid: summarize_id(values, labels[oid]['tape_forward_m']) for oid, values in rows.items()}


def collect_rows(result, labels, rows):
    matches = match_boxes(labels, result.obstacles, .3)
    for i, label in enumerate(labels):
        o = result.obstacles[matches[i]] if i in matches else None
        rows[label['obstacle_id']].append(dict(matched=o is not None,
            forward_m=float(o.ground.forward_m) if o and o.ground else None,
            rejection=o.rejection if o else 'missed_detection', source=o.detection.source if o else None))


def adapter(config, pose):
    return ObstacleDetector.from_config(config, predictor=lambda image: (), camera_pose_path=pose,
                                       floor_type='glossy', semantic_floor=False, open_vocabulary=False)


def labels_for(annotations, dataset):
    annotations = json.loads(Path(annotations).read_text(encoding='utf-8-sig'))
    with (Path(dataset)/'obstacles_2026-10-15.csv').open(encoding='utf-8-sig') as stream:
        truth = {row['obstacle_id']: row for row in csv.DictReader(stream)}
    labels = {}
    for a in annotations:
        oid, b = str(a['obstacle_id']), a['xyxy']
        if (oid in labels or a['clip'] not in CHAIRS or truth[oid]['clip'] != a['clip']
                or len(b) != 4 or not all(math.isfinite(v) for v in b)
                or not 0 <= b[0] < b[2] <= 640 or not 0 <= b[1] < b[3] <= 480):
            raise ValueError('invalid independent chair annotations')
        tape = float(truth[oid]['tape_distance_m'])
        if not math.isfinite(tape) or tape <= 0:
            raise ValueError('positive finite tape forward required')
        labels[oid] = dict(a, obstacle_id=oid, tape_forward_m=tape)
    if not labels or {a['clip'] for a in labels.values()} != set(CHAIRS):
        raise ValueError('all three annotated chair clips required')
    return labels


def evaluate(manifest, reference, candidate, data_root, config, pose, laptop=None):
    detector = adapter(config, pose)
    labels = manifest['labels']
    rows = {name: {oid: [] for oid in labels} for name in ('reference', 'candidate')}
    stats = []
    for i, frame in enumerate(manifest['frames']):
        path = Path(data_root)/frame['id']
        if sha256(path) != frame['sha256']:
            raise ValueError('raw D1 image hash mismatch')
        image = cv2.imread(str(path))
        if image is None:
            raise ValueError('unreadable D1 frame')
        selected = [a for a in labels.values() if a['clip'] == frame['clip']]
        detections = [decode(raw[i], frame, manifest['postprocess']) for raw in (reference, candidate)]
        stats.append(box_stats(*detections))
        for name, values in zip(rows, detections):
            detector.predictor = lambda image, values=values: values
            collect_rows(detector(image, float(i)), selected, rows[name])
    summaries = {name: summarize_rows(values, labels) for name, values in rows.items()}
    ref_count, cand_count = sum(r['reference'] for r in stats), sum(r['candidate'] for r in stats)
    matched = sum(r['matched'] for r in stats)
    denominator = max(ref_count, cand_count)
    box_fraction = matched/denominator if denominator else None
    raw = raw_stats(reference, candidate)
    boxes = dict(reference=ref_count, candidate=cand_count, matched_at_iou_09=matched,
        matched_fraction=box_fraction, count_mismatch_frames=sum(not r['same_count'] for r in stats))
    passed = (len(stats) >= 200 and raw['frames_below_0999'] == 0 and box_fraction is not None
              and box_fraction >= .95 and boxes['count_mismatch_frames'] == 0)
    report = dict(frames=len(stats), raw=raw, boxes=boxes, conversion_parity_passed=passed,
        distance=distance_stats(summaries['reference'], summaries['candidate']), per_id=summaries,
        parity_scope='raw cosine and decoded boxes; distance and Stage A acceptance are separate',
        distance_gate_policy='>=20 annotated IDs, estimates for every ID in both paths, absolute median-error delta <=2 percentage points')
    if laptop is not None:
        report['distance_against_laptop_640'] = distance_stats(laptop, summaries['candidate'])
        report['laptop_640_per_id'] = laptop
    return report


def prepare(onnx, data_root, dataset, annotations, out, report_path, frames=200, config=DEFAULT_PATH):
    import onnxruntime as ort
    import torch
    from ultralytics import YOLO
    from ultralytics.cfg import DEFAULT_CFG_DICT

    out, config, data_root, dataset, onnx = map(Path, (out, config, data_root, dataset, onnx))
    if not out.resolve().is_relative_to((ROOT/'data').resolve()):
        raise ValueError('private parity inputs must stay under data/')
    if out.exists() or Path(report_path).exists():
        raise FileExistsError('choose fresh output directory and report')
    cfg = load(config)
    weights = config.resolve().parent/cfg['obstacle']['weights']
    pose = dataset/'camera_pose_classroom_1015.json'
    metadata = json.loads(onnx.with_suffix('.json').read_text(encoding='utf-8'))
    if metadata['onnx_sha256'] != sha256(onnx) or metadata['weights_sha256'] != sha256(weights):
        raise ValueError('ONNX and configured laptop weights must match export hashes')
    if cfg['obstacle']['imgsz'] != 640:
        raise ValueError('this comparison explicitly targets the configured laptop 640 path')
    labels = labels_for(annotations, dataset)
    paths = sorted(p for clip in CHAIRS for p in (data_root/clip).glob('*.jpg'))
    if frames < 1 or frames > len(paths):
        raise ValueError('insufficient unique D1 chair frames')
    paths = [paths[i] for i in np.linspace(0, len(paths)-1, frames, dtype=int)]
    protected = [config, weights, onnx, Path(annotations), pose, dataset/'obstacles_2026-10-15.csv',
                 config.resolve().parent/cfg['obstacle']['camera_calibration'],
                 Path(__file__), ROOT/'jetson/stage_a_parity_run.py', ROOT/'jetson/yolo_post.py',
                 ROOT/'sentry/perception/obstacle.py', ROOT/'sentry/perception/camera.py', ROOT/'sentry/perception/contact.py']
    hashes = {str(p): sha256(p) for p in protected}
    detector = ObstacleDetector.from_config(config, camera_pose_path=pose, floor_type='glossy',
                                            semantic_floor=False, open_vocabulary=False)
    model = YOLO(str(weights)).model.cpu().float().eval()
    session = ort.InferenceSession(str(onnx), providers=['CPUExecutionProvider'])
    if (len(session.get_inputs()) != 1 or session.get_inputs()[0].shape != [1, 3, 320, 320]
            or session.get_inputs()[0].type != 'tensor(float)'
            or len(session.get_outputs()) != 1 or session.get_outputs()[0].shape != [1, 84, 2100]):
        raise ValueError('wrong fixed YOLOv8n-320 ONNX interface')
    canvases, pt, ort_raw, records = [], [], [], []
    laptop_rows = {oid: [] for oid in labels}
    for index, path in enumerate(paths):
        content_hash = sha256(path)
        image = cv2.imread(str(path))
        if image is None or image.shape != (480, 640, 3):
            raise ValueError('D1 must contain readable 640x480 images')
        canvas, scale, px, py = yolo_canvas(detector.geometry.undistort(image), 320)
        x = blob(canvas)
        with torch.inference_mode():
            prediction = model(torch.from_numpy(x))
        if isinstance(prediction, (tuple, list)):
            prediction = prediction[0]
        pt.append(prediction.cpu().numpy()[0])
        ort_raw.append(session.run(None, {session.get_inputs()[0].name: x})[0][0])
        canvases.append(canvas)
        clip = path.parent.name
        records.append(dict(id=path.relative_to(data_root).as_posix(), clip=clip, sha256=content_hash,
                            size=[640, 480], letterbox=[scale, px, py]))
        result = detector(image, float(index))
        collect_rows(result, [a for a in labels.values() if a['clip'] == clip], laptop_rows)
        if sha256(path) != content_hash:
            raise ValueError('image changed during inference')
        if (index+1) % 25 == 0:
            print('D1 frames: %d/%d' % (index+1, frames), flush=True)
    for path, digest in hashes.items():
        if sha256(path) != digest:
            raise ValueError('source/config/model changed during inference')
    out.mkdir(parents=True)
    laptop = summarize_rows(laptop_rows, labels)
    write_json(out/'laptop.json', laptop)
    np.savez_compressed(out/'inputs.npz', canvases=np.stack(canvases))
    np.savez_compressed(out/'reference.npz', raw=np.stack(ort_raw))
    np.savez_compressed(out/'torch.npz', raw=np.stack(pt))
    manifest = dict(schema=SCHEMA, frames=records, labels=labels, onnx_sha256=sha256(onnx),
        inputs_sha256=sha256(out/'inputs.npz'), reference_sha256=sha256(out/'reference.npz'),
        torch_sha256=sha256(out/'torch.npz'), source_sha256=hashes,
        laptop_sha256=sha256(out/'laptop.json'),
        adapter_sha256=dict(config=sha256(config), pose=sha256(pose),
                            camera=sha256(config.resolve().parent/cfg['obstacle']['camera_calibration'])),
        postprocess=dict(confidence=cfg['obstacle']['confidence'], class_ids=cfg['obstacle']['class_ids'],
                         nms_iou=float(DEFAULT_CFG_DICT['iou']), class_aware=True),
        input_scope='640x480 undistorted with original K, 320x320 square letterbox, RGB /255',
        laptop=dict(imgsz=640, rect=True, actual_device=str(detector.predictor.model.predictor.device),
                    nms_iou=float(DEFAULT_CFG_DICT['iou']), dtype='FP32'),
        versions={key: importlib.metadata.version(key) for key in ('torch', 'ultralytics', 'onnxruntime-gpu', 'numpy')})
    write_json(out/'manifest.json', manifest)
    report = evaluate(manifest, np.stack(pt), np.stack(ort_raw), data_root, config, pose, laptop)
    report.update(backend='pytorch-fp32-vs-onnxruntime-cpu-fp32', schema=SCHEMA,
        onnx_sha256=manifest['onnx_sha256'], manifest_sha256=sha256(out/'manifest.json'),
        inputs_sha256=manifest['inputs_sha256'], versions=manifest['versions'],
        laptop=manifest['laptop'], postprocess=manifest['postprocess'],
        adapter_sha256=manifest['adapter_sha256'],
        source_sha256={Path(p).resolve().relative_to(ROOT).as_posix(): digest for p, digest in hashes.items()},
        tensorrt_status='pending engine outputs from DQK', stage_a_g2_accepted=False,
        formal_t1_passed=False, motor_commands_sent=0,
        limitations=['200 correlated frames from three stationary glossy chair clips; nine annotated IDs',
                     'same laptop contact/projection adapter for all outputs; not KR robot-module parity',
                     'no matte, small-object recall, full-image precision, map, HIL or latency claim'])
    write_json(report_path, report)
    return report


def compare(bundle, candidate_dir, data_root, config, pose, report_path):
    bundle, candidate_dir = Path(bundle), Path(candidate_dir)
    if Path(report_path).exists():
        raise FileExistsError('choose a fresh report path')
    manifest, _ = load_inputs(bundle)
    info = json.loads((candidate_dir/'result.json').read_text(encoding='utf-8'))
    expected = dict(schema=SCHEMA, backend='tensorrt', complete=True,
        onnx_sha256=manifest['onnx_sha256'], manifest_sha256=sha256(bundle/'manifest.json'),
        inputs_sha256=manifest['inputs_sha256'], frame_ids=[r['id'] for r in manifest['frames']],
        raw_sha256=sha256(candidate_dir/'raw.npz'))
    if any(info.get(key) != value for key, value in expected.items()):
        raise ValueError('candidate provenance, frame order, completeness or raw hash mismatch')
    if len(info.get('engine_sha256', '')) != 64 or not info.get('runtime', {}).get('tensorrt'):
        raise ValueError('TensorRT engine hash/version required')
    # The adapter must be exactly the one used in preparation, including camera
    # intrinsics/pose and every source recorded in the manifest.
    for path, digest in manifest['source_sha256'].items():
        if sha256(path) != digest:
            raise ValueError('prepared code/config/model changed: '+path)
    cfg = load(config)
    adapter_hashes = dict(config=sha256(config), pose=sha256(pose),
                         camera=sha256(Path(config).resolve().parent/cfg['obstacle']['camera_calibration']))
    if adapter_hashes != manifest['adapter_sha256']:
        raise ValueError('wrong adapter configuration')
    if sha256(bundle/'reference.npz') != manifest['reference_sha256']:
        raise ValueError('reference archive hash mismatch')
    with np.load(bundle/'reference.npz', allow_pickle=False) as arrays:
        reference = arrays['raw']
    with np.load(candidate_dir/'raw.npz', allow_pickle=False) as arrays:
        candidate = arrays['raw']
    if reference.shape != (len(manifest['frames']), 84, 2100) or candidate.shape != reference.shape:
        raise ValueError('wrong raw shape/frame count')
    if sha256(bundle/'laptop.json') != manifest['laptop_sha256']:
        raise ValueError('laptop summary hash mismatch')
    laptop = json.loads((bundle/'laptop.json').read_text(encoding='utf-8'))
    report = evaluate(manifest, reference, candidate, data_root, config, pose, laptop)
    report.update(backend='onnxruntime-fp32-vs-tensorrt', provenance=info, schema=SCHEMA,
        adapter_sha256=adapter_hashes,
        stage_a_g2_accepted=False, formal_t1_passed=False, motor_commands_sent=0,
        limitation='laptop contact/projection adapter; robot module, fallback, safety and HIL remain separate')
    write_json(report_path, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prep = commands.add_parser('prepare')
    prep.add_argument('--onnx', required=True)
    prep.add_argument('--annotations', default='reports/HuynhNguyenHoaiLoc/week-02/issue-43/chair_boxes.json')
    prep.add_argument('--dataset', default='assets/d1/obstacles_2026-10-15')
    prep.add_argument('--out', required=True)
    prep.add_argument('--frames', type=int, default=200)
    comp = commands.add_parser('compare')
    comp.add_argument('--bundle', required=True)
    comp.add_argument('--candidate-dir', required=True)
    comp.add_argument('--pose', default='assets/d1/obstacles_2026-10-15/camera_pose_classroom_1015.json')
    for cmd in (prep, comp):
        cmd.add_argument('--data-root', default='data/dqk-obstacles-2026-10-15')
        cmd.add_argument('--config', default=str(DEFAULT_PATH))
        cmd.add_argument('--report', required=True)
    args = vars(parser.parse_args())
    command = args.pop('command')
    args['report_path'] = args.pop('report')
    report = prepare(**args) if command == 'prepare' else compare(**args)
    print(json.dumps({key: report[key] for key in ('backend', 'frames', 'raw', 'boxes', 'distance_against_laptop_640')}, indent=2))


if __name__ == '__main__':
    main()
