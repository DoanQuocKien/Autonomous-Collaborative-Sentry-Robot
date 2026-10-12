# Mid-Term Report Plan

**Due Mon 2026-11-23** (first day of Week 8). Deliverables: a 10-15 page report, the code (tag `midterm` + appendix), and an **optional** 2-4 min demo video (link). Schedule: `Implementation Plan.md` section 5, Weeks 4-7. Editor: KR; each chapter owner checks their own numbers.

Rules:
- Every number cites its evidence file (`reports/<handle>/week-NN/...`, `calib/*.json`). No file, no number.
- What is not built or measured yet is written as **expected** (with its threshold from Implementation Plan section 4.3 and its week), never as a result.
- Spec section 6 still says 15-20 pages in Week 4; the team lead's 10-15 pages on 2026-11-23 replaces it.

## 1. Outline and page budget (13 pages + 1 page appendix = 14)

| # | Chapter | Content (required item) | Pages | Owner |
| :-- | :-- | :-- | :-: | :-- |
| 1 | Introduction | Problem, the three phases, scope, hardware (item 1: description) | 1 | KR |
| 2 | Related work | Researched papers and what each one is used for (item 3) | 1.5 | KR compiles, all contribute |
| 3 | System architecture | Laptop / Jetson / ESP32 split, network and interfaces, safety design | 2 | DQK |
| 4 | Robot platform and calibration | Fisheye, camera pose, motion model, dead reckoning + ArUco | 1.5 | DQK (+KR localization) |
| 5 | Perception | Obstacle distance, entrance (XFeat / DINOv2), face verification, re-ID, tracking; models, GPU budget, optimization | 3 | HNHL (+KR for entrance) |
| 6 | Behaviour and control | State machine, Phase 1 deployment, queue, pursuit and hold | 1.5 | KR (+DQK controllers) |
| 7 | Tests and results to date | T0/T1/T2 tiers, section 4.3 status table, the "what has run" table (section 4 below), real-robot runs | 1.5 | KR, rows by owners |
| 8 | Expected results and remaining plan | Targets for evasion, search, full loop; Weeks 8-13; risks (item 2: expectation) | 1 | DQK |
| A | Appendix | Code: modules, owners, tests, how to run, tag link; demo video link and shot list (items 3-4) | 1 | KR |

Item 5 (images and charts): at least one figure per page in chapters 3-7 (section 3).

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
| 10+ | ... | | | |

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

## 4. What has run (chapter 7 table)

**R** = real on 2026-10-12, with evidence. **E** = expected by 2026-11-23 (planned week). "-" = not applicable. The final report table is filled from evidence only; an E that did not happen is reported as not done.

