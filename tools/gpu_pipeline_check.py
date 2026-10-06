"""Extras next to HuynhNguyenHoaiLoc's `tools.gpu_baseline` (the Week 1 GPU baseline): things it does not cover.

    python -m tools.gpu_pipeline_check                     # both sections
    python -m tools.gpu_pipeline_check --only pipeline     # or just one (osnet, pipeline)

* pipeline: YOLOv8n detect + YOLOv8n-pose + OSNet on two crops, back to back for 30 s (the plan's real target is the
  whole pipeline at >= 15 FPS, not one model).
* osnet: loads the RE-ID-trained OSNet weights from weights/ (python -m tools.fetch_models) and times them.
* run_unthrottled(): Windows runs background processes (e.g. started from a hidden shell) in a low-power mode: a 35 FPS
  pipeline measured 5 FPS and the GPU clock sat near 250-450 MHz. This opts the process out and raises its priority;
  measured 2026-10-06 on an RTX 4050: 5.3 -> 34.9 FPS. Worth calling in any benchmark or live pipeline on Windows.
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


def osnet_section(keep):
    section("OSNet via torchreid, RE-ID-trained weights from weights/ (python -m tools.fetch_models), 256x128 person crops")
    try:
        from pathlib import Path
        import torchreid
        wdir = Path(__file__).resolve().parent.parent / "weights"
        for arch, fname in (("osnet_ain_x1_0", "osnet_ain_x1_0_dg.state.pt"), ("osnet_x0_25", "osnet_x0_25_market1501.state.pt")):
            path = wdir / fname
            if not path.exists():
                print("%s: %s missing, run python -m tools.fetch_models" % (arch, fname))
                continue
            net = torchreid.models.build_model(name=arch, num_classes=1000, pretrained=False)
            have, saved = net.state_dict(), torch.load(str(path), map_location="cpu", weights_only=True)
            usable = {k: v for k, v in saved.items() if k in have and v.shape == have[k].shape}  # the id classifier differs per dataset
            net.load_state_dict(usable, strict=False)
            print("%s <- %s: %d of %d weight tensors loaded (%d skipped, e.g. the dataset-specific id classifier)"
                  % (arch, fname, len(usable), len(have), len(saved) - len(usable)))
            net = net.cuda().eval()
            x = torch.randn(1, 3, 256, 128, device="cuda")
            with torch.no_grad():
                a, b = net(x), net(x)
                other = net(torch.randn(1, 3, 256, 128, device="cuda"))
            cos = torch.nn.functional.cosine_similarity
            print("  embedding size %d; same crop twice cos %.3f; two different noise crops cos %.3f" % (a.shape[1], cos(a, b).item(), cos(a, other).item()))
            for bs in (1, 8):
                x = torch.randn(bs, 3, 256, 128, device="cuda")
                with torch.no_grad():
                    p50, p95 = bench(lambda: net(x), n=100)
                print("  batch %d: median %.1f ms  p95 %.1f ms" % (bs, p50, p95))
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
    ap.add_argument("--only", nargs="+", choices=["osnet", "pipeline"], default=["osnet", "pipeline"])
    only = ap.parse_args().only
    section("environment")
    run_unthrottled()
    print("torch", torch.__version__, "cuda", torch.cuda.is_available(), torch.cuda.get_device_name(0))
    print("GPU memory used before anything: %.0f MB of %.0f MB" % (vram_used_mb(), torch.cuda.get_device_properties(0).total_memory / 1e6))
    keep = []
    for name, fn in (("osnet", osnet_section), ("pipeline", pipeline_section)):
        if name in only:
            fn(keep)
    section("loaded together: %s" % ", ".join(only))
    print("models kept in memory: %d" % len(keep))
    print("GPU memory used now: %.0f MB (plan target: peak <= 5,500 MB of 6,141 MB)" % vram_used_mb())
    print("torch peak allocated: %.0f MB" % (torch.cuda.max_memory_allocated() / 1e6))


if __name__ == "__main__":
    main()
