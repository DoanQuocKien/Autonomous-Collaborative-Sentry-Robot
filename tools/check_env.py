"""Verify the laptop environment. Run from the repo root:

    python tools/check_env.py            # GPU laptop: CUDA torch and a REAL onnxruntime CUDA session are required
    python tools/check_env.py --cpu-ok   # CPU-only laptop: GPU checks become warnings
"""
import argparse
import importlib
import importlib.metadata as md
import os
from pathlib import Path
import sys

problems = []


def report(ok, name, msg, fatal=True):
    print("%-5s %-22s %s" % ("ok" if ok else ("FAIL" if fatal else "warn"), name, msg))
    if not ok and fatal:
        problems.append(name)


def installed(pkg):
    try:
        return md.version(pkg)
    except md.PackageNotFoundError:
        return None


def onnx_cuda_session():
    import onnxruntime as ort
    from onnx import TensorProto as T, helper as h
    g = h.make_graph([h.make_node("Relu", ["x"], ["y"])], "g", [h.make_tensor_value_info("x", T.FLOAT, [1, 4])],
                     [h.make_tensor_value_info("y", T.FLOAT, [1, 4])])
    m = h.make_model(g, opset_imports=[h.make_opsetid("", 13)])
    m.ir_version = 8
    s = ort.InferenceSession(m.SerializeToString(), providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
    return s.get_providers()[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cpu-ok", action="store_true", help="CPU-only machine: GPU problems are warnings")
    gpu_fatal = not ap.parse_args().cpu_ok
    cache = Path(__file__).resolve().parents[1] / "data" / "ultralytics"
    cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("YOLO_CONFIG_DIR", str(cache))

    report(sys.version_info >= (3, 11), "python", sys.version.split()[0] + " (need >= 3.11 for tomllib; 3.12 tested)")

    import torch  # BEFORE onnxruntime, so onnxruntime reuses torch's CUDA DLLs
    cuda = torch.cuda.is_available()
    report(cuda, "torch cuda", "%s cuda=%s gpu=%s" % (torch.__version__, torch.version.cuda,
           torch.cuda.get_device_name(0) if cuda else "none"), fatal=gpu_fatal)

    both = [p for p in ("onnxruntime", "onnxruntime-gpu") if installed(p)]
    report(len(both) <= 1, "onnxruntime pkgs", "+".join(both) or "none",)
    if len(both) > 1:
        print("      fix: pip uninstall -y onnxruntime onnxruntime-gpu ; pip install onnxruntime-gpu==1.23.2")
    if cuda or gpu_fatal:
        try:
            first = onnx_cuda_session()
            report(first == "CUDAExecutionProvider", "onnxruntime session", "first provider: " + first, fatal=gpu_fatal)
        except Exception as e:  # noqa: BLE001 - any failure here means "no GPU for onnx"
            report(False, "onnxruntime session", str(e)[:120], fatal=gpu_fatal)

    for mod in ("cv2", "zmq", "PIL", "ultralytics", "insightface", "torchreid", "pytest"):
        try:
            m = importlib.import_module(mod)
            report(True, mod, getattr(m, "__version__", ""))
        except Exception as e:  # noqa: BLE001
            report(False, mod, "%s: %s" % (type(e).__name__, str(e)[:100]))
    import cv2
    report(hasattr(cv2, "aruco") and hasattr(cv2.aruco, "ArucoDetector"), "cv2.aruco", "ArucoDetector present")

    print("\nALL GOOD" if not problems else "\nPROBLEMS: " + ", ".join(problems))
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
