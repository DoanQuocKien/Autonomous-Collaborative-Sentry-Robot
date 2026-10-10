# Week 01 - HuynhNguyenHoaiLoc (2026-10-05 to 2026-10-11)

Development started early on 2026-10-04. Branch:
`HuynhNguyenHoaiLoc/w01-network-telemetry`. Local implementation and tests are
ready for review; no PR has been merged, so the plan's formal definition of
done is still pending.

Resumed at HNHL's request on 2026-10-04 after the shutdown pause. Current
environment/measurement status is tracked below; historical handoff notes
are in [RESUME.md](week-01/RESUME.md).

## Implemented locally

- `sentry/net/zmq_rx.py`: socket-owning receiver thread, bounded multipart drain,
  JPEG decode and a single latest-frame slot; worker errors and clean shutdown.
- `sentry/net/frame.py`: `VideoFrame` live/replay contract for KR.
- `sentry/net/udp_tx.py`: normalized nonblocking v/w packets, 30 Hz rate limit,
  monotonic sequence, no stale-command heartbeat, immediate zero on context exit.
- `sentry/net/clock_sync.py`: 20 valid echoes, minimum-RTT Cristian estimate,
  timeout and malformed/stale-reply handling; synthetic delay T0 tests.
- `sentry/net/latency.py`, `tools/log_latency.py`: raw CSV timestamps and JSON
  latency/FPS summaries, signed clock correction, reset/negative-latency flags.
- `tools/check_net.py`: complete synthetic localhost publisher/echo/CSV smoke test.
- `tools/gpu_baseline.py`: reproducible YOLOv8n/s FP32 batch-1 profiling,
  CUDA/ONNX/InsightFace execution checks, package/GPU metadata and JSON evidence.
- Isolated Python 3.12 `.venv`; usage and integration notes in
  [W1-HNHL.md](../../docs/W1-HNHL.md).

## Tests run

| Tier / scope | Command (using `.venv/Scripts/python.exe`) | Result | Evidence |
| :-- | :-- | :-- | :-- |
| T0 + local transport | `-m pytest -m "not gpu and not hil" --basetemp=data/pytest-tmp-gpu-env -q` | 77 passed, 5.58 s in the complete GPU environment | [pytest.log](week-01/pytest.log) |
| Synthetic localhost telemetry | `-m tools.check_net --fps 30 --seconds 5` | 145 frames, 28.917 run FPS; decoded p95 1.887 ms | [JSON](week-01/loopback_latency.json), [CSV](week-01/loopback_latency.csv) |
| Environment | `tools/check_env.py` | ALL GOOD; CUDA torch, ORT GPU, InsightFace and torchreid available | [check_env.log](week-01/check_env.log) |
| GPU baseline | `-m tools.gpu_baseline --check-face --power-source unspecified` | Pass; CUDA Relu executed, buffalo_s detection + 512-d embedding, both YOLO models measured | [JSON](week-01/gpu_baseline.json), [log](week-01/gpu_baseline.log), [ORT profile](week-01/ort_cuda_2026-10-04_23-01-27.json) |

The localhost test simulates a 100-second Jetson/laptop clock offset and uses
the real multipart header/JPEG wire format. This verifies telemetry logic;
it is not Wi-Fi/HIL acceptance. No robot or motor connection was made.

## GPU baseline results

Measured 2026-10-04 on RTX 5060 Laptop GPU (8 GB), NVIDIA driver 591.74,
Python 3.12.15, torch 2.9.1+cu128, torchvision 0.24.1+cu128, ultralytics
8.4.172, insightface 2.1 and onnxruntime-gpu 1.23.2. Plain onnxruntime is
absent. All 72 installed distribution versions and download hashes are saved
in [environment_versions.json](week-01/environment_versions.json).

Protocol: seeded synthetic 640x640 BGR image, batch 1, FP32 (parameter dtype
checked), 10 warmup calls and 100 measured `predict()` calls. CUDA is
synchronized around wall time; preprocessing and postprocessing are included.
The final run used the current `quantize=32` API and ran after CPU tests ended.

| Model | FPS | Mean latency (ms) | p95 latency (ms) | Peak allocated (MiB) | Peak reserved (MiB) |
| :-- | --: | --: | --: | --: | --: |
| YOLOv8n | 49.179 | 20.334 | 27.025 | 33.545 | 58.000 |
| YOLOv8s | 26.060 | 38.373 | 40.740 | 78.616 | 94.000 |

Memory columns measure the PyTorch allocator, not total process/GPU VRAM.
GPU snapshots recorded an enforced power limit of **20 W**, temperatures
41-42 C around the final model runs, and variable clocks. AC/battery state
was not confirmed; the recorded `power_source` is `unspecified`. These
conditions matter when comparing later measurements or the RTX 4050 host.
This is single-model synthetic speed evidence, not accuracy, full-pipeline
budget or real-robot latency evidence.

The ORT profile records CUDAExecutionProvider executing Relu with correct
output. InsightFace buffalo_s executed detection on a blank BGR frame (no
faces expected) and recognition on a synthetic aligned crop, returning a
finite [1, 512] embedding with CUDA first in the model sessions. D2 biometric
accuracy remains a W3 task.