| Component | Definition | Model | Architecture | How to use | Real-robot run | Optimization | Practical deployment |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| Video + control link | R robot video to laptop, (v, w) back, clock offset | - (Cristian min-RTT) | R ZMQ multipart JPEG q60, latest-frame slot; UDP 30 Hz; ports 5555-5557 | R `sentry-camera`/`sentry-control` services, `tools.log_latency`, `tools.send_cmd` | R 20 fps, p95 53 ms (target < 50), 0 % loss | R JPEG q60, drain to latest; E re-measure p95 (risk 16) | R systemd units, reboot-tested |
| Safety | R moves only while armed and R1 held; stops on link loss | - | R `estop.py` on the robot host cuts the motor driver over I2C; heartbeat to `robot_udp.py` | R hold Start 1.5 s, hold R1 | R wheels-off and floor; watchdog 305-315 ms | - | R `sentry-estop` service |
| Fisheye calibration | R undistort the 160 deg lens | R Kannala-Brandt (`cv2.fisheye`) | R 52 of 58 views -> `calib/camera.json` | R `python -m tools.calibrate_fisheye` | R RMS 0.83 px | R outlier views dropped | R committed calibration file |
| Motion model + localization | R command -> m/s, rad/s; E pose from dead reckoning + ArUco | R linear gains at v = 1.0; E speed-dependent fit + drift (W3) | E `nav/localization.py` | R `tools.calibrate_motion run/fit` | R 0.414 m/s, 6.48 rad/s, drift -0.19 rad/m (provisional); E 3 m path error (W4) | - | R first estimate on the robot; E final `calib/motion.json` |
| Obstacle distance | E distance from the bbox foot point | E YOLOv8n furniture classes; R camera pose H 0.101 m, pitch 2.6 deg (provisional) | E `perception/obstacle.py`, pitched ground-plane model, repulsion | E replay of D1 | E error on D1 (W2-W3), exploration T2 0 collisions | R YOLOv8n 110 FPS (RTX 4050, FP32) | E laptop, live during exploration |
| Map + vantage | E occupancy grid, sweet spot | - (geometry, scoring) | E `nav/gridmap.py`, `nav/vantage.py` | E from a D1 sweep | E map vs tape; sweet spot 5/5 (W4) | - | E map saved for the search |
| Entrance (XFeat, DINOv2; ORB baseline) | E find the door from `I_ref` | E XFeat + RANSAC (robot reference), DINOv2-B descriptor (phone reference) | E `perception/entrance.py` | E `I_ref` photo + replay per door | R D1 bake-off on 2 doors, 2026-10-12: XFeat AUC 0.99-1.00, DINOv2-B 1.00 (phone reference), ORB 0.91 (risk 14); E a third door and a second session | E undistort, stable features | E Phase 1 HIL (W4) |
| ESP32-CAM stream | R fixed entrance camera to laptop | - | R GC2145 raw Bayer changed-tile UDP, `sentry.espcam.TileReceiver`; OV2640 MJPEG untested | R flash `esp32/tile_stream`, `tools.esp_tile_rx` | R 14.4 fps average (9-10 worst) | R camera on core 0, changed tiles only | E placed at the door, handshake T2 (W3) |
| Deployment + audio | E stop, prompt, verify, standby | - | E `play` packets -> `aplay`; offline TTS WAVs | E Phase 1 run | E 5 runs (W3), Phase 1 5 runs (W4) | - | E USB speaker on the robot |
| Face verification | E whitelist vs intruder | R `buffalo_s` runs on CUDA (about 7 ms); E threshold from ROC | E `perception/face.py`, max cosine over all enrolled embeddings | E `tools/enroll_whitelist.py` | E TAR/FAR on D2 (W3); live at the door (W5) | R onnxruntime CUDA | E laptop, Phase 2 live |
| Re-ID + queue | E appearance vector, FIFO | R OSNet weights fetched, 11-13 ms; E choice by rank-1 (W4) | E `perception/reid.py`, `app/target_queue.py` | E D2 replay -> queue | E rank-1 on D2 (W4) | E smaller model if rank-1 is equal | E Phase 2 live (W5) |
| State machine | E events in, commands out | - | E `app/state_machine.py`, phases 1-3 | E scripted event replays (T0) | E drives Phase 1 (W4) and pursuit (W6) | - | E laptop |
| Tracking, pursuit, hold | E follow at 1.2 m, hold when stopped | E YOLOv8 + ByteTrack + OSNet filter; PD | E `perception/tracker.py`, `nav/controllers.py`, hold detector | E D3 replay, T2 protocols | E pursuit and hold T2 (W5-W6) | E GPU budget (W5), FP16 (W6) | E laptop + robot at the 0.3 cap |
| Evasion, search, full loop | planned W8-W10 | - | - | - | - | - | written as expected results (chapter 8) |

Optional, timebox 2 h, only if it installs without touching the robot's working setup: one detector running on the Jetson itself, as evidence for why the models run on the laptop. Skip it otherwise.

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
| 8 | All models together: FPS and `nvidia-smi` | 15 | GPU budget, optimization |
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
| T-2 w, Mon Nov 9 | Chapters 1-4 drafted from Week 1-4 evidence; F1-F15 made; Phase 1 and Phase 2 video shots recorded |
| T-8 d, Sun Nov 15 | Experiments closed, **figures frozen**, all video shots recorded |
| T-5 d, Wed Nov 18 | **Internal draft:** full merged report (10-15 pages) and video cut |
| T-4..3 d, Thu-Fri Nov 19-20 | Internal review: each member reads the whole report and checks every number against its file; PR freeze Fri |
| T-2 d, Sat Nov 21 | Clean checkout test, tag `midterm`, spare re-shoot slot |
| T-1 d, Sun Nov 22 | PDF final, video uploaded, links checked |
| **T-0, Mon Nov 23** | **Submit** |
