# Mid-Term Report Plan

**Due Mon 2026-11-23** (first day of Week 8). Deliverables: a 10-15 page report, the code (tag `midterm` + appendix), and an **optional** 2-4 min demo video (link). Schedule: `Implementation Plan.md` section 5, Weeks 4-7. Editor: KR; each chapter owner checks their own numbers.

Rules:
- Every number cites its evidence file (`reports/<handle>/week-NN/...`, `calib/*.json`). No file, no number.
- What is not built or measured yet is written as **expected** (with its threshold from Implementation Plan section 4.3 and its week), never as a result.
- The spec's roadmap (section 6) was rewritten on 2026-10-16 to the 13-week calendar: this report is 10-15 pages, due Mon 2026-11-23 (it replaced the earlier 15-20 pages in Week 4).

## 1. Outline and page budget (13.5 pages + 1 page appendix = 14.5)

| # | Chapter | Content (required item) | Pages | Owner |
| :-- | :-- | :-- | :-: | :-- |
| 1 | Introduction | Problem, the three phases, scope, hardware (item 1: description) | 1 | KR |
| 2 | Related work | Researched papers and what each one is used for (item 3) | 1.5 | KR compiles, all contribute |
| 3 | System architecture | Laptop / Jetson / ESP32 split, network and interfaces, safety design, and the optional on-robot inference mode (spec section 4.7) | 2 | DQK |
| 4 | Robot platform and calibration | Fisheye, camera pose, motion model, dead reckoning + ArUco | 1.5 | DQK (+KR localization) |
| 5 | Perception, optimization and on-device deployment | Obstacle distance, entrance (XFeat / DINOv2), face verification, re-ID, tracking; models, GPU budget; **5.x Optimization and deployment on the robot: ONNX to TensorRT conversion, FP16, latency and memory on the Jetson, parity with the laptop, what failed and how it was fixed (F20, F21)** | 3.5 | HNHL (+KR for entrance, DQK for 5.x) |
| 6 | Behaviour and control | State machine, Phase 1 deployment, queue, pursuit and hold | 1.5 | KR (+DQK controllers) |
| 7 | Tests and results to date | T0/T1/T2 tiers, section 4.3 status table, the "what has run" table (section 4 below), real-robot runs | 1.5 | KR, rows by owners |
| 8 | Expected results and remaining plan | Targets for evasion, search, full loop; Weeks 8-13; risks (item 2: expectation) | 1 | DQK |
| A | Appendix | Code: modules, owners, tests, how to run, tag link; demo video link and shot list (items 3-4) | 1 | KR |

Item 5 (images and charts): at least one figure per page in chapters 3-7 (section 3).

### 1.1 The instructor's required content (received 2026-10-16) and where it lands

The instructor's note lists six content items and a demo video (the video is optional if there are practical results). The mapping, so no item is missed:

| Instructor's item | Chapter | Evidence |
| :-- | :-- | :-- |
| Topic and goals: problem, application context, inputs and outputs, planned functions, final result wanted | 1, 8 | spec sections 1, 3 |
| Knowledge and technology studied: concepts, models, algorithms, architecture, libraries, and how each is used | 2, 3, 5 | section 2 paper list, section 4 table |
| Progress to the mid-term: what runs on the PC, camera data, robot control, methods tried, partial integration | 3-6 | section 4 table (R rows) |
| Current experimental results: tests, configuration, results, open problems, comparison of options and why one was chosen | 5, 7 | section 3 figures F1-F19, section 4.3 status |
| **Optimization and deployment on a real device: conversion, latency, memory, running on the edge device or robot** | **5.x** | **F20, F21, `docs/Edge Deployment.md`, `week-02/edge_deploy/`, video shot 8** |
| Plan for the next phase: what is missing, problems to solve, plan to the end of term | 8 | Implementation Plan section 5 (gates G0-G4) |
| Demo video (laptop model, camera data, robot control, model on the edge device, whole pipeline in real time) | appendix | section 5 shots 3-8 |


