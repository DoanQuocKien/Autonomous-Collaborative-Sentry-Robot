# Edge deployment evidence (2026-10-16)

Raw output behind `docs/Edge Deployment.md`. The robot was a Jetson Nano 4GB (JetPack 4.5, TensorRT 7.1.3) running the camera and control services, wheels untouched, e-stop latch in place, **nobody in the camera view**; the door pipeline ran on a still public photo with two faces (not on ESP32-CAM frames). Runs from "evening" onward were on the robot's own battery.

| File | What it is |
| :-- | :-- |
| `engine_builds_first_run.json` | `trtexec` FP16 builds of YOLOv8n-pose, OSNet x0.25, OSNet-AIN, XFeat backbone, SCRFD (first export, with the Resize problem), MobileFaceNet: build time, mean GPU ms, engine size; the DINOv2 entries failed to parse (bicubic Resize) |
| `engine_builds_dinov2.json` | DINOv2 ViT-S/14 and ViT-B/14 after baking in the position embedding: both build (359.5 and 885.9 ms) |
| `bench_decode.json`, `bench_det.json`, `bench_stageB.json`, `bench_stageC.json` | `jetson/edge_bench.py` results on the live camera stream (60 s each; decode 20 s, detector 30 s); `stageB` is the run after the pre/post-processing speed-up; `stageC` has the door pipeline inside the frame loop |
| `bench_B_battery.json`, `bench_B_clocks.json` | Stage B on battery with default clocks and with `jetson_clocks` locked (no real difference) |
| `bench_C_thread.json`, `bench_C_sustained.json` | Stage C with the door pipeline in its own thread, 2 minutes and a 10-minute soak (12 000 frames, 3 001 door runs) |
| `tegra_*.log` | `tegrastats` at 1 Hz during the matching run (RAM, CPU, GPU load, temperatures, power rails) |

Not here: the parity numbers (cosine, box IoU) are in `docs/Edge Deployment.md`; the per-layer comparison that located the SCRFD `Resize` bug was a one-off script (`tools/export_edge_onnx.py` holds the fix and its test); the battery voltage samples during the soak were printed, not saved (12.14 V at the start, 11.93 V at the end, 11.96 V at rest afterwards).

Reproduce: `python -m tools.export_edge_onnx`, build the engines on the robot with `trtexec`, then `docker exec -w /workspace/sentry jetbot_jupyter python3 jetson/edge_bench.py --mode stageB --seconds 60` (commands in `docs/Edge Deployment.md`).
