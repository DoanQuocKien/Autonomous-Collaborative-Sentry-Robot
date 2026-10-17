# Edge Feasibility: the sentry on the Jetson Nano

> **Status (2026-10-16, evening):** this desk study was written before the on-robot measurements. Its stage E0 (the bench) is done: see `docs/Edge Deployment.md`. Where its estimates and those measurements differ, the measurements win (for example the Stage B frame-to-result time was estimated at 85-150 ms and measured at 38 ms mean, 51 ms p95, nobody in view; SCRFD's FP16 accuracy risk turned out to be a TensorRT 7.1 `Resize` bug, fixed). Its sources are search snippets that were not read in full. The staging and the gates it proposes are adopted, with changes, in `Implementation Plan.md` section 5 (extra task, gates G0-G4) and `Project Specification.md` section 4.7; the plan's strike limit is 150 ms frame to command.

Question (2026-10-16): can the robot run the sentry nearly self-contained on its Jetson Nano 4GB (JetPack 4.5, TensorRT 7.1.3, Python 3.6), with the laptop reduced to a companion app (start/stop, live view, confirm intruders)? If yes, in what stages, with what budget and what risks.

Inputs: the trtexec FP16 measurements and robot facts of 2026-10-16 (network only, batch 1, camera and control services running), `docs/Project Specification.md`, `docs/Implementation Plan.md`, `docs/JetBot Notes.md`, the code in `jetson/` and `sentry/`. Every number marked **est.** is an estimate from this study, not a measurement. Measured numbers come from the inputs table unless a source [n] is given.

**Answer: go, staged.** The models fit on the Nano in GPU time and RAM with a 2x margin if the expensive work is gated. The cost is engineering time (a TensorRT wrapper, a Python 3.6 port of the pursuit code, a vendored ByteTrack), not compute. Stage A (obstacle detector on the robot) fits before the mid-term and gives the report its on-device deployment chapter; Stage B (pursuit loop) after it; Stage C (door pipeline, search, robot as access point) only if B is done by Sun Dec 6.

## 1. Compute budget per stage

Rules used: one CUDA context in one process; engines run one after another on the Nano's single GPU (concurrent engines only interleave, they do not add throughput), so GPU time is a sum. "GPU %" = network ms x rate / 1000 ms. CPU is in % of one A57 core (400 % total).

### 1.1 What runs, at what rate

| Work | Engine | GPU ms | Rate (gated) | GPU ms/s | Stage |
|---|---|---|---|---|---|
| Obstacles (furniture) | YOLOv8n 320 | 14.8 | 15 Hz exploring; 5 Hz in pursuit (furniture does not move) | 222 / 74 | A, B |
| Person boxes + keypoints (pursuit, strike) | YOLOv8n-pose 320 | 15.7 | every frame, 15 Hz | 236 | B |
| Target lock / re-lock | OSNet x0.25 | 9.3 per crop | new tracks and every 0.5 s: about 1 crop per 5 frames; burst 3 crops on re-lock | 28 avg; 28 ms in one frame | B |
| Door faces | SCRFD 500m 320 | 7.9 | <= 5 Hz, only on frames with changed tiles | 40 | C |
| Door embeddings | MobileFaceNet | 14.8 per face | <= 5 faces/s; best 3 frames per person | 74 (1 face), 220 (3 faces) | C |
| Door body crop | YOLOv8n 320 on the door frame | 14.8 | 1 Hz while an unknown face is in view | 15 | C |
| Door appearance vector | OSNet x0.25 | 9.3 | once per intruder | ~0 | C |
| Entrance check | XFeat backbone 480x640 | 37.2 | 1-2 Hz, Phase 1 only | 37-74 | Phase 1 |
| Entrance (phone-photo mode) | DINOv2 ViT-S/14 | 359.5 | on demand, Phase 1 only, never with pursuit | - | Phase 1 |

Using YOLOv8n-pose as the person detector in pursuit is the main saving: it gives the person boxes for ByteTrack and the keypoints for the strike detector in one pass, so the obstacle detector drops to 5 Hz. OSNet-AIN x1.0 (26.6 ms) is affordable only for the once-per-intruder door embedding, not for the per-frame lock; the lock and the door must use the same model, so x0.25 is the edge choice unless the W4 Rank-1 comparison shows it misses 85 %.

### 1.2 Budget per stage (15 Hz robot camera)

| | A: obstacles + watchdog | B: whole pursuit loop | C: B + door + search |
|---|---|---|---|
| GPU ms per robot frame | 14.8 | 15.7 + 4.9 + 1.9 = 22.5 avg; 49 burst | 22.5 + door work slotted between frames |
| GPU ms/s (duty) | 222 (22 %) | 338 (34 %) | 338 + 130 to 290 = 470-630 (47-63 %) |
| GPU duty at 20 Hz | 30 % | 45 % (burst 49 ms in a 50 ms period: tight) | 58-74 % |
| CPU, main loop **est.** | capture 15 %, undistort remap 6 %, pre/post 8 %, grid 2 %, preview JPEG 3 % = ~35 % | + pose decode 4 %, ByteTrack 3 %, PD and hold < 1 % = ~45 % | + tile receive/decode 5-30 %, demosaic 3 %, face align 1 % = 55-80 % |
| CPU, other processes (measured) | robot_udp, estop, nvargus, camera_pub (25 % today, drops to a 5 Hz preview) | same | same |
| RAM, inference process **est.** | 0.5-0.7 GB (CUDA context + TensorRT libraries ~0.45 GB, engines 9 MB, buffers) | 0.6-0.8 GB | 0.7-0.9 GB |
| RAM, system **est.** | 1.3 GB today + 0.7 = 2.0 GB of 3.96 | 2.1 GB | 2.2 GB; 1.9 GB after stopping the jupyter and stats/OLED containers (293 MB RSS) |
| Power over today **est.** | +1.5-2.5 W | +3-4 W | +4-5 W |
| Frame-to-command latency **est.** | - | camera path ~40 + frame wait 0-67 + process ~33 + local UDP + I2C ~10 = 85-150 ms | same; door work must never delay a robot frame |

Latency comparison: the laptop path adds the Wi-Fi uplink (p50 12 ms, p95 22-53 ms measured), the laptop's own processing and the UDP return, so the edge loop saves about 30-70 ms at p95 **est.** against the 150 ms strike target, and removes link loss from the control loop entirely.

Battery **est.**: a 3S 18650 pack of 2.6-3.0 Ah cells is 29-33 Wh nominal, about 24 Wh usable down to 10.5 V (cell capacity is not recorded; check the cells). +4-5 W of compute is about 1 h less runtime at a 6-10 W total draw; sessions are 1-2 h, so runtime is not the limit. Peak current is: GPU bursts plus a motor reverse pulse at low voltage can brown the Nano out, which is already the reason for the 10.5 V stop rule. Run at MAXN (10 W) and watch for thermal throttling (`tegrastats`) in the first 10-minute bench; the 5 W mode cost a third of the frame rate in a Nano robot study [12] and would break the 15 Hz budget of Stage C.

### 1.3 Concurrency, time slicing, gating

| Item | Policy |
|---|---|
| GPU scheduling | One inference process, one CUDA context (a second context costs ~0.2-0.3 GB **est.**). Fixed priority per robot frame: pose -> obstacle (every 3rd frame) -> OSNet lock -> door work in the remaining slack of the 67 ms period. Door frames are dropped, never queued. |
| Door gating | The tile stream already says which tiles changed: no changed tiles, no SCRFD. MobileFaceNet only for faces above the size where verification works (measure on D2). One OSNet vector per intruder. |
| Phase gating | XFeat/DINOv2 run only in Phase 1 (no pursuit, no door). Pursuit models load at the Phase 2 -> 3 switch, or stay loaded (RAM allows it). |
| Search | Coverage tour planned once when the Phase 1 map is saved (the laptop target is < 2 s; on the A57 5-10 s **est.**, done while the robot is parked); at handoff only A* from the current pose to the tour (ms). |
| Processes | Keep `estop.py` and `robot_udp.py` unchanged. The on-robot brain sends the same `{"seq","v","w"}` packets to 127.0.0.1:5556, so the watchdog, dead-man and speed cap still apply and the laptop and edge modes share one control path. |

## 2. CPU-bound work on 4x A57

| Work | Cost **est.** | Mitigation |
|---|---|---|
| Robot camera capture | today 25 % of a core with BGR convert + JPEG q60 at 20 fps | Let `nvvidconv` (hardware) output the inference size; keep `videoconvert` out; JPEG only for a 5 Hz 320x240 preview |
| Fisheye undistort (`obstacle.py` remaps the full frame) | 3-5 ms per 640x480 frame with precomputed maps | Remap at 320x240, or run the detector on the raw frame and undistort only box points (`fisheye.undistortPoints`); needs an accuracy check on D1 |
| JPEG decode, OV2640 MJPEG VGA 15 fps | 6-10 ms per frame with libjpeg-turbo = 9-15 % of a core | Software decode is fine: forum reports put the Nano's `nvjpegdec` below software `jpegdec` (4.19 vs 25 fps in one case) and libjpeg/libnvjpeg conflict with OpenCV [8]. Decode at half size (`IMREAD_REDUCED_COLOR_2`) for motion, full size only when a face is present |
| GC2145 tile stream (the frozen interface) | each changed 64x32 tile is a small grayscale JPEG: up to 150 tiles x 10 fps in large motion = 1500 decodes/s at 0.1-0.2 ms = 15-30 % of a core; near 0 when the door is still | Already motion-gated by the firmware; demosaic + LUT 2-3 ms per new frame |
| Pre-processing | letterbox resize + float cast 2-3 ms | Put HWC->CHW and /255 inside the ONNX graph (TensorRT 7 has no uint8 input, so feed float32 HWC) |
| YOLOv8 decode + NMS | 1x84x2100 at 320: class max 1-3 ms in numpy, `cv2.dnn.NMSBoxes` < 0.5 ms; pose (1x56x2100) the same | 320 input keeps it small; TensorRT 7.1's `BatchedNMS_TRT` plugin only if numpy proves too slow |
| ByteTrack | 1-2 ms for < 10 tracks (Kalman + IoU + assignment) | Ultralytics needs Python >= 3.8, so vendor the original ByteTrack tracker (MIT, ~300 lines) with numpy IoU and `scipy.optimize.linear_sum_assignment` instead of `cython_bbox`/`lap` |
| Occupancy grid | ~1 ms per frame (`cv2.fillPoly` of the seen floor, point updates) | Update at 5 Hz |
| Coverage planning | 5-10 s per plan in Python | Plan once at the end of Phase 1; A* per leg only |
| Python GIL | camera thread + inference + tile receiver in one interpreter contend | Tile receiver and camera in their own processes (shared memory or a local ZeroMQ socket); one inference process |

Python 3.6 port (applies to anything moved from `sentry/`): 30 uses of 3.7+ features in 6 files (`from __future__ import annotations`, `X | None` hints, `tomllib` in `config.py`), `dataclasses` (pip backport works on 3.6), and `cv2.aruco.ArucoDetector` in `camera_pose.py`/`localization.py`, which needs OpenCV >= 4.7; the robot has 4.1.1, so the legacy `cv2.aruco.detectMarkers` call is needed, and whether the JetPack OpenCV build has the aruco module at all is unchecked.

## 3. Inference runtime

| Candidate | On JetPack 4.5 / Python 3.6 | Cost | Verdict |
|---|---|---|---|
| **TensorRT Python API + pycuda** | TensorRT 7.1 bindings ship with JetPack; pycuda builds from source with pip | Loads our trtexec `.engine` files directly; no extra runtime; ~120-line wrapper | **Recommended** |
| jetson-inference / jetson-utils | builds from source | `detectNet` does not parse YOLOv8 outputs without C++ changes; jetson-utils (zero-copy CSI capture) is useful on its own | Optional for the camera only |
| DeepStream 5.1 | runs on JetPack 4.5.1 per users [7] | Custom YOLOv8 parser in C++, GStreamer configs; one user reports 1.5 GB used at idle and 2.7 GB with a 25 MB engine [7] | No: too heavy for a 4 GB board shared with our stack |
| ONNX Runtime (Jetson Zoo wheels) | Python 3.6 GPU wheels exist and run on JetPack 4.6.3 with an older protobuf [5]; the TensorRT execution provider needs a source build [6] | CUDA provider only, slower than a TensorRT engine **est.** | Only for a parity check against the laptop |
| torch2trt | needs PyTorch on the robot | Converts PyTorch modules; we already have ONNX -> engine via trtexec; importing torch costs ~1 GB RAM **est.** | No |

Wrapper effort **est.**: deserialize engine, page-locked host and device buffers per binding, `execute_async_v2`, stream sync: half a day. YOLOv8 / pose decode and NMS: half a day. Parity against the laptop ONNX on 200 D1 frames (boxes matched at IoU > 0.9 for >= 95 % of detections; the inputs list parity as not yet checked): one day. **About 2 person-days.** If pycuda will not build, `ctypes` on `libcudart.so` (`cudaMalloc`, `cudaMemcpyAsync`) is a ~40-line fallback. Build engines on the robot itself (engines are tied to the device and TensorRT version) and pin ONNX opset 11.

## 4. Networking without the laptop hotspot

With the models on the robot, video latency (risk 16, the p95 < 50 ms target) leaves the control loop; the network only carries the ESP32 stream (if the door pipeline runs on the robot), a 5 Hz preview and events.

| Option | Facts | Verdict |
|---|---|---|
| Robot as access point (hostapd or `nmcli device wifi hotspot` on the RTL8822CE) | Unverified on our vendor driver `rtl8822ce` (L4T R32.5, kernel 4.9). On an Orin Nano the in-tree module showed no AP mode and the rtw88 driver did [10]. A 5 GHz AP on this chip is refused on DFS/radar channels [11], and our robot runs the generic `world` regulatory domain, which also blocks 5 GHz AP **est.**. Concurrent AP + STA is not enabled by default on Jetson | Possible on 2.4 GHz only; check first with `iw list` ("Supported interface modes: AP", "valid interface combinations"), 1 minute on the robot |
| Travel router ($20-30, already the gate item in `Hardware.md` section 2) | Both bands at once, fixed IPs, no load on the robot or the laptop radio | **Recommended** for Stage C and for demo day; independent of the driver |
| Phone hotspot | Fallback already listed in `JetBot Notes.md`; clients must be able to reach each other | Demo-day fallback |
| Laptop hotspot (today) | Works, p95 22-53 ms | Keep until Stage C; fine in laptop mode |

How the ESP32-CAM joins: it is 2.4 GHz only, so any AP it joins must serve 2.4 GHz. The tile firmware finds its receiver by a `HELO` broadcast, so it works on any subnet where the receiver (`sentry.espcam.TileReceiver`, then on the robot) is on the same network. Give the new AP the same SSID and password as the laptop hotspot and neither the ESP32 nor the robot needs reflashing or a new profile. Traffic is small: the tile stream measured 0.06-0.2 Mbit/s on a still scene (motion bursts unmeasured), the preview ~1 Mbit/s **est.**. `TileReceiver` must be ported to Python 3.6 (it imports `sentry.net.discover`; small).

## 5. Companion-app interface (same for laptop or robot models)

One "brain" process publishes and accepts these, wherever it runs. Robot -> app: ZeroMQ PUB, multipart `[json, optional jpeg]`. App -> robot: ZeroMQ REQ/REP (commands need an answer). Motion permission stays with the gamepad dead-man; the app can always stop, never override it.

| Message | Direction | Fields |
|---|---|---|
| `status` | brain -> app, 1 Hz | `t, phase, state, battery_v, estop_armed, deadman, fps_robot, fps_door, gpu_ms, cpu_pct, temp_c, ram_mb, where` (`laptop` or `edge`) |
| `frame` | brain -> app, <= 5 Hz | `seq, t_cap, src` (`robot` or `door`), `w, h, dets: [{tid, cls, box, conf, is_target}]` + JPEG |
| `event` | brain -> app | `name` (`ENTRANCE_FOUND, INTRUDER_QUEUED, TARGET_STATIONARY, STRIKE, TARGET_EXITED, TARGET_FOUND, SEARCH_EXHAUSTED`), `t, data` |
| `intruder_candidate` | brain -> app | `id, t, face_sim_max, face_jpeg, body_jpeg, timeout_s` |
| `queue` | brain -> app, on change | `items: [{id, status (waiting, active, dropped, done), t_enter}]` |
| `map` | brain -> app, on change | `res_m, origin, guard_pose, png` |
| `start` / `stop` | app -> brain | `phase` (`setup` or `guard`) / none; reply `{ok, reason}` |
| `confirm` | app -> brain | `id, verdict` (`intruder` or `occupant`); unanswered candidates follow a configured default after `timeout_s` |

The state machine already consumes only events (`Implementation Plan.md` section 3), so the messages map onto it without new logic.

## 6. Prior work and independent numbers

| Claim | External number | Our number | Check |
|---|---|---|---|
| YOLOv8n FP16 on the Nano | about 19 FPS, inference only, input size not stated (likely 640) [1] | 23.8 ms at 416; scaled by pixels to 640: ~56 ms = 18 FPS **est.** | Consistent |
| SCRFD-0.5GF | 3.6 ms at VGA on a desktop GPU, 28.3 ms on one desktop CPU thread [2] | 7.9 ms at 320 on the Nano GPU | Plausible; CPU-only on the A57 would be ~100 ms **est.**, so the face detector belongs on the GPU |
| Face pipeline on the Nano | MTCNN + ArcFace ResNet-50 with TensorRT, ~10 FPS end to end [3] | SCRFD + MobileFaceNet 22.7 ms network for one face | Our lighter pair should run 15-25 FPS end to end **est.** |
| OSNet + tracker on Jetson | FastMOT runs OSNet in TensorRT on a Xavier NX and advises lighter models for the Nano [4] | OSNet x0.25 9.3 ms | Supports gating re-ID instead of running it per box per frame |
| ByteTrack on ARM | no published per-frame cost found | 1-2 ms **est.** | Unverified; measure in the bench |
| Nano power | ~4.1 W at MAXN under CPU-only stress [9] | not measured with GPU load | Measure with `tegrastats` |
| Self-contained Jetson Nano robots | person-following robot: YOLOv3-tiny 9 FPS on the Nano at 10 W, 6 FPS at 5 W, detector only; the full system ran on an AGX Xavier [12]. No complete Nano-only sentry robot with reported FPS was found | Stage B mix ~44 FPS network-only **est.** (1000 / 22.5) | Our models are lighter than YOLOv3-tiny and run in TensorRT FP16; the 5 W mode costs ~1/3 of the rate, so stay at MAXN |

The sources found no contradiction with the measured table. A forum report of YOLOv5 + DeepSORT on a Nano at 4-6 FPS (about 100 ms in DeepSORT, URL not recorded) is the warning case: a per-box, per-frame re-ID tracker in Python is what breaks the budget, hence ByteTrack (no re-ID) with OSNet gated. All external figures above come from search snippets, not read in full.

## 7. Staged plan, risks, recommendation

### 7.1 Stages

| Stage | Weeks | Content | Effort **est.** (person-days) | Gate to continue |
|---|---|---|---|---|
| E0 bench | **done 2026-10-16** (person in view, ESP32 frames and the battery run remain: W3, gate G1) | TensorRT + pycuda wrapper, YOLOv8 decode, parity on D1, then the Section 7.4 bench | 2-3 (DQK) | Stage B model mix >= 15 FPS on live frames, CPU < 200 %, system RAM < 3.0 GB, no throttling in 10 min |
| A | W4-W5 | Obstacle detector + repulsion on the robot, camera preview to the laptop; laptop path kept as the fallback | 4 (DQK, HNHL for parity) | 0 collisions in the existing exploration protocol, same distance errors as on the laptop |
| Mid-term | W6-W7 | FP32 vs FP16 vs laptop latency, RAM, power, parity table: the "model optimisation and on-device deployment" chapter | 1-2 (HNHL), replaces part of the W6 laptop-only optimisation | figures frozen Sun Nov 15 |
| B | W8-W9 | Pose + strike detector, vendored ByteTrack, OSNet x0.25 lock, PD/hold ported to 3.6, brain -> local UDP | 8-10 (DQK, HNHL; KR ports hold logic) | pursuit and hold rows of section 4.3 pass on the edge path; strike latency <= 150 ms |
| C (stretch) | W10-W11 | Door pipeline on the robot, queue, pre-planned coverage search, robot or router network, companion app | 8-12 (all) | only if B passed by Sun Dec 6; otherwise the door stays on the laptop |

Pursuit and hold stay on the laptop for the mid-term demo (the plan's W5-W6), so the report does not depend on Stage B. Total A + B is about 15 person-days, roughly one fifth of the team's remaining time; C would compete with the W10 full-loop integration and the W11 contingency week, which is why it is a stretch. Staying in the laptop mode for the door costs little: the laptop is present anyway to confirm intruders, and only small events cross the link.

### 7.2 Top risks (ranked)

| # | Risk | Effect | Mitigation |
|---|---|---|---|
| 1 | End-to-end rate falls well below the network-only sums (Python pre/post, GIL, camera path, copies) | Stage B under 15 FPS, strike window unmet | E0 bench before any port; pose-as-detector, 320 inputs, gating; drop to 12 Hz with a timestamp-based strike window (risk 1 of the plan) |
| 2 | Accuracy parity of FP16 engines vs the laptop models is unchecked; OSNet x0.25 may miss the 85 % Rank-1 that x1.0 reaches | Wrong locks, missed intruders | Parity check in E0; W4 Rank-1 comparison decides; INT8 is out of scope |
| 3 | Python 3.6 port and dependencies (no ultralytics, OpenCV 4.1.1 without the new aruco API, pycuda build) | Weeks lost to tooling | Keep edge code in `jetson/`-style 3.6 modules; vendor ByteTrack; ctypes fallback; check `cv2.aruco` on the robot first |
| 4 | Power and heat: GPU bursts plus motor reverse at low battery brown out the Nano; MAXN throttling | Resets mid-demo, SD corruption | `tegrastats` in the bench; 10.5 V rule; fan check |
| 5 | Single robot, school property: more software on the SD card | A bad install blocks every T2 | Back up the SD card before installing; everything in `/home/jetbot/sentry` and a venv/container; add each install to the return checklist |
| 6 | Network change (robot as AP) late in the term | Demo-day connectivity | Keep the laptop hotspot as the default until C; see Section 4 |

### 7.3 Recommendation

**Go, staged.** Do E0 now, Stage A before the mid-term, Stage B after it, Stage C only on the Dec 6 gate. The three numbers that drive it: Stage B needs 22.5 ms of GPU per frame (34 % duty at 15 Hz), the whole of Stage C peaks at about 63 % GPU duty, and the system needs about 2.2 GB of the 3.96 GB RAM. The limit is the porting effort (about 15 person-days for A + B), not the hardware.

### 7.4 Cheapest experiment that removes the most uncertainty

One 10-minute bench on the robot (1 day after the wrapper exists): a single Python 3.6 process that reads the live CSI camera, runs YOLOv8n-pose 320 every frame, YOLOv8n 320 every third frame and OSNet x0.25 on one crop every fifth frame, does the letterbox, decode and NMS, and runs SCRFD + MobileFaceNet at 5 Hz on recorded door frames from a file; `camera_pub` and `robot_udp` keep running. Log per-stage times from `t_cap` to "command ready", FPS, `tegrastats` (CPU per core, GPU %, RAM, temperature, power rails) and battery voltage before and after. It measures the four unknowns at once: end-to-end rate, CPU headroom, RAM with one CUDA context, and thermal/power behaviour. Wheels off the ground, no motor commands needed.

## References

[1] Qengineering, YoloV8-TensorRT-Jetson_Nano, https://github.com/Qengineering/YoloV8-TensorRT-Jetson_Nano
[2] InsightFace, SCRFD README, https://github.com/deepinsight/insightface/blob/master/detection/scrfd/README.md
[3] KICS journal, face recognition on Jetson Nano with TensorRT, https://journal.kics.or.kr/digital-library/37607
[4] FastMOT, https://github.com/geekalexis/fastmot
[5] NVIDIA forum, pre-built onnxruntime on Jetson Nano, https://forums.developer.nvidia.com/t/jetson-nano-fails-to-install-pre-built-onnxruntime/259049
[6] NVIDIA technical blog, ONNX Runtime with TensorRT on Jetson, https://developer.nvidia.com/blog/?p=19761
[7] NVIDIA forum, DeepStream memory use on Jetson Nano, https://forums.developer.nvidia.com/t/memory-usage-when-loading-unet-for-inference-on-jetson-nano/182596
[8] NVIDIA forum, nvjpegdec slower than jpegdec on Jetson Nano, https://forums.developer.nvidia.com/t/use-nvjpegdec-slower-than-jpegdec-on-jetson-nano/319892 and https://forums.developer.nvidia.com/t/nvjpegdec-does-not-work-for-usb-camera/280767
[9] CNX Software, Jetson Nano with and without fan, https://www.cnx-software.com/2019/12/09/testing-nvidia-jetson-nano-developer-kit-with-and-without-fan/
[10] NVIDIA forum, RTL8822CE access point mode, https://forums.developer.nvidia.com/t/rtl8822ce-access-point-mode/288083
[11] Arch Linux forum, RTL8822CE 5 GHz AP refused on a DFS channel, https://bbs.archlinux.org/viewtopic.php?id=301988
[12] Person-following robot with YOLOv3-tiny on Jetson Nano and AGX Xavier, https://arxiv.org/pdf/2008.13474
