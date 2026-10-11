"""W1: real CUDA checks and YOLOv8n/s FPS/VRAM on a seeded synthetic BGR image.

    python -m tools.gpu_baseline --check-face

Weights download into gitignored data/models. This measures predict() including
preprocess/inference/postprocess, batch 1, FP32. It is not the full pipeline FPS
or evidence on a recorded room dataset. --check-face downloads buffalo_s and
executes detection and an embedding on synthetic images through CUDA sessions.
"""
import argparse
from datetime import datetime, timezone
import gc
import hashlib
import importlib
import importlib.metadata as md
import json
import os
from pathlib import Path
import platform
import subprocess
import time

from sentry.config import load
from sentry.net.latency import percentile


def package_versions():
    versions = {}
    for name in ("torch", "torchvision", "numpy", "opencv-python", "pyzmq", "ultralytics",
                 "insightface", "onnx", "onnxruntime", "onnxruntime-gpu", "torchreid", "pytest"):
        try:
            versions[name] = md.version(name)
        except md.PackageNotFoundError:
            versions[name] = None
    return versions


def gpu_snapshot():
    fields = ["name", "driver_version", "memory.total", "power.limit",
              "enforced.power.limit", "pstate", "temperature.gpu", "clocks.current.graphics"]
    try:
        process = subprocess.run(["nvidia-smi", "--query-gpu=" + ",".join(fields),
                                  "--format=csv,noheader"], text=True, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, check=True, timeout=10)
        return {"fields": fields, "rows": process.stdout.strip().splitlines()}
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        return {"error": str(exc)}


def check_onnx_cuda(out_dir, device):
    import numpy as np
    import onnxruntime as ort
    from onnx import TensorProto, helper

    graph = helper.make_graph([helper.make_node("Relu", ["x"], ["y"])], "cuda_check",
                              [helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, 4])],
                              [helper.make_tensor_value_info("y", TensorProto.FLOAT, [1, 4])])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    model.ir_version = 8
    options = ort.SessionOptions()
    options.enable_profiling = True
    options.profile_file_prefix = str(out_dir / "ort_cuda")
    session = ort.InferenceSession(model.SerializeToString(), sess_options=options,
                                   providers=[("CUDAExecutionProvider", {"device_id": device}),
                                              "CPUExecutionProvider"])
    result = session.run(None, {"x": np.array([[-1, 2, -3, 4]], dtype=np.float32)})[0]
    profile_path = session.end_profiling()
    events = json.loads(Path(profile_path).read_text(encoding="utf-8"))
    providers = sorted({e.get("args", {}).get("provider") for e in events
                        if e.get("args", {}).get("provider")})
    correct = bool(np.array_equal(result, [[0, 2, 0, 4]]))
    return {"session_providers": session.get_providers(), "executed_providers": providers,
            "correct_output": correct, "pass": correct and "CUDAExecutionProvider" in providers}


def check_face_cuda(root, device):
    import numpy as np
    from insightface.app import FaceAnalysis

    app = FaceAnalysis(name="buffalo_s", root=str(root),
                       providers=[("CUDAExecutionProvider", {"device_id": device}),
                                  "CPUExecutionProvider"])
    app.prepare(ctx_id=device, det_size=(640, 640))
    faces = app.get(np.zeros((640, 640, 3), dtype=np.uint8))
    recognizer = app.models["recognition"]
    embedding = recognizer.get_feat(np.zeros((112, 112, 3), dtype=np.uint8))
    providers = {name: model.session.get_providers() for name, model in app.models.items()}
    return {"pack": "buffalo_s", "detector_executed": True,
            "synthetic_face_count": len(faces), "embedding_shape": list(embedding.shape),
            "providers": providers,
            "pass": embedding.shape[-1] == 512 and bool(np.isfinite(embedding).all())
            and all(p[0] == "CUDAExecutionProvider" for p in providers.values()),
            "note": "Synthetic smoke test only; biometric accuracy needs D2."}


def environment_checks(out_dir, device, check_face):
    result = {"python": platform.python_version(), "platform": platform.platform(),
              "versions": package_versions(), "checks": {}}
    checks = result["checks"]
    try:
        import torch  # first: load torch CUDA/cuDNN DLLs before ONNX Runtime
        checks["torch_cuda"] = {"available": torch.cuda.is_available(), "cuda": torch.version.cuda}
        if not torch.cuda.is_available():
            raise RuntimeError("torch CUDA is unavailable")
        torch.cuda.set_device(device)
        props = torch.cuda.get_device_properties(device)
        result["gpu"] = {"name": props.name, "total_vram_bytes": props.total_memory,
                         "compute_capability": list(torch.cuda.get_device_capability(device))}
        x = torch.tensor([1.0, 2.0], device=device)
        checks["torch_cuda"]["pass"] = (x * x).sum().item() == 5
        del x
    except Exception as exc:
        checks["torch_cuda"] = {"pass": False, "error": str(exc)}
    result["nvidia_smi"] = gpu_snapshot()
    for name in ("cv2", "zmq", "ultralytics", "insightface", "torchreid"):
        try:
            importlib.import_module(name)
            checks[name] = {"pass": True}
        except Exception as exc:
            checks[name] = {"pass": False, "error": "%s: %s" % (type(exc).__name__, exc)}
    checks["onnx_packages"] = {"pass": bool(result["versions"]["onnxruntime-gpu"])
                              and not result["versions"]["onnxruntime"]}
    try:
        checks["onnx_cuda_inference"] = check_onnx_cuda(out_dir, device)
    except Exception as exc:
        checks["onnx_cuda_inference"] = {"pass": False, "error": str(exc)}
    if check_face:
        try:
            checks["insightface_inference"] = check_face_cuda(Path("data/insightface"), device)
        except Exception as exc:
            checks["insightface_inference"] = {"pass": False, "error": str(exc)}
    result["pass"] = all(c.get("pass", False) for c in checks.values())
    return result


