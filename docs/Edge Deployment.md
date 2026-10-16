# Edge deployment on the Jetson Nano (measured 2026-10-16)

What was measured on the robot, what broke, and how to repeat it. The staged plan that builds on these numbers is `docs/Edge Feasibility.md` (a desk study with thin sources: treat its budgets as a plan to test). The spec still keeps all models on the laptop (`Project Specification.md` section 5); this is evidence for the "optimise and deploy on the robot" part of the Mid-Term report, not a spec change.

## Environment (robot)
- Jetson Nano 4GB B01, L4T R32.5.0 (JetPack 4.5), CUDA 10.2, cuDNN 8.0, **TensorRT 7.1.3**, Python 3.6.9, MAXN.
- The JetBot container (`jetbot_jupyter`) already has numpy 1.19.4, OpenCV 4.1.1, pyzmq, **tensorrt 7.1.3 and pycuda**; the host Python has numpy 1.13 and tensorrt only. Run robot code inside the container (`docker exec -w /workspace/sentry jetbot_jupyter python3 ...`).
- Root filesystem grown to 58 GB (34 GB free) on 2026-10-16, see `JetBot Notes.md`.

## Engines built on the robot (`trtexec --onnx ... --fp16`, batch 1, fixed shapes)
Mean GPU compute, network only (no pre/post-processing, no copies beyond trtexec's own), camera and control services running.

| Model | Input | GPU ms | Engine MB | Build min |
|---|---|---|---|---|
| YOLOv8n detect | 320 | 14.8 (FP32 20.7) | 9 | ~7 |
| YOLOv8n detect | 416 | 23.8 | 14.8 | |
| YOLOv8n-pose | 320 | 15.7 | 9.1 | 10.4 |
| OSNet x0.25 | 256x128 | 9.3 | 1.5 | 3.9 |
| OSNet-AIN x1.0 | 256x128 | 26.6 | 6.6 | 4.7 |
| XFeat backbone | 480x640 | 37.2 | 5.0 | 5.7 |
| SCRFD det_500m | 320x320 | 8.5 (7.9 for the first export with the Resize problem) | 2.4 | 2.8 |
| MobileFaceNet w600k_mbf | 112x112 | 14.8 | 7.6 | 4.0 |
| DINOv2 ViT-S/14 | 336x448 | 359.5 | 45.6 | 7.0 |
| DINOv2 ViT-B/14 | 336x448 | 885.9 | 174.2 | 10.6 |

DINOv2 at 0.4 to 2.8 frames per second stays on the laptop; the XFeat backbone alone is 27 FPS, without peak picking, matching or RANSAC.

## TensorRT 7.1 limits and how they were handled
| Problem | Handling |
|---|---|
| ONNX opset must be <= 11 | `tools/export_edge_onnx.py` exports at opset 11 |
| No bicubic `Resize` (DINOv2 position embedding) | embedding computed once for the fixed 24x32 grid and baked in |
| No `scaled_dot_product_attention` at opset 11 | attention rewritten as matmul + softmax (`Erf`/GELU is accepted) |
| `Resize` in the opset-11 `sizes` form is computed wrongly (SCRFD neck, cosine 0.88 to 0.99 against ONNX Runtime, FP32 and FP16 alike, no error or warning) | nearest 2x upsampling rewritten as a grouped ConvTranspose (2x2 ones, stride 2), identical in ONNX Runtime (`export_edge_onnx.resize_to_deconv`, tested). **Check every new engine against ONNX Runtime**: a bad operator does not fail, it only gives worse numbers |
| `grid_sample`, `unfold` | XFeat's backbone exports without `grid_sample`; descriptor sampling belongs to post-processing |
| InstanceNorm (OSNet-AIN, XFeat) is a plugin | Python must call `trt.init_libnvinfer_plugins` before deserialising; `trtexec` does it itself (found by the parity test: the engines built but would not load) |
| Dynamic ONNX shapes (insightface det/rec) | build with `--minShapes = --optShapes = --maxShapes`, then `TrtEngine(path, input_shape=...)` |
| Output order differs from the ONNX file (SCRFD) | `face_post.decode_scrfd` groups the 9 outputs by anchor count, not by position |
| Engines are tied to TensorRT version and GPU | copy the ONNX file, build on the robot, rebuild after a JetPack upgrade |

## Parity: TensorRT FP16 on the robot vs FP32 ONNX Runtime on the laptop
Same input tensor from the two public demo photos (not our data).

| Model | Result |
|---|---|
| YOLOv8n detector | cosine 1.00000 on the raw output; 4 boxes vs 4, best IoU 0.963 to 0.999 |
| YOLOv8n-pose | cosine 1.00000; 3 boxes vs 3, best IoU 0.991 to 0.999 |
| OSNet x0.25 / OSNet-AIN | cosine 1.00000 / 0.99998 on the 512-d embedding |
| XFeat backbone | cosine 0.99998 to 1.00000 on all three outputs |
| MobileFaceNet | cosine 0.99998 |
| **SCRFD** | the insightface export is computed **wrongly by TensorRT 7.1**, in FP32 and FP16 alike (best face score 0.720 against 0.813, 3 anchors above 0.5 against 5, landmarks off by up to ~10 px at stride 8). Cause found by comparing 22 intermediate tensors (backbone exact, first mismatch after the neck's `Resize` + `Add`) and fixed by rewriting the two nearest 2x `Resize` nodes as grouped ConvTranspose: **FP32 and FP16 engines now give cosine 1.00000 on all nine outputs, top score 0.813 and 5 anchors above 0.5, as ONNX Runtime** (FP16: 8.5 ms) |

Not covered: accuracy on our own data (D1/D2), FP16 effects on re-ID Rank-1, threshold behaviour.

## Live bench on the robot: `jetson/edge_bench.py` (reads the camera stream, no motors)
20 FPS camera, 640x480 JPEG q60, newest frame only, nobody in view, 60 s per mode (raw files: `week-02/edge_deploy/bench_*.json`, `tegra_*.log`).

| Mode | Compute / frame (mean, p95) | Capture to result (mean / p95) | FPS | Skipped |
|---|---|---|---|---|
| JPEG decode only | 4.9 ms | 11.9 / 12.9 ms | 20.0 | 0 |
| YOLOv8n detector every frame | 38.5 ms | 44.3 / 46.2 ms | 20.0 | 0 |
| Stage B (first run): pose every frame, detector every 3rd, OSNet x0.25 every 15th on a person | 35.7 ms | 41.6 / 56.2 ms | 20.0 | 0 |
| **Stage B after the pre/post-processing speed-up** | **32.0 ms (p95 44.5)** | **37.9 / 51.1 ms** | 20.0 | 1 of 1199 |
| **Stage C**: Stage B + door pipeline at 5 Hz (SCRFD, align, MobileFaceNet, 2 faces per run, in the same loop) | 45.0 ms (**p95 95.5**) | 63.0 / **101.2 ms** | 20.0 | 2 of 1198 |

Resources (`tegrastats`): Stage B RAM 2.08 GB mean (2.13 max) of 3.96 GB, GPU 36 % mean (93 % peak), CPU 30 %, 37 C, board 4.6 W mean (5.9 W peak); Stage C RAM 2.10 GB (2.15 max), GPU 50 % (93 % peak), CPU 35 %, 37 C, board 5.4 W (6.6 W peak). Decode only: 2.5 W.

Per stage, Stage B before and after the speed-up (ms mean): JPEG decode 4.7 / 4.8, pre-processing **6.4 / 3.4** (`cv2.dnn.blobFromImage`), pose 17.5 / 17.6, detector (every 3rd frame) 17.3 / 17.4, detector post-processing **3.3 / 0.85** (class argmax only on the rows above the threshold). The output of the new pre-processing is identical (max difference 6e-08). The `pycuda` path is slower than `trtexec` for the same engine (detector alone 23.6 ms vs 14.8 ms, 17.3 ms once the GPU is busier): copies, Python and probably GPU clocks at low load (not verified; try `jetson_clocks`).

Door pipeline per run (ms mean): pre-processing 4.6, SCRFD 10.2, decode 3.1, align + MobileFaceNet 17.2 per face (x2) = **52.2 per run**.

**What Stage C shows:** the door work is cheap on average but lumpy. A frame that carries a door run takes about 95 ms, so the capture-to-result p95 of 101 ms is close to the plan's 100 ms target (the strike limit is 150 ms frame to command, `Implementation Plan.md` section 4.3; the spec's 100 ms is the bounding-box growth window and needs a steady frame rate). The loop still averages 20 FPS. To keep the pursuit loop clear, the door pipeline needs its own process or thread, or its stages (SCRFD, then one face per frame) have to be spread across frames, or it pauses while a target is being pursued (the spec runs door monitoring in Phase 2, pursuit in Phase 3). This is what the sequential loop cannot answer; the threaded version below measured it.

## On battery: threaded door pipeline, GPU clocks, 10-minute soak (evening of 2026-10-16)
Same bench, robot on its own battery (12.28 V idle), wheels untouched, e-stop latch in place; files `week-02/edge_deploy/bench_B_*.json`, `bench_C_*.json`, `tegra_*.log`.

| Run | FPS / skipped | Compute mean (p95) | Capture to result mean / p95 | Door pipeline |
|---|---|---|---|---|
| Stage B, default clocks, 60 s | 20.0 / 0 of 1201 | 31.9 (44.3) ms | 37.9 / 51.1 ms | - |
| Stage B, `jetson_clocks` locked, 60 s | 20.0 / 0 of 1200 | 31.6 (43.7) ms | 36.9 / 49.1 ms | - |
| Stage C, door in the frame loop (earlier run) | 19.96 / 2 of 1198 | 45.0 (95.5) ms | 63.0 / **101.2** ms | 52.2 ms per run |
| **Stage C, door in its own thread (`--door-thread`), 120 s** | 20.0 / 0 of 2400 | 37.0 (65.7) ms | 45.0 / **72.1** ms | 601 runs = 5.0 Hz, 75.1 ms per run (p95 90.7) |
| **Stage C threaded, 10-minute soak** | 20.0 / 0 of 12000 | 35.7 (59.5) ms | 43.4 / **69.9** ms | 3001 runs = 5.0 Hz, 68.6 ms per run (p95 73.2) |

- **Threading keeps the pursuit loop clear.** With the door work in its own thread (own engines and CUDA stream, shared CUDA context) the pursuit loop keeps 20 FPS and its capture-to-result p95 falls from 101 ms to 70 to 72 ms. The door runs themselves get slower (52 to about 70 ms) because the two threads share the GPU, which is fine at 5 Hz.
- **`jetson_clocks` is not worth it:** locking the clocks gained about 1 ms mean and 2 ms p95 for about 0.1 W. The extra `pycuda` cost over `trtexec` (23.6 against 14.8 ms for the detector alone) is therefore not a low-load clock effect.
- **Soak (10 min, Stage C threaded):** RAM 2.14 GB mean, 2.157 max (no growth), GPU 60 % mean (99 % peak), CPU 35 %, GPU 39 C mean (40 max), board 5.76 W mean (7.0 W peak). No skipped-frame trend, no thermal problem.
- **Battery:** 12.14 V at the start of the soak, 11.93 V at the end, 11.96 V at rest afterwards; about 0.2 V in 10 minutes with the motors off. The voltage is noisy (swings of about 0.1 V between samples) and a Li-ion pack is not linear, so this does **not** give a runtime: run a long drain test from full to 11.1 V (and later with driving) before promising one.

## Limits of these results
- Nobody was in the camera view: person-dependent costs (keypoints, OSNet crops, NMS with many boxes) are under-measured. The door pipeline ran on a still public photo with two faces, not on ESP32-CAM frames (not connected during these runs).
- No motors and no e-stop in the loop (the latch stayed in place); the battery numbers cover compute only, not driving, which adds a large current.
- Parity covers FP16 against FP32 on a few public photos, not accuracy on our own data (D1/D2).

## Reproduce
```
python -m tools.export_edge_onnx                    # laptop: ONNX files in data/models/onnx_export/ (the face detector comes out as det_500m_deconv320.onnx)
# copy the .onnx files to /home/jetbot/trt/ on the robot, then there:
/usr/src/tensorrt/bin/trtexec --onnx=NAME.onnx --saveEngine=NAME_fp16.engine --fp16 --workspace=512
# dynamic-shape models (the embedder): add --minShapes=input.1:1x3x320x320 --optShapes=... --maxShapes=...  (112x112 for the embedder)
docker exec -w /workspace/sentry jetbot_jupyter python3 jetson/edge_bench.py --mode stageB --seconds 60
```
Code: `jetson/trt_runtime.py` (engine runner), `jetson/yolo_post.py`, `jetson/face_post.py` (SCRFD decode and ArcFace alignment, verified against insightface: identical boxes and landmarks, embedding cosine 1.0000), tests in `tests/test_yolo_post.py` and `tests/test_face_post.py`.
