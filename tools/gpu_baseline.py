"""GPU baseline: download the pretrained models, check each runs on the GPU, and measure speed and memory.

    python -m tools.gpu_baseline                       # everything
    python -m tools.gpu_baseline --only yolo osnet     # just these sections (yolo, insightface, osnet)

Each section is tried on its own, so one failure (a download, an API change) does not hide the others.
Measures: YOLOv8n / YOLOv8s / YOLOv8n-pose at 640 (fp32 and fp16), InsightFace detector+embedder, OSNet (torchreid).
Ends with the GPU memory with the models of the chosen sections loaded together (plan target: <= 5.5 GB, pipeline >= 15 FPS).
Inputs are random noise images, so speeds are valid but detections are meaningless.
"""
import argparse
import statistics
import subprocess
import sys
import time
import traceback

import numpy as np
import torch  # before onnxruntime (via insightface), so onnxruntime reuses torch's CUDA libraries


def run_unthrottled():
    """Windows runs background processes (e.g. started from a hidden shell) in a low-power mode: CPU and GPU clocks stay low and
    a 35 FPS pipeline measured 5 FPS. Opt this process out of power throttling and raise its priority. No-op elsewhere."""
    try:
        import ctypes
        from ctypes import wintypes

        class State(ctypes.Structure):
            _fields_ = [("Version", ctypes.c_ulong), ("ControlMask", ctypes.c_ulong), ("StateMask", ctypes.c_ulong)]

        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.GetCurrentProcess.restype = wintypes.HANDLE
        k.SetProcessInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        k.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        h = k.GetCurrentProcess()
        s = State(1, 1, 0)  # version 1, control EXECUTION_SPEED, state 0 = throttling off
        ok = k.SetProcessInformation(h, 4, ctypes.byref(s), ctypes.sizeof(s))  # 4 = ProcessPowerThrottling
        k.SetPriorityClass(h, 0x00008000)  # ABOVE_NORMAL
        print("power-throttling opt-out: %s, priority ABOVE_NORMAL" % ("ok" if ok else "failed"))
    except Exception as e:  # not Windows, or an old Windows without the API
        print("power-throttling opt-out skipped (%s)" % type(e).__name__)


def vram_used_mb():
    out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                         stdout=subprocess.PIPE, universal_newlines=True).stdout
    return float(out.strip().splitlines()[0])


def bench(fn, n=100, warmup=15):
    for _ in range(warmup):
        fn()
    torch.cuda.synchronize()
    ts = []
    for _ in range(n):
        t = time.perf_counter()
        fn()
        torch.cuda.synchronize()
        ts.append((time.perf_counter() - t) * 1000)
    ts.sort()
    return statistics.median(ts), ts[int(0.95 * (n - 1))]


def section(title):
    print("\n=== " + title)
    sys.stdout.flush()


def yolo_section(keep):
    from ultralytics import YOLO
    section("YOLOv8 at 640 (weights are downloaded on first use)")
    img = np.random.randint(0, 255, (640, 640, 3), dtype=np.uint8)
    for name in ("yolov8n.pt", "yolov8s.pt", "yolov8n-pose.pt"):
        try:
            for half in (False, True):
                m = YOLO(name)  # a fresh model per precision, so one setting cannot leak into the other
                kw = {"half": True} if half else {}
                for _ in range(15):
                    m.predict(img, imgsz=640, verbose=False, device=0, **kw)
                tot, pre, inf, post = [], [], [], []
                for _ in range(100):
                    t = time.perf_counter()
                    r = m.predict(img, imgsz=640, verbose=False, device=0, **kw)
                    torch.cuda.synchronize()
                    tot.append((time.perf_counter() - t) * 1000)
                    pre.append(r[0].speed["preprocess"])
                    inf.append(r[0].speed["inference"])
                    post.append(r[0].speed["postprocess"])
                tot.sort()
                print("%-16s %s  whole call median %.1f ms (%.0f FPS) p95 %.1f ms | preprocess %.1f + inference %.1f + postprocess %.1f ms"
                      % (name, "fp16" if half else "fp32", statistics.median(tot), 1000 / statistics.median(tot), tot[94],
                         statistics.median(pre), statistics.median(inf), statistics.median(post)))
                if half:
                    keep.append(m)
        except Exception:
            print("%s FAILED:\n%s" % (name, traceback.format_exc(limit=3)))