## 2. Researched papers

Each member adds 3+ papers from their area in Week 3. Candidates below are the methods the code already uses; **verify every reference before citing it**, and keep only what was actually read.

| # | Paper (verify) | Used for | Ch. | Added by |
| :-- | :-- | :-- | :-: | :-- |
| 1 | Rublee et al., "ORB: an efficient alternative to SIFT or SURF", ICCV 2011 | Entrance matching | 5 | KR |
| 2 | Kannala and Brandt, generic camera model for fish-eye lenses, TPAMI 2006 | `cv2.fisheye` calibration | 4 | DQK |
| 3 | Garrido-Jurado et al., ArUco fiducial markers, Pattern Recognition 2014 | Localization anchors | 4 | KR |
| 4 | Cristian, "Probabilistic clock synchronization", Distributed Computing 1989 | Clock sync | 3 | HNHL |
| 5 | Deng et al., "ArcFace", CVPR 2019; Chen et al., "MobileFaceNets", CCBR 2018; Guo et al., "SCRFD", ICLR 2022 | Face detection and embedding (`buffalo_s`) | 5 | HNHL |
| 6 | Zhou et al., "Omni-Scale Feature Learning for Person Re-Identification" (OSNet), ICCV 2019, and the OSNet-AIN follow-up | Re-ID | 5 | HNHL |
| 7 | Zhang et al., "ByteTrack", ECCV 2022 | Tracking | 5 | HNHL |
| 8 | Ultralytics YOLOv8 (software, cite the repository) | Detection, pose | 5 | HNHL |
| 9 | Galceran and Carreras, "A survey on coverage path planning for robotics", RAS 2013 | Search (expected) | 8 | KR |
| 10 | Potje, Cadar, Araujo, Martins and Nascimento, "XFeat: Accelerated Features for Lightweight Image Matching", CVPR 2024, arXiv:2404.19174 (reference verified against arXiv on 2026-10-15; **read in full on 2026-10-15**: sparse XFeat 27.1 FPS on an i5-1135G7 CPU at VGA, MegaDepth-1500 AUC@5/10/20 42.6/56.4/67.7 against ORB 17.9/27.6/39.0; the paper does not test in-plane rotation, fisheye images or repeated doors, so our inlier threshold stays empirical; code vendored in `third_party/xfeat/`, Apache-2.0) | Entrance matching (primary method after the bake-off, `sentry/perception/entrance.py`) | 5 | DQK |
| 11 | Oquab et al., "DINOv2: Learning Robust Visual Features without Supervision", TMLR 2024, arXiv:2304.07193 (reference verified against the paper text on 2026-10-15; torch hub, pinned commit) | Entrance matching with a phone reference (`sentry/perception/entrance.py`); cosine similarity of cls + GeM descriptors is our choice, the paper does not specify pooling for retrieval | 5 | DQK |
| 12+ | ... | | | |

## 3. Figures and charts

Each figure is saved as PNG next to its evidence in `reports/<handle>/week-NN/`, made by a committed script or tool. "Now" = the evidence exists on 2026-10-12.

