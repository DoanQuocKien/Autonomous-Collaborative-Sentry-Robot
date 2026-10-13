"""Real YOLO + calibrated projection inference smoke, without motors or D1 claims.

python -m tools.check_w2 --out reports/HuynhNguyenHoaiLoc/week-02/inference_smoke.json
Uses the local raw camera-pose photo by default. Does not imply object accuracy,
collision avoidance, whole-pipeline FPS or the RTX 4050 target baseline.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import platform
import time

import cv2
import numpy as np

from sentry.config import DEFAULT_PATH
from sentry.perception.obstacle import ObstacleDetector


def run(image_path, out_path, config_path=DEFAULT_PATH, warmup=3, iterations=10,
        camera_pose_path=None, camera_path=None, floor_type="unknown"):
    if warmup < 0 or iterations < 1:
        raise ValueError("warmup >=0 and iterations >=1 required")
    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError("cannot read smoke image")
    import torch
    import ultralytics
    detector = ObstacleDetector.from_config(config_path, camera_pose_path=camera_pose_path,
                                            camera_path=camera_path, floor_type=floor_type)
    for _ in range(warmup):
        detector(image, time.perf_counter())
    times, result = [], None
    for _ in range(iterations):
        start = time.perf_counter()
        result = detector(image, start)
        # YOLO result is copied to CPU by the adapter, synchronizing output.
        times.append((time.perf_counter() - start) * 1000)
    s = detector.settings
    root = Path(config_path).resolve().parent
    runtime = str(detector.predictor.model.predictor.model.device)
    fp16 = bool(detector.predictor.model.predictor.model.fp16)
    cuda_requested = str(s["device"]).lower() != "cpu"
    if cuda_requested and not runtime.startswith("cuda"):
        raise RuntimeError("configured GPU inference did not execute on CUDA")
    if fp16:
        raise RuntimeError("Week 2 smoke requires FP32 inference")
    evidence = dict(kind="inference smoke on camera-pose photo; not T1 D1 or T2 HIL",
                    python=platform.python_version(), torch=torch.__version__,
                    opencv=cv2.__version__, ultralytics=ultralytics.__version__,
                    cuda_runtime=torch.version.cuda, actual_device=runtime, precision="FP32",
                    gpu=torch.cuda.get_device_name() if runtime.startswith("cuda") else None,
                    weights=s["weights"], weights_sha256=hashlib.sha256((root / s["weights"]).read_bytes()).hexdigest(),
                    image=str(image_path), image_sha256=hashlib.sha256(Path(image_path).read_bytes()).hexdigest(),
                    config_sha256=hashlib.sha256(Path(config_path).read_bytes()).hexdigest(),
                    calibration_sha256={s[k]: hashlib.sha256((root / s[k]).read_bytes()).hexdigest()
                                        for k in ("camera_calibration", "camera_pose")},
                    settings=s, warmup=warmup, iterations=iterations, latency_ms=times,
                    camera_session=detector.geometry.session, camera_pose_status=detector.geometry.pose_status,
                    latency_p50_ms=float(np.median(times)), latency_p95_ms=float(np.percentile(times, 95)),
                    result=asdict(result), motor_commands_sent=0, passed=True)
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, indent=2, allow_nan=False), encoding="utf-8")
    return evidence


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--image", default="calib/camera_pose_nowedge_raw.jpg")
    ap.add_argument("--out", required=True)
    ap.add_argument("--config", default=str(DEFAULT_PATH))
    ap.add_argument("--warmup", type=int, default=3)
    ap.add_argument("--iterations", type=int, default=10)
    ap.add_argument("--camera-pose")
    ap.add_argument("--camera")
    ap.add_argument("--floor-type", choices=("unknown","glossy","matte"), default="unknown")
    a = ap.parse_args()
    evidence = run(a.image, a.out, a.config, a.warmup, a.iterations,a.camera_pose,a.camera,a.floor_type)
    print(json.dumps({key: evidence[key] for key in ("actual_device", "gpu", "latency_p50_ms", "latency_p95_ms", "passed")}, indent=2))


if __name__ == "__main__":
    main()
