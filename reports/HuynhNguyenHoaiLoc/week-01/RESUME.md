# Resume HNHL Week 1

Originally paused at the user's explicit request on **2026-10-04** for computer
shutdown. **Resumed on 2026-10-04 when the user said "Tiếp tục".** The historical
pause is no longer active; read the latest weekly report for current status.

## Latest state after resuming - supersedes the historical snapshot below

**Review update 2026-10-10:** baseline implementation is now committed on the
W1 branch. New review fixes/evidence remain in the working tree. Final checks:
87 tests passed, check_env ALL GOOD with actual CUDA Relu execution, and
synthetic localhost telemetry passed (28.767 run FPS, decoded p95 2.984 ms).
See [the weekly report](../week-01.md) and
[prepared PR text](../../../docs/PR-W1-HNHL.md). The measurements and process
statements below describe the earlier 2026-10-04 session.

Local W1 implementation and GPU/environment verification are complete.
The `.venv` is now ready; no further download/install is required for W1.

- `check_env.py`: **ALL GOOD**; generated Ultralytics settings stay under data/.
- Tests in the complete GPU environment: **77 passed in 5.58 s**.
- Final GPU baseline: **pass**, YOLOv8n **49.179 FPS**, YOLOv8s **26.060 FPS**;
  640x640 seeded synthetic BGR, FP32 verified, batch 1, 10 warmup/100 samples.
- Peak allocated/reserved PyTorch memory: n **33.545/58 MiB**, s **78.616/94 MiB**.
  These are allocator values, not total process VRAM.
- Torch CUDA computation, profiled ONNX CUDA Relu and InsightFace buffalo_s
  detector + finite [1, 512] embedding all passed.
- Actual GPU remains RTX 5060 Laptop GPU, driver 591.74. Final snapshots
  recorded **20 W enforced power limit**, temperatures 41-42 C; AC/battery
  state was not confirmed (`power_source=unspecified`).
- Python 3.12.15; torch 2.9.1+cu128; torchvision 0.24.1+cu128;
  ultralytics 8.4.172; insightface 2.1; ORT GPU 1.23.2; CPU ORT absent.
- Complete torch/ORT wheels are in data/wheels, checked against source SHA256.
  buffalo_s ZIP is complete, CRC-checked and extracted. Scratch resumable
  range downloader lives in data/bootstrap/resume_download.py.
- Added `gdown` to requirements for torchreid's undeclared import dependency.
  Updated profiling precision API to remove per-frame deprecation logging.
- Evidence: check_env.log, pytest.log, gpu_baseline.json/.log,
  ort_cuda_2026-10-04_23-01-27.json, environment_versions.json, and the previous
  loopback CSV/JSON under this directory. See the current weekly report.
- No commits, pushes, PR or merge have been made. Work remains on branch
  HuynhNguyenHoaiLoc/w01-network-telemetry.

Remaining handoff: DQK review/PR, team W1 interface freeze, real JetBot
latency/control/watchdog HIL, D1 capture and a rerun on the specified RTX 4050.
Do not interpret localhost/synthetic results as HIL or biometric accuracy.
On a future continuation, use this latest state and the weekly report;
**do not repeat the old partial-download/install instructions below**.

## Scope and decisions

- User: HuynhNguyenHoaiLoc (HNHL). Implement their W1 networking/telemetry and
  GPU baseline items in `docs/Implementation Plan.md`.
- Teacher's pasted JetBot overview was read. Keep the project's laptop AI +
  ZMQ video/UDP control architecture; camera/hardware setup remains with DQK.
- Actual GPU: NVIDIA GeForce RTX 5060 Laptop GPU, 8 GB, driver 591.74. Label
  its measurements correctly; RTX 4050 target evidence still needs DQK.
- User confirmed there was no `sentry` environment. Created isolated Python
  **3.12.15** in `.venv`. Bootstrap Python and caches live under gitignored
  `data/`; existing Python installations were not modified.
- Branch: `HuynhNguyenHoaiLoc/w01-network-telemetry`. No commit, push, PR or
  merge has been made. Working tree contains the implementation.
- No AGENTS.md was found in the repo or checked ancestor paths. CLAUDE.md and
  project specification/plan/setup were read. No subagents were used.

## Implemented and verified

- `sentry/net/frame.py`: `VideoFrame` contract for KR's future record/replay.
- `zmq_rx.py`: receiver worker owns its socket, bounded multipart drain,
  JPEG decode, one latest slot, timeout/error handling and clean shutdown.
  `CONFLATE` cannot handle multipart, so do not enable it. Wire format stays
  `[header_json, jpeg_bytes]`; review this correction at W1 interface freeze.
- `udp_tx.py`: nonblocking normalized v/w commands, 30 Hz maximum rate, no
  stale-command heartbeat, immediate zero on stop/context exit.
- `clock_sync.py`: 20 valid echoes, minimum RTT Cristian offset; rejects
  malformed/stale replies and times out instead of inventing an offset.
- `latency.py` + `tools/log_latency.py`: raw CSV and JSON p50/p95/FPS summaries,
  signed clock correction, negative-latency/reset flags; no motor commands.
- `tools/check_net.py`: synthetic local publisher + echo + real latency CLI.
- `tools/send_cmd.py` now uses UDPSender; `--silent-end` applies only to
  normal completion, exceptions still attempt a stop.
- `tools/gpu_baseline.py`: CUDA torch computation, profiled ONNX Relu checking
  the actual executed provider, optional buffalo_s detection/512-d embedding,
  YOLOv8n/s FP32 batch-1 640 warmup/FPS/allocator-memory measurements and JSON.
  Implemented but **NOT yet run** because CUDA dependencies are incomplete.
