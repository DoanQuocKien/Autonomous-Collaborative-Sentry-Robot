# HNHL Week 1: Networking and GPU baseline

Owner: HuynhNguyenHoaiLoc. Scheduled week: 2026-10-05 through 2026-10-11.
Development started 2026-10-04. Hardware setup, gamepad e-stop and D1 recording
remain with DQK; record/replay tooling remains with KR.
The branch now integrates main through `7d34e46` (DQK/KR's W1 changes).

## Environment and checks

Follow GPU setup A in [Setup.md](Setup.md). HNHL's local environment is `.venv`
with Python 3.12 (no Conda needed); the equivalent commands use
`.venv\Scripts\python.exe` instead of the activated `sentry` interpreter.
Configure your IDE to use that interpreter. `.venv`, downloaded weights,
Python bootstrap and caches under `data/` are gitignored.

```powershell
.venv\Scripts\python.exe tools/check_env.py
.venv\Scripts\python.exe -m pytest -m "not gpu and not hil" --basetemp=data/pytest-tmp -q
.venv\Scripts\python.exe -m tools.gpu_baseline --check-face
```

`gpu_baseline.json` records package versions, the actual GPU, a CUDA torch
computation, ONNX Relu output plus the executed provider from the ORT profile,
and optional InsightFace buffalo_s detection and 512-d embedding inference.
Both YOLOv8n and YOLOv8s use batch 1, FP32, a seeded synthetic 640x640 BGR
image, configured warmup/iterations, and CUDA synchronization around wall time.
FPS includes `predict()` preprocessing and postprocessing. Peak allocated and
reserved memory are **PyTorch allocator** measurements, not total process VRAM
(InsightFace/ORT and the display can consume additional memory).
This is a speed baseline, not an accuracy measurement or full-pipeline budget.
RTX 5060 results must not be presented as RTX 4050 evidence.
The completed W1 measurements are in
[the weekly report](../reports/HuynhNguyenHoaiLoc/week-01.md).
The profiler uses `quantize=32` on current Ultralytics, or `half=False` on
older versions, and verifies the actual parameter dtype. GPU power/clock/
temperature snapshots are included. Use `--power-source plugged-in` or
`--power-source battery` when that state is known; otherwise it stays
`unspecified`.

Tunables are in root `config.toml`, sections `net`, `telemetry` and `profiling`.

Laptop timestamps consistently use the monotonic, high-resolution
`time.perf_counter()` clock. On Python 3.12/Windows, `time.monotonic()` can
have ~15.6 ms resolution; mixing these clock domains would corrupt latency.
Jetson `t_cap` remains its original `time.monotonic()` value and is converted
using the measured clock offset.

## Live and replay contract

```python
from sentry.net.zmq_rx import ZMQReceiver

with ZMQReceiver(ip="192.168.137.20") as receiver:
    frame = receiver.read(timeout=1.0)
    if frame is not None:
        image = frame.frame_bgr
        source_time = frame.t_cap
```

`read()` consumes one latest frame, returns `None` on timeout or after shutdown,
and raises `RuntimeError` on worker failure. It has one consumer. A consumer
must not modify `frame_bgr` when sharing it with other modules.
`VideoFrame` also carries the source sequence, original JPEG bytes, local
receive time and local decode-completion time. KR's replay adapter can return
the same class; `tools.replay.ReplayStream.read(timeout)` now returns it and
preserves source `t_cap`/sequence, JPEG bytes and recorded local times. The
legacy `(frame_bgr, timestamp)` iterator remains available. For older JetBot
recordings without local timing fields, `t_rx`/`t_decode` are generated during
replay; they are not historical receive-latency evidence. ESP32's iterator
still uses its own metadata and is separate from the JetBot clock contract.
The receiver accepts sequence resets after publisher restarts.
Context/socket creation failures are propagated through the same worker-error
contract, and partially created resources are closed. Shared packet decoders
reject numbers outside the finite float range with `ValueError`, so invalid
numeric packets are discarded instead of terminating receivers or clock echo.

The worker owns the ZMQ socket, drains complete `[header, JPEG]` messages,
decodes the newest drained message and overwrites one slot. Invalid messages
are discarded and a later valid message recovers automatically. Queue/drain
bounds prevent indefinite work or memory growth with a slow consumer.
`CONFLATE` is intentionally absent because [libzmq does not support multipart
conflation](https://libzmq.readthedocs.io/en/latest/zmq_setsockopt.html#zmq-conflate-keep-only-last-message).
Review this correction at the W1 interface freeze; wire bytes are unchanged.
`tools.record.record_jetbot` uses the same receiver, stores original JPEGs,
and numbers files independently of source sequence to avoid overwriting a
previous recording when the publisher restarts. Latest-frame drops can still
occur during slow disk writes; source sequence gaps document these skips.

## UDP control

```python
from sentry.net.udp_tx import UDPSender

with UDPSender(ip="192.168.137.20") as sender:
    accepted = sender.send(v=0.0, w=0.0)
```

The caller runs the control loop at 30 Hz or faster. `send()` is nonblocking
and returns `False` when called too soon or when the OS send buffer is full.
There are no retries, accumulated bursts, or background heartbeats repeating
stale motion commands. Commands validate finite normalized v/w. Positive w
turns left; the Jetson still owns wheel mixing and the speed cap.
`stop()` and context exit immediately attempt a zero packet, bypassing rate
limiting. UDP delivery is not guaranteed; the robot-side watchdog is still
required. The sender is for one control loop, not concurrent callers.

Manual HIL command (with DQK, robot wheels raised for first runs):

```powershell
.venv\Scripts\python.exe -m tools.send_cmd --ip <jetbot-ip> --v 0.1 --seconds 2
```

`--silent-end` omits the final zero after normal completion for DQK's watchdog
test; an exception still attempts a zero. This is separate from the HIL speed
cap enforced by `jetson/robot_udp.py --max-speed`.

## Clock sync and CSV latency

On the Jetson, run `jetson/robot_udp.py` (or `--dry-run` for transport testing)
to enable clock echo port 5557 and `jetson/camera_pub.py` for video port 5555.
The current robot deployment uses the `jetbot_jupyter` container; follow
Setup.md. Motor movement additionally requires the host `jetson/estop.py`
interlock to be armed with R1 held; a telemetry run does not drive the motors.
Then on the laptop:

```powershell
.venv\Scripts\python.exe -m tools.log_latency --ip <jetbot-ip> --seconds 30
```

This tool sends only clock probes. Twenty valid echoes produce
`offset = t_jetson - (t0 + t1)/2` from the exchange with the minimum RTT.
Convert capture time with `t_cap_local = t_cap_jetson - offset`.
Asymmetric delay is unknown; half the chosen RTT is the uncertainty bound.
Wrong/stale echoes are ignored; missing echoes fail instead of using zero.
Resync after a Jetson restart (monotonic clock resets) or a network change.

CSV stores raw timestamps, offset, RTT, receive latency and decoded latency.
The JSON summary reports p50/p95, delivered/run FPS, negative-latency flags,
sequence resets and gaps. Gaps include deliberate latest-frame drops and are
**not** a UDP packet-loss measurement. Negative latency or source restart
prevents a pass. HIL target: decoded p95 < 50 ms and run FPS >= 20.
`camera_pub.py` timestamps after camera read, so this excludes exposure/read
time; document this limitation in DQK's HIL evidence.

Local socket tests are marked `loopback`; they prove transport compatibility
without implying Wi-Fi or real-robot acceptance. T0-only new tests can be run
with `-m "not gpu and not hil and not loopback"` (the older camera publisher
test also uses localhost and predates this marker).

End-to-end CLI smoke test without the robot:

```powershell
.venv\Scripts\python.exe -m tools.check_net --fps 30 --seconds 5
```

This runs the Jetson synthetic publisher and clock echo locally, with a
simulated 100-second clock offset, then invokes the real latency logger.
Output is explicitly labelled synthetic localhost evidence. At a source rate
of exactly 20 FPS, encode/scheduling overhead in the synthetic generator can
lower measured FPS below 20; use 30 FPS to test the telemetry pass calculation.
The simulated offset must be finite. Publisher sleep is interruptible with
bounded, high-resolution slices, so even a low source FPS can shut down promptly
without reducing normal Windows timer precision.

## Integration status after main sync

- DQK has recorded real-camera 20 FPS/p95 53 ms, control loss 0%, watchdog
  305-315 ms and wheels-off gamepad e-stop evidence. See
  [DQK's report](../reports/DoanQuocKien/week-01.md). These are DQK's recorded
  runs, not measurements performed by HNHL; p95 53 ms misses the <50 ms target.
- DQK: rerun final real video latency with the integrated HNHL receiver/logger.
- Team: review/freeze multipart/latest-frame and `VideoFrame` contracts; record D1.
- KR/HNHL: review the proposed GC2145 UDP-tile/HTTP-relay interface before freeze;
  integrating the code does not approve that proposal or prove firmware HIL.
- DQK/RTX 4050 host: rerun GPU baseline for the specified 6 GB target.
- DQK: review HNHL's branch/PR; merge after T0 passes and one approval.