def benchmark_model(weights, cfg):
    import numpy as np
    import torch
    from ultralytics import YOLO
    from ultralytics.cfg import DEFAULT_CFG_DICT

    torch.cuda.set_device(cfg["device"])
    torch.manual_seed(cfg["seed"])
    frame = np.random.default_rng(cfg["seed"]).integers(
        0, 256, (cfg["imgsz"], cfg["imgsz"], 3), dtype=np.uint8)
    model = YOLO(str(weights))
    options = dict(imgsz=cfg["imgsz"], device=cfg["device"], verbose=False)
    if "quantize" in DEFAULT_CFG_DICT:
        options["quantize"] = 32
    else:
        options["half"] = False
    try:
        runtime_before = gpu_snapshot()
        for _ in range(cfg["warmup"]):
            model.predict(frame, **options)
        dtype = next(model.model.parameters()).dtype
        if dtype != torch.float32:
            raise RuntimeError("FP32 baseline requested, got " + str(dtype))
        torch.cuda.synchronize(cfg["device"])
        torch.cuda.reset_peak_memory_stats(cfg["device"])
        durations = []
        with torch.inference_mode():
            for _ in range(cfg["iterations"]):
                torch.cuda.synchronize(cfg["device"])
                start = time.perf_counter()
                model.predict(frame, **options)
                torch.cuda.synchronize(cfg["device"])
                durations.append(time.perf_counter() - start)
        mean = sum(durations) / len(durations)
        return {"model": weights.name, "weights_sha256": hashlib.sha256(weights.read_bytes()).hexdigest(),
                "parameter_dtype": str(dtype),
                "status": "measured", "fps": 1 / mean, "mean_latency_ms": mean * 1000,
                "p50_latency_ms": percentile(durations, 0.5) * 1000,
                "p95_latency_ms": percentile(durations, 0.95) * 1000,
                "gpu_runtime_before": runtime_before, "gpu_runtime_after": gpu_snapshot(),
                "peak_allocated_mib": torch.cuda.max_memory_allocated(cfg["device"]) / 2**20,
                "peak_reserved_mib": torch.cuda.max_memory_reserved(cfg["device"]) / 2**20}
    finally:
        del model
        gc.collect()
        torch.cuda.empty_cache()


def main():
    cfg = load()["profiling"].copy()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path,
                    default=Path("reports/HuynhNguyenHoaiLoc/week-01/gpu_baseline.json"))
    ap.add_argument("--device", type=int, default=cfg["device"])
    ap.add_argument("--iterations", type=int, default=cfg["iterations"])
    ap.add_argument("--warmup", type=int, default=cfg["warmup"])
    ap.add_argument("--check-face", action="store_true")
    ap.add_argument("--env-only", action="store_true")
    ap.add_argument("--power-source", choices=["unspecified", "plugged-in", "battery"],
                    default="unspecified", help="user-reported laptop power state")
    args = ap.parse_args()
    if args.device < 0 or args.iterations <= 0 or args.warmup < 0:
        ap.error("device/warmup must be nonnegative and iterations positive")
    cfg.update(device=args.device, iterations=args.iterations, warmup=args.warmup)
    cfg["power_source"] = args.power_source
    args.out.parent.mkdir(parents=True, exist_ok=True)
    config_dir = Path("data/ultralytics").resolve()
    config_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("YOLO_CONFIG_DIR", str(config_dir))
    result = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "configuration": cfg,
              "scope": "single-model predict, batch=1 FP32, seeded synthetic BGR; not full pipeline or HIL",
              "environment": environment_checks(args.out.parent, args.device, args.check_face), "models": []}
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if not args.env_only and result["environment"]["checks"]["torch_cuda"].get("pass"):
        model_dir = Path("data/models")
        model_dir.mkdir(parents=True, exist_ok=True)
        for name in cfg["models"]:
            try:
                metrics = benchmark_model(model_dir / name, cfg)
            except Exception as exc:
                metrics = {"model": name, "status": "failed", "error": str(exc)}
            result["models"].append(metrics)
            args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    passed = result["environment"]["pass"] and (args.env_only or
             len(result["models"]) == len(cfg["models"])
             and all(m["status"] == "measured" for m in result["models"]))
    result["pass"] = passed
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