def insightface_section(keep):
    section("InsightFace detector + embedder (buffalo_s pack)")
    try:
        import onnxruntime as ort
        from insightface.app import FaceAnalysis
        app = FaceAnalysis(name="buffalo_s", providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
                           allowed_modules=["detection", "recognition"])
        app.prepare(ctx_id=0, det_size=(640, 640))
        print("onnxruntime providers available:", ort.get_available_providers())
        print("models loaded:", sorted(app.models.keys()))
        for k, mdl in app.models.items():
            sess = getattr(mdl, "session", None)
            if sess is not None:
                print("  %-14s runs on: %s" % (k, sess.get_providers()[0]))
        img = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        ts = []
        for i in range(60):
            t = time.perf_counter()
            app.get(img)
            if i >= 10:
                ts.append((time.perf_counter() - t) * 1000)
        ts.sort()
        print("FaceAnalysis.get on a 640x480 noise image: median %.1f ms  p95 %.1f ms (no face found, so this is detector time)"
              % (statistics.median(ts), ts[int(0.95 * (len(ts) - 1))]))
        keep.append(app)
    except Exception:
        print("InsightFace FAILED:\n%s" % traceback.format_exc(limit=4))


def osnet_section(keep):
    section("OSNet via torchreid (re-identification embedding), 256x128 person crops")
    try:
        import torchreid
        try:
            net = torchreid.models.build_model(name="osnet_x0_25", num_classes=1000, pretrained=True)
            print("osnet_x0_25 pretrained weights loaded")
        except Exception as e:  # download problems are common (Google Drive); speed is still measurable
            print("pretrained download failed (%s); measuring with random weights" % type(e).__name__)
            net = torchreid.models.build_model(name="osnet_x0_25", num_classes=1000, pretrained=False)
        net = net.cuda().eval()
        for bs in (1, 8):
            x = torch.randn(bs, 3, 256, 128, device="cuda")
            with torch.no_grad():
                p50, p95 = bench(lambda: net(x), n=100)
            print("batch %d: median %.1f ms  p95 %.1f ms" % (bs, p50, p95))
        keep.append(net)
    except Exception:
        print("torchreid/OSNet FAILED:\n%s" % traceback.format_exc(limit=4))


def pipeline_section(keep):
    """What matters for the plan: several models per frame, back to back, for 30 s (keeps the GPU busier than one small model)."""
    from ultralytics import YOLO
    section("pipeline: YOLOv8n detect + YOLOv8n-pose + OSNet (2 crops) per frame, 30 s")
    try:
        import torchreid
        det, pose = YOLO("yolov8n.pt"), YOLO("yolov8n-pose.pt")
        net = torchreid.models.build_model(name="osnet_x0_25", num_classes=1000, pretrained=False).cuda().eval()
        img = np.random.randint(0, 255, (640, 640, 3), dtype=np.uint8)
        crops = torch.randn(2, 3, 256, 128, device="cuda")

        def frame():
            det.predict(img, imgsz=640, verbose=False, device=0)
            pose.predict(img, imgsz=640, verbose=False, device=0)
            with torch.no_grad():
                net(crops)

        for _ in range(15):
            frame()
        ts, t_end, clocks = [], time.time() + 30, []
        while time.time() < t_end:
            t = time.perf_counter()
            frame()
            torch.cuda.synchronize()
            ts.append((time.perf_counter() - t) * 1000)
            if len(ts) % 100 == 0:
                clocks.append(subprocess.run(["nvidia-smi", "--query-gpu=clocks.sm", "--format=csv,noheader,nounits"],
                                             stdout=subprocess.PIPE, universal_newlines=True).stdout.strip())
        ts.sort()
        print("frames: %d in 30 s -> %.1f FPS; per frame median %.1f ms, p95 %.1f ms (plan target: >= 15 FPS)"
              % (len(ts), len(ts) / 30.0, statistics.median(ts), ts[int(0.95 * (len(ts) - 1))]))
        print("GPU clock samples (MHz, max 3105): %s" % ", ".join(clocks))
        keep.extend([det, pose, net])
    except Exception:
        print("pipeline FAILED:\n%s" % traceback.format_exc(limit=4))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="+", choices=["yolo", "insightface", "osnet", "pipeline"], default=["yolo", "insightface", "osnet", "pipeline"])
    only = ap.parse_args().only
    section("environment")
    run_unthrottled()
    print("torch", torch.__version__, "cuda", torch.cuda.is_available(), torch.cuda.get_device_name(0))
    print("GPU memory used before anything: %.0f MB of %.0f MB" % (vram_used_mb(), torch.cuda.get_device_properties(0).total_memory / 1e6))
    keep = []
    for name, fn in (("yolo", yolo_section), ("insightface", insightface_section), ("osnet", osnet_section), ("pipeline", pipeline_section)):
        if name in only:
            fn(keep)
    section("loaded together: %s" % ", ".join(only))
    print("models kept in memory: %d" % len(keep))
    print("GPU memory used now: %.0f MB (plan target: peak <= 5,500 MB of 6,141 MB)" % vram_used_mb())
    print("torch peak allocated: %.0f MB" % (torch.cuda.max_memory_allocated() / 1e6))


if __name__ == "__main__":
    main()