| ID | Figure | Source (tool / evidence file) | Owner | Ch. | Ready by |
| :-- | :-- | :-- | :-- | :-: | :-- |
| F1 | System overview: three phases, laptop / Jetson / ESP32 | drawn from spec sections 1 and 5 | DQK | 1, 3 | W4 |
| F2 | Data flow with ports, rates and formats | Implementation Plan section 3 | DQK | 3 | W4 |
| F3 | Photo of the JetBot, gamepad and ESP32-CAM at the door | photo | DQK, KR | 1 | W5 |
| F4 | Fisheye: raw vs undistorted frame; per-view reprojection error bars | `calib/camera.json`, `reports/DoanQuocKien/week-02/fisheye_metrics.json` (now) | DQK | 4 | W4 |
| F5 | Camera pose fit: distance vs image row, marks vs model; tilt over sessions (2.6° down -> 1° up) and, once built, live marker tilt vs strip tilt | `week-02/camera_pose_nowedge.json` (PR #22), `calib/camera_pose_classroom.json`, `perception/camera_pose.py` output | DQK | 4 | W4 |
| F6 | Motion model: commanded vs measured speed and turn rate, drift | `week-02/motion_runs.csv` (now, v = 1.0 only), W3 runs, `calib/motion.json` | DQK | 4 | W4 |
| F7 | Video latency CDF and FPS; watchdog and e-stop stop times (table) | `week-01/link_test_2026-10-04.txt`, `estop_*_2026-10-06.txt` (now); re-measure with `tools.log_latency` CSV | DQK, HNHL | 3 | W5 |
| F8 | ESP32 tile stream: sample frame, FPS over time | `week-01/esp32_gc2145_jpeg_2026-10-09.txt` (now) | DQK, KR | 3 | W4 |
| F9 | GPU: FPS and VRAM per model and combined (RTX 4050; RTX 5060 labelled separately) | `week-01/gpu/gpu_baseline_rtx4050.json`, `gpu_baseline_2026-10-06.txt` (now); W5 profile | HNHL | 5 | W5 |
| F10 | Obstacle distance error vs tape (scatter, median, p90) | HNHL T1 metrics JSON on D1 classroom | HNHL | 5 | W4 |
| F11 | Occupancy map with the chosen sweet spot | `gridmap` / `vantage` output on a D1 sweep | HNHL | 5 | W4 |
| F12 | Entrance: ORB vs XFeat vs DINOv2 AUC and TPR at 5 % FPR per door, inlier / similarity distributions door vs no door | `week-02/d1/entrance_bench_2026-10-12.md` and `.json` (now, two doors), KR T1 metrics JSON | KR | 5 | W4 |
| F13 | Face verification ROC on D2 with the chosen threshold | HNHL week-03 metrics | HNHL | 5 | W4 |
| F14 | Re-ID CMC / ROC, both OSNet weights | HNHL week-04 metrics | HNHL | 5 | W5 |
| F15 | Dead-reckoning path vs ground truth, with and without ArUco | KR/DQK T2 localization (W4) | KR | 4 | W5 |
| F16 | State machine diagram | `app/state_machine.py` | KR | 6 | W5 |
| F17 | Pursuit: distance to target and bbox-centre error vs time; hold events | DQK week-06 T2 logs | DQK | 6 | W6 |
| F18 | Optimization: FP32 vs FP16 (TensorRT if done) latency and accuracy | HNHL week-06 metrics | HNHL | 5 | W6 |
| F19 | Test growth and section 4.3 status | pytest logs per week (`week-NN/pytest.log`), weekly reports | KR | 7 | W6 |
| F20 | Edge deployment: ONNX -> TensorRT 7.1 FP16 on the Nano, per model (GPU ms, engine MB, build time) and FP16-vs-FP32 parity (cosine, box IoU); TensorRT 7.1 limits and workarounds | `docs/Edge Deployment.md`, `week-02/edge_deploy/` (DQK 2026-10-16; SCRFD fixed by rewriting its Resize nodes, cosine 1.00000 against ONNX Runtime; our own D1/D2 accuracy still to do) | DQK | 5 | W6 |
| F21 | On-robot live bench: capture-to-result latency (mean, p95), FPS, RAM, GPU %, power, temperature for detector only and the pursuit model mix (with a person in view and with the door pipeline once measured) | `jetson/edge_bench.py` output and `tegrastats` logs (DQK 2026-10-16, nobody in view: Stage B 37.9 / 51.1 ms, 2.1 GB, 36 % GPU, 4.6 W; with the door pipeline in the same loop 63.0 / 101.2 ms; in its own thread 45.0 / 72.1 ms, 60 % GPU, 5.8 W, 10-minute soak stable, battery 12.14 -> 11.93 V) | DQK | 5 | W6 |

## 4. What has run (chapter 7 table)

**R** = real on 2026-10-16, with evidence. **E** = expected by 2026-11-23 (planned week). "-" = not applicable. The final report table is filled from evidence only; an E that did not happen is reported as not done.

| Component | Definition | Model | Architecture | How to use | Real-robot run | Optimization | Practical deployment |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| Video + control link | R robot video to laptop, (v, w) back, clock offset | - (Cristian min-RTT) | R ZMQ multipart JPEG q60, latest-frame slot; UDP 30 Hz; ports 5555-5557 | R `sentry-camera`/`sentry-control` services, `tools.log_latency`, `tools.send_cmd` | R 20 fps, p95 53 ms (target < 50), 0 % loss | R JPEG q60, drain to latest; E re-measure p95 (risk 16) | R systemd units, reboot-tested |
| Safety | R moves only while armed and R1 held; stops on link loss | - | R `estop.py` on the robot host cuts the motor driver over I2C; heartbeat to `robot_udp.py` | R hold Start 1.5 s, hold R1 | R wheels-off and floor; watchdog 305-315 ms | - | R `sentry-estop` service |
| Fisheye calibration | R undistort the 160 deg lens | R Kannala-Brandt (`cv2.fisheye`) | R 52 of 58 views -> `calib/camera.json` | R `python -m tools.calibrate_fisheye` | R RMS 0.83 px | R outlier views dropped | R committed calibration file |
| Motion model + localization | R command -> m/s, rad/s; E pose from dead reckoning + ArUco | R affine fits with a dead-zone offset: steady speed 0.491 (v - 0.124) m/s, turn rate 7.20 (w - 0.130) rad/s, and a per-wheel law (k 1.64, offset 0.038, track 0.137); E the speed-dependent model in the drive loop (W3) | R `sentry/nav/wheel_model.py`, `motion_estimator.py` (marker range and bearing -> scale, drift, start-up lag); E `nav/localization.py` on `WheelModel` (issue #41) | R `tools.calibrate_motion`, `speed_trial`, `motion_trial`, `turn_trial`, `speedfit` | R classroom glossy tile 2026-10-15 at 11.8-12.2 V; heading error is random per run (about +/-10 deg/m plus a left bias) so no fixed trim fixes it; E 3 m path error (W4) | R per-wheel dead zone; battery sag lowers speed (10.97 V gave a third) | R `calib/motion.json` blocks (its source file `week-02/classroom_1015/README.md` is on the unmerged `w02-log` branch); E online heading correction from the marker |
| Obstacle distance | E distance from the bbox foot point | E YOLOv8n furniture classes; R camera pose by strips (H 0.101 m) and live marker tilt (`LiveTilt`, 2026-10-14: 0.5-6 % ground-distance error standing, 3-20 % moving) | E `perception/obstacle.py`, pitched ground-plane model, reflection handling for the glossy floor (risk 23), repulsion | E replay of D1; R 24-row obstacle pack for HNHL (`assets/d1/obstacles_2026-10-15/`) | E error on D1 (W2-W3), exploration T2 0 collisions (W3) | R YOLOv8n 110 FPS (RTX 4050, FP32); R on the Jetson: TensorRT FP16 14.8 ms at 320 (F20) | E laptop, live during exploration; on-robot obstacle layer is extra Stage A (gate G2) |
| Map + vantage | E occupancy grid, sweet spot | - (geometry, scoring) | E `nav/gridmap.py`, `nav/vantage.py` | E from a D1 sweep | E map vs tape; sweet spot 5/5 (W4) | - | E map saved for the search |
| Entrance (XFeat, DINOv2; ORB baseline) | E find the door from `I_ref` | E XFeat + RANSAC (robot reference, vendored) and DINOv2 (phone reference), per-room calibration, one door per room | E `perception/entrance.py` | E `I_ref` photo + replay per door | R D1 bake-off on 2 doors, 2026-10-12: XFeat AUC 0.99-1.00, DINOv2-B 1.00 (phone reference), ORB 0.91 (risk 14); E a second session on the classroom door, the primary demo door (other doors are optional, reported without a threshold) | E undistort, stable features | E Phase 1 HIL (W4) |
| ESP32-CAM stream | R fixed entrance camera to laptop | - | R GC2145 raw Bayer changed-tile UDP, `sentry.espcam.TileReceiver`; OV2640 MJPEG untested | R flash `esp32/tile_stream`, `tools.esp_tile_rx` | R 14.4 fps average (9-10 worst) | R camera on core 0, changed tiles only | E placed at the door, handshake T2 (W3) |
| Deployment + audio | E stop, prompt, verify, standby | - | E `play` packets -> `aplay`; offline TTS WAVs | E Phase 1 run | E 5 runs (W3), Phase 1 5 runs (W4) | - | E USB speaker on the robot |
| Face verification | E whitelist vs intruder | R `buffalo_s` runs on CUDA (about 7 ms); E threshold from ROC | E `perception/face.py`, max cosine over all enrolled embeddings | E `tools/enroll_whitelist.py` | E TAR/FAR on D2 (W3); live at the door (W5) | R onnxruntime CUDA | E laptop, Phase 2 live |
| Re-ID + queue | E appearance vector, FIFO | R OSNet weights fetched, 11-13 ms; E choice by rank-1 (W4) | E `perception/reid.py`, `app/target_queue.py` | E D2 replay -> queue | E rank-1 on D2 (W4) | E smaller model if rank-1 is equal | E Phase 2 live (W5) |
| State machine | E events in, commands out | - | E `app/state_machine.py`, phases 1-3 | E scripted event replays (T0) | E drives Phase 1 (W4) and pursuit (W6) | - | E laptop |
| Tracking, pursuit, hold | E follow at 1.2 m, hold when stopped | E YOLOv8 + ByteTrack + OSNet filter; PD | E `perception/tracker.py`, `nav/controllers.py`, hold detector | E D3 replay, T2 protocols | E pursuit and hold T2 (W5-W6) | E GPU budget (W5), FP16 (W6) | E laptop + robot at the 0.3 cap |
| On-robot inference (extra, DQK) | R the Jetson runs the time-critical models itself; the laptop becomes a companion | R YOLOv8n, YOLOv8n-pose, OSNet x0.25 and AIN, XFeat backbone, SCRFD, MobileFaceNet, DINOv2-S/B converted; DINOv2 stays on the laptop (0.4-2.8 FPS) | R ONNX (opset 11) to TensorRT 7.1 engines built on the robot; `jetson/trt_runtime.py`, `yolo_post.py`, `face_post.py`; door pipeline in its own thread | R `tools.export_edge_onnx`, `trtexec`, `jetson/edge_bench.py` | R 20 FPS on live frames, capture-to-result p95 51 ms (Stage B), 72 ms with the door thread, nobody in view, wheels still, on battery | R FP16 (detector 20.7 to 14.8 ms); Resize and DINOv2 attention rewritten for TensorRT 7.1; pre/post-processing 6.4 to 3.4 ms; parity cosine >= 0.9999 | E Stage A in the control loop (gate G2, W5); Stage B after the mid-term (G3) |
| Evasion, search, full loop | planned W8-W10 | - | - | - | - | - | written as expected results (chapter 8) |

**On-device deployment is now a required part of chapter 5 (instructor's item 5), not optional.** Evidence exists from 2026-10-16: eight models converted to TensorRT 7.1 FP16 on the Jetson and matched against ONNX Runtime; the pursuit model mix on live frames (about 51 ms capture-to-result p95 with nobody in view, 72 ms with the door pipeline in its own thread), RAM about 2.1 GB, power and a 10-minute battery run; a silent TensorRT operator bug found and fixed (SCRFD `Resize`). The chapter reports it as measured and says what is still open (person in view, ESP32 frames, our own D1/D2 accuracy, driving under load; gate G1). What runs in the control loop on the robot (stages A to C of the extra task, `Implementation Plan.md` section 5) is reported only for the stages whose gates have passed by Nov 15; the rest is written as expected.

## 5. Demo video (2-4 min, optional)

The video is optional: if pursuit slips, cut the W6 robot shots and keep the Phase 1 and calibration shots (or use the replay/`sim_robot` fallback, captioned as such).

Who: DQK films the robot (phone on a tripod) and edits; HNHL screen-records the laptop overlays (OBS); KR films the door and the ESP32 view. When: each shot as soon as its feature works (W5-W6 sessions); pick-up session Sun Nov 15; cut by Wed Nov 18; spare re-shoot Sat Nov 21. Upload to the team Drive; the link goes in the report and appendix, never in git.

| # | Shot | s | Proves |
| :-- | :-- | :-: | :-- |
| 1 | Title + F1 overview | 10 | what the system is |
| 2 | Boot: services up, `tools.jetbot_status` battery, arm, R1 drive and release stop | 20 | deployment, safety |
| 3 | Live stream with FPS/latency overlay, raw vs undistorted side by side | 20 | network, calibration |
| 4 | Exploration with obstacle boxes and distances, map building (split screen) | 30 | obstacle distance, map |
| 5 | Entrance found -> sweet spot -> audio prompt -> camera placed -> verified -> standby | 40 | Phase 1 end to end |
| 6 | ESP32 view: team member walks in -> whitelisted; consenting volunteer -> intruder -> queued | 30 | Phase 2 |
| 7 | Pursuit at 1.2 m, then hold and re-centre when the target stops | 30 | Phase 3 (first part) |
| 8 | All models together: FPS and `nvidia-smi` on the laptop; then the same detector + pose + re-ID mix running on the Jetson itself (`edge_bench.py` overlay: FPS, GPU %, watts) | 15 | GPU budget, optimization, on-device deployment |
| 9 | Next steps: evasion, search (text over F1) | 10 | expected results |

Rules: check the battery before every take (>= 11.1 V; stop below 10.5 V); the operator holding R1 is shown or stated; replay or `sim_robot` shots are captioned as such (fallback for shots 4-7); only consenting people on camera, blur anyone else.

## 6. Code submission package

1. PR freeze Fri Nov 20; all three review `main`; tag `midterm` on Sat Nov 21.
2. Clean checkout test: fresh clone of the tag into an empty folder, environment per `docs/Setup.md`, `python tools/check_env.py`, `pytest -m "not gpu and not hil"` (and `-m "not hil"` on a CUDA laptop). Save the logs as `reports/<handle>/week-07/clean_checkout_pytest.log`.
3. Contents check with `git ls-files`: **never** `data/`, recordings, face photos, `.env`, `esp32/*/secrets.h`, the host-key pin, model weights. Included: `calib/*.json`, evidence reports, README run steps.
4. Appendix: module list with owners and tests, how to run, and the **public repo link** at the tag (the repo is public: also check the history for secrets with `git log -p -S` on the Wi-Fi password and keys, and keep `data/` and faces out for good). The appendix counts toward the 10-15 pages.
5. Fallback if the repo cannot be reached: `git archive --format=zip midterm`.

## 7. Countdown

| When | Milestone |
| :-- | :-- |
| T-3 w, Mon Nov 2 | Outline, page budget and owners agreed (this file); 3+ papers per member; figures assigned; shared document created |
| T-2 w, Mon Nov 9 | Chapters 1-4 drafted from Week 1-4 evidence; F1-F15 and F20-F21 made; Phase 1 and Phase 2 video shots recorded |
| T-8 d, Sun Nov 15 | Experiments closed, **figures frozen**, all video shots recorded |
| T-5 d, Wed Nov 18 | **Internal draft:** full merged report (10-15 pages) and video cut |
| T-4..3 d, Thu-Fri Nov 19-20 | Internal review: each member reads the whole report and checks every number against its file; PR freeze Fri |
| T-2 d, Sat Nov 21 | Clean checkout test, tag `midterm`, spare re-shoot slot |
| T-1 d, Sun Nov 22 | PDF final, video uploaded, links checked |
| **T-0, Mon Nov 23** | **Submit** |