## Acceptance criteria status (Implementation Plan section 4.3)

- Video uplink p95 < 50 ms / >= 20 FPS: localhost smoke passes; **real JetBot
  HIL pending** with DQK. Source `t_cap` starts after camera read, excluding
  sensor exposure/read time.
- Control packet loss < 1% / watchdog <= 350 ms: protocol/rate-limit/exit-stop
  tests pass; **HIL measurements pending** with DQK.
- GPU baseline: **measured on HNHL's machine**; this machine has an RTX 5060 Laptop
  GPU (8 GB), not the spec's RTX 4050 (6 GB). DQK must rerun on RTX 4050 for
  target-hardware evidence. W1 measures models separately; full concurrent
  <= 5.5 GB / >= 15 FPS budget belongs to W5.

## Findings / risks / review points

- Corrected the planned `CONFLATE=1`: [libzmq explicitly does not support
  multipart conflation](https://libzmq.readthedocs.io/en/latest/zmq_setsockopt.html#zmq-conflate-keep-only-last-message).
  Preserve `[header, JPEG]`, bound/drain the SUB queue and overwrite the latest
  decoded slot. Review this clarification with all three members before the
  W1 interface freeze.
- Python 3.12 Windows `monotonic()` on this host reports 15.625 ms resolution
  (`GetTickCount64`). Laptop code now consistently uses `perf_counter()`
  (`QueryPerformanceCounter`, reported resolution 100 ns); remote Jetson
  monotonic timestamps remain unchanged and are corrected by sync offset.
- Seq gaps include deliberate frame skips; never report them as network packet
  loss. Resync after a Jetson restart or a network change.
- Updated stale `science_env`/Python 3.14 mentions in the HNHL W1/environment
  section to match [Setup.md](../../docs/Setup.md)'s Python 3.12 environment.
- Instructor's JetBot overview supports the camera/differential-drive and
  initial motor-test context. The project's specified laptop-AI + ZMQ/UDP
  architecture remains the implementation contract.
- D1 recordings, gamepad e-stop and integration hardware belong to DQK;
  record/replay/sim tooling belongs to KR. No D1/HIL evidence is fabricated.
- Added undeclared torchreid dependency `gdown` to the shared requirements.
  The optional Cython rank evaluator is unavailable; torchreid imports and
  uses its Python evaluation fallback. This is not a W1 inference failure.
- `check_env.py` now keeps generated Ultralytics settings in gitignored
  `data/ultralytics`, and the profiling tool supports current FP32 precision
  options while retaining compatibility with older `half=False` APIs.

## Next actions

- DQK review of the HNHL branch/PR, plus team review of the W1 video contract.
- Configure real JetBot IP, collect real video/control HIL evidence, record D1
  in the Oct 11 integration session, and confirm the mid-term due date.
- W2: obstacle distance/repulsion and vantage scoring after calibration/D1.

## Code consistency review (2026-10-10)

Reviewed the current W1 branch against the implementation plan, shared wire
protocol, Jetson publisher/controller, CLI tools and environment documentation.
The video/control formats, clock-offset sign and live/replay frame contract
are consistent. The existing baseline suite passed 77 tests before the fixes.

Regression tests reproduced two errors before correction: oversized JSON
numbers raised `OverflowError` outside the documented decoder contract, and
ZMQ context/socket creation errors bypassed worker error propagation/cleanup.
Both are fixed. The shared protocol and Jetson modules retain Python 3.6 syntax.

Additional corrections reject nonfinite simulated clock offsets, make low-FPS
smoke-test publisher shutdown interruptible, and require `check_env.py` to run
Relu and verify its executed CUDA provider rather than only list providers.
CLAUDE.md, Setup.md and the implementation plan now consistently describe
Python 3.12, HNHL's `.venv` and the distinction between RTX 5060 and RTX 4050.

| Check | Final result | Evidence |
| :-- | :-- | :-- |
| CPU + localhost suite | **87 passed in 6.81 s** | [review_pytest.log](week-01/review_pytest.log) |
| CUDA environment | **ALL GOOD**, ONNX Relu output and CUDA execution verified | [review_check_env.log](week-01/review_check_env.log), [profile](week-01/review_ort_cuda.json) |
| CLI localhost smoke, 30 FPS source / 5 s | **144 frames**, run **28.767 FPS**, decoded p95 **2.984 ms**, pass | [JSON](week-01/review_loopback_latency.json), [CSV](week-01/review_loopback_latency.csv), [log](week-01/review_loopback.log) |
| Jetson compatibility | `ast.parse(..., feature_version=(3, 6))` passes for common/ and jetson/ | Syntax check only; device execution still pending |

The 2026-10-04 GPU benchmark is retained as historical evidence; YOLO/InsightFace
benchmarks were not repeated during this review. New localhost measurements
remain synthetic and do not close HIL, D1 or RTX 4050 acceptance items.
PR title/body are prepared in [PR-W1-HNHL.md](../../docs/PR-W1-HNHL.md), targeting
`main` from `HuynhNguyenHoaiLoc/w01-network-telemetry`, with DQK as reviewer.
The original implementation has been committed on this branch; the review
fixes and new evidence are saved in the working tree for HNHL to commit/push.

## Hours

Not tracked; to be filled by HNHL.