- Added config knobs, `.venv/` ignore, `loopback` pytest marker, tests, guide
  `docs/W1-HNHL.md`, weekly report, and corrected stale W1 environment/CONFLATE
  notes in the plan.
- Laptop timestamps consistently use **time.perf_counter()**. Windows
  Python 3.12 `monotonic()` reported 15.625 ms resolution; perf_counter is
  100 ns. Jetson t_cap remains source monotonic; offset converts domains.

Latest verification:

```powershell
.venv\Scripts\python.exe -m pytest -m "not gpu and not hil" --basetemp=data/pytest-tmp-reviewed -q
# 77 passed in 1.49 s; reports/HuynhNguyenHoaiLoc/week-01/pytest.log
.venv\Scripts\python.exe -m tools.check_net --fps 30 --seconds 5
# 145 frames; 28.917 run FPS; decoded p95 1.887 ms
# loopback_latency.csv / .json, simulated clock offset 100 s, not HIL
```

The latest code change cleared pending frames on receiver close and added
shutdown/startup-failure tests; the 77-test run includes these changes.
Compileall and git diff --check passed. Evidence logs were normalized to UTF-8.

## Installation state when paused

All relevant download/install processes were explicitly stopped for shutdown,
including the automatic wait-then-install chain. No background installation
should be assumed to continue. Old exec session/process IDs are stale after
shutdown and must never be used to stop processes in a resumed session.

- Ready `.venv` packages: pytest 9.1.1, numpy 2.5.3, opencv-python 5.0.0.93,
  pyzmq 27.2.0, pillow 12.3.0 and their minimal test dependencies.
- **torch is not installed** in `.venv` at pause. PyTorch 2.9.1 cu128 wheel
  (2.7 GiB download) was partially streamed/extracted into UV cache. Do not
  treat partial archives as usable packages; UV may need to redownload.
- `data/bootstrap/uv/uv.exe` is ready. Python bootstrap is under `data/python`.
- Cache root: `data/uv-cache`. Some complete dependency wheels are cached;
  torch and onnxruntime-gpu downloads were incomplete when stopped.
- A separate `--target data/deps-staging --no-deps -r requirements.txt` prefetch
  was interrupted. This directory is not the usable project environment.
- Cached source inspection found insightface 2.1 and ultralytics 8.4.172.
  FaceAnalysis(name="buffalo_s") and recognition.get_feat still exist.
  Record the versions actually installed after resuming.
- Complete weights in `data/models`: yolov8n.pt (6,549,796 bytes), yolov8s.pt
  (22,588,772 bytes), downloaded from official Ultralytics assets v8.4.0.
- **Incomplete** `data/insightface/models/buffalo_s.zip`: 37,761,024 bytes at
  pause; official asset total was 127,607,557 bytes. Do not extract/use it yet.
  Also incomplete `buffalo_s.part0` through `.part3` from an attempted parallel
  range download; do not concatenate/use these without completing and checking.
  Simplest path: resume the original ZIP with curl `-C -` and then verify ZIP.
- `data/bootstrap/ort_meta.json` is official PyPI metadata for ORT GPU 1.23.2;
  the cp312 Windows wheel is 244,508,327 bytes, with SHA256 in that metadata.

## Next steps on resume

1. Read this note and the weekly report, check git status and actual environment
   state. Preserve the existing implementation, data/cache and evidence.
2. Finish CUDA torch and project dependencies in `.venv`, using the existing
   UV/cache (network/escalation may be required):

```powershell
$env:UV_CACHE_DIR = Join-Path (Get-Location) 'data/uv-cache'
& data/bootstrap/uv/uv.exe pip install --python .venv/Scripts/python.exe torch==2.9.1 torchvision==0.24.1 --index-url https://download.pytorch.org/whl/cu128
& data/bootstrap/uv/uv.exe pip install --python .venv/Scripts/python.exe -r requirements.txt
& data/bootstrap/uv/uv.exe pip uninstall --python .venv/Scripts/python.exe onnxruntime onnxruntime-gpu
& data/bootstrap/uv/uv.exe pip install --python .venv/Scripts/python.exe onnxruntime-gpu==1.23.2
```

3. Finish buffalo_s from the official URL (if remote asset unchanged):

```powershell
curl.exe -L --fail -C - --retry 5 --retry-all-errors -o data/insightface/models/buffalo_s.zip https://github.com/deepinsight/insightface/releases/download/model-zoo/buffalo_s.zip
# verify the complete ZIP before extracting
Expand-Archive -LiteralPath data/insightface/models/buffalo_s.zip -DestinationPath data/insightface/models/buffalo_s -Force
```

4. Run `.venv/Scripts/python.exe tools/check_env.py`; fix actual missing
   dependencies/conflicts. ONNX CPU and GPU packages must not coexist.
5. Run `.venv/Scripts/python.exe -m tools.gpu_baseline --check-face`, save log,
   JSON and actual versions. Keep profiler output showing CUDA execution.
   Synthetic model/embedding checks are not biometric accuracy evidence.
6. Rerun the relevant suite after dependency changes, using a fresh basetemp
   under `data/` if the sandbox cannot access default Windows temp.
   Update report counts, GPU measurements/versions and evidence links; save
   environment freeze. Review final diff. The GPU fields are currently pending.
7. Handoff for DQK review/team interface freeze and real HIL/D1. No real JetBot
   connection or fabricated HIL results. Formal reviewed-PR/merge remains pending.

See `docs/W1-HNHL.md` for commands/contracts and `week-01.md` for the report.
