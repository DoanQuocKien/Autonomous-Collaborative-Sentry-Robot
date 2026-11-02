# W5: ByteTrack + OSNet target lock and resident-model GPU profiling

## Behavior

Add `PersonTracker` for raw live/replay frames: local YOLOv8n person detections (including low-confidence association), upstream Ultralytics ByteTrack, current-frame OSNet embeddings, model/hash-gated target lock and confirmed reacquisition. Lost predictions never become visible targets; tied/ambiguous appearance abstains. Stream resets/gaps create a new epoch, preventing recycled numeric IDs from carrying identity. Phase2 `IntruderRecord` handoff rejects simulated appearance and incompatible model hashes.

Add receive-only live logging, private replay predictions and an aligned D3 evaluator reporting ID switches/min, misses, FP and protocol completeness. An empty tracker cannot pass. Add GPU profiling with all models resident: tracking/OSNet, pose, InsightFace, XFeat and optionally DINOv2-B. Sample NVML device memory across Torch/ORT, distinguish Torch allocator, and expose wall-clock door scheduling with actual update frequency. Dependencies are explicit; profiling blocks inference-time downloads.

## Validation

- CPU **584 passed**, 2 missing-D1 skips, 4 GPU deselected (26.06s); GPU **4 passed** (8.94s). Logs: `reports/HuynhNguyenHoaiLoc/week-05/pytest_{cpu,gpu}.log`. Python3.6 AST for common/jetson, updated CLI help and whitespace checks pass.
- Real D2 runtime replay: **822 frames**, full three clips. No D3 ID/lock accuracy claim; timestamps uniformly approximated, outputs private. GPU test executes real YOLO/ByteTrack/OSNet, with explicit synthetic bbox to cover embedding/lock independently of detection on noise.
- RTX5060, 5 warmup/100 iterations, at least two body/face workloads (synthetic padding disclosed): all stages every frame **12.719 FPS**, XFeat-only entrance **14.245 FPS**, all models resident with requested 5Hz door scheduling **19.652 FPS**, actual door **4.520 Hz**. Full-mix NVML sampled peak **0.939 GiB**. DINO FP16, other Torch models FP32. These are workload measurements, not RTX4050/live-stream acceptance.
- F9 generated from committed metrics; Chapter5 draft and API/reproduction documentation included. No raw biometric frames, embeddings, private predictions, weights or engines added.

## Dependencies and remaining acceptance

Base: main **36cb701**. Tracking/model tunables and evaluation protocol are in config.toml; target cosine/margin remain provisional until D2/D3 calibration.

D3 reviewed two-person scenes, target relock accuracy, RTX4050 budget/live dual-stream and optional Nano FP16 rank-1 comparison remain pending. No motor commands/hardware trials in this task. The benchmark scheduler is not a production main-loop integration. Target cosine/margin remain provisional until D2/D3 calibration.

Report/API/figures: `reports/HuynhNguyenHoaiLoc/week-05.md`, `W5-USAGE.md`, `week-05/`. Reviewer: DQK.
