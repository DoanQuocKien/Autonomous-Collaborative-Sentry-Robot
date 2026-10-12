# Implementation Plan

Companion to `Project Specification.md` (the spec decides *what*; this file decides *who, how, and how we prove it works*).
Week 1 starts **Mon 2026-10-05**. The Mid-Term Technical Report is due **Mon 2026-11-23** (start of Week 8; date given by DQK on 2026-10-12, the earlier assumption was Sun 2026-11-01) and **must include the code** (see the submission package in Week 4). The Week 4 report work below is kept as the internal draft deadline.

## 1. Team & Roles

| Handle | CUDA | Hardware | Primary ownership |
| :-- | :-: | :-: | :-- |
| **DoanQuocKien** (DQK) | Yes | Holds the JetBot kit (speaker later) | Jetson side, motor control, calibration, controllers on the robot, hardware-in-the-loop (HIL) testing, integration host |
| **HuynhNguyenHoaiLoc** (HNHL) | Yes | – | Laptop perception: YOLOv8, ByteTrack, InsightFace, OSNet, YOLOv8-pose, GPU profiling |
| **kouun-rokku** (KR) | No | Holds the ESP32-CAM + MB base | CPU-side logic: record/replay tooling, ORB entrance matching, localization (ArUco + dead reckoning), state machine, queue/handoff logic, simulation, audio assets, test infrastructure, report editing |

Principles behind the split:
- KR has no GPU, so KR owns everything that runs on CPU and the tooling that lets others work without the robot.
- Only DQK has the robot (and only KR has the ESP32 kit), so every task must be developable **offline on recorded data** first. HIL time on DQK's setup is for validation, not development.
- Each member carries roughly equal weekly load (about 3 work items per week).

## 2. Repository Layout (target)

```
sentry/                 # laptop package, Python 3.12 in sentry (see Setup.md)
  net/                  # zmq_rx.py, udp_tx.py, mjpeg_rx.py, clock_sync.py
  perception/           # obstacle.py, entrance.py, face.py, reid.py, tracker.py, pose.py
  nav/                  # localization.py, gridmap.py, vantage.py, coverage.py, controllers.py
  app/                  # state_machine.py, target_queue.py, audio.py, main.py
config.toml             # repo-root tunables (thresholds, gains, ports); stdlib tomllib
common/                 # Python 3.6-compatible, stdlib only; used by BOTH laptop and Jetson
  protocol.py           # ports, packet encode/decode with validation, SeqFilter, video header, clock echo
  mixing.py             # (v, w) -> wheel values: rescale-not-clip, dead zone (zero below `min_pwm`), setting checks
tools/                  # DONE: check_env.py, send_cmd.py, make_markers.py, record.py, replay.py, sim_robot.py,
                        # calibrate_fisheye.py (calib/camera.json, RMS 0.83 px), calibrate_motion.py (no runs yet),
                        # plus network/ESP32/D1/GPU helpers
                        # TODO: enroll_whitelist.py, label_events.py
jetson/                 # Python 3.6, Ubuntu 18.04; own requirements.txt (see docs/Setup.md)
  camera_pub.py         # CSI -> JPEG q60 -> ZeroMQ PUB; `--source synthetic` works without the robot (tested on the robot 2026-10-06)
  robot_udp.py          # UDP (v, omega) + audio commands -> motors / speaker, watchdog, e-stop interlock (motors tested; aplay untested)
  estop.py              # gamepad dead-man + e-stop, robot host (tested wheels-off 2026-10-06, first floor drive 2026-10-11)
  systemd/              # boot units for estop / camera / control (written 2026-10-11, not yet tested on the robot)
assets/print/           # ArUco markers (ids 0-5, 10 cm) and 9x6 checkerboard PDFs, from tools/make_markers.py
esp32/tile_stream/      # GC2145 boards: raw Bayer changed-tile UDP stream (the frozen interface, section 3)
esp32/sentry_cam/       # OV2640 boards only: stock HTTP MJPEG VGA sketch (not tested on a board)
assets/audio/           # pre-generated WAV prompts (committed, small)
calib/                  # calibration outputs (camera.json, motion.json); committed
tests/                  # pytest; markers below
data/                   # recordings, face photos (GITIGNORED; shared via team Drive)
reports/<handle>/       # weekly reports + test evidence (section 6)
```

Keep it flat. A module gets split only when it passes about 400 lines.

## 3. Interfaces (frozen by end of Week 1)

Freezing these lets the three members work in parallel against the same contracts. Any change needs a PR that all three approve.

| Link | Transport | Format |
| :-- | :-- | :-- |
| JetBot -> laptop video | ZeroMQ PUB/SUB, port 5555; bounded SUB queue, drain complete messages and overwrite one latest-frame slot | multipart `[header_json, jpeg_bytes]`; header `{"seq": int, "t_cap": float (Jetson monotonic s), "w": int, "h": int}` |
| Laptop -> JetBot control | UDP, port 5556, non-blocking | JSON `{"seq": int, "v": float, "w": float}` with v, w normalized to [-1, 1]; or `{"seq": int, "play": "<clip_name>"}` |
| Clock sync | UDP echo, port 5557 | laptop sends `t0`, Jetson replies `{t0, t_jetson}`; offset by Cristian's algorithm (min-RTT of 20 samples) |
| ESP32-CAM -> laptop | **UDP tiles, port 5600** (GC2145 module, no hardware JPEG): raw Bayer 640x480, changed 64x32 tiles only, laptop found by `HELO` broadcast; `sentry.espcam.TileReceiver.latest()` gives a BGR frame. **Frozen 2026-10-11 by DQK's decision: the UDP tile stream is the interface.** An OV2640 module was nevertheless ordered the same day (`docs/ESP32-CAM.md`; firmware ready in `esp32/sentry_cam`, not tested on a board); switching the interface to it needs a PR all three approve. HNHL approved PR #2, which carried this row; KR was asked in the comments on PR #2 and #6 and had not answered by 2026-10-11, so KR may still object (a change then needs a PR all three approve). With an OV2640 module the original HTTP MJPEG `http://<esp32-ip>:81/stream` (VGA, 15 FPS) is used instead | 640x480 at 14.4 FPS average (fixed camera); see `docs/ESP32-CAM.md` |

Laptop-internal contract:
- JetBot video adapters use `read(timeout) -> VideoFrame | None`, single consumer, with `frame_bgr`, original `jpeg`, `seq`, source `t_cap`, laptop `t_rx` and `t_decode` (see `sentry/net/frame.py`). Latest-frame receivers deliberately skip old frames; record/replay preserves source timestamps. `tools.replay.ReplayStream.read()` implements this offline contract; legacy tuple iteration remains supported. The ESP32 tile interface uses `latest()` as documented separately above.
- Do not use `ZMQ_CONFLATE` on the multipart video link: [libzmq documents that it retains only one part](https://libzmq.readthedocs.io/en/latest/zmq_setsockopt.html#zmq-conflate-keep-only-last-message). The wire format stays unchanged; review this correction with the team before the W1 interface freeze.
- Every perception module is a class with a `__call__(frame_bgr, t) -> dataclass` method and no global state.
- Every module can be fed from `replay.py` exactly as from a live stream.
- The state machine only consumes **events** (e.g. `ENTRANCE_FOUND`, `INTRUDER_QUEUED`, `TARGET_STATIONARY`, `STRIKE`, `TARGET_EXITED`, `TARGET_FOUND`, `SEARCH_EXHAUSTED`) and emits **commands**. It never touches sockets or models directly, so it is unit-testable on CPU.

**Motion convention** (details and reasons in `JetBot Notes.md`):
- `v, w` are normalized to [-1, 1]; positive `w` turns left. The Jetson mixes `left = v - K*w`, `right = v + K*w`.
- If either wheel value exceeds 1 in magnitude, **rescale both** by the larger one (never clip), so the turn ratio is kept.
- Jetson code must run on Python 3.6.

**Safety (non-negotiable):**
- The Jetson stops the motors if no control packet arrives for 300 ms.
- The kit gamepad is a **dead-man switch plus e-stop** (`jetson/estop.py`, runs on the robot host): the robot moves only while R1 is held and the e-stop is armed (hold Start 1.5 s); releasing R1 stops it, any other button or losing the pad is a hard stop, and every stop cuts the motor driver directly over I2C. `robot_udp.py` refuses to drive without the e-stop's heartbeat. Verified on the robot 2026-10-06 (wheels off the ground), including with `robot_udp.py` frozen. Details and limits in `docs/JetBot Notes.md`.
- Speed is capped during all HIL tests by `robot_udp.py --max-speed` on the robot (0.3 in `jetson/systemd/sentry-control.service`; the Jetson cannot read `config.toml`). Commands are mapped onto [`min_pwm`, cap] (dead-zone compensation, `common/mixing.py`), so small commands still move the wheels and the evasion arc keeps both wheels turning; at a 0.3 cap, though, evasion reaches only 0.3 of full speed. Raising the cap for the Week 6 evasion trials is a safety decision for the team, recorded in the weekly log of whoever runs them.

## 4. Testing Policy

### 4.1 Tiers

| Tier | Marker | Runs where | Content |
| :-- | :-- | :-- | :-- |
| T0 Unit | (none) | Any machine, CPU, no network, whole suite < 60 s | Pure logic: geometry, formulas, state transitions, queue, packet encode/decode, controllers against `sim_robot` |
| T1 Replay | `replay` (+ `gpu` if it needs models) | Machine with `data/` synced | Run a module on a recorded dataset, assert metric thresholds, write a metrics JSON |
| T2 HIL | `hil` | DQK's setup | Scripted protocol on the real robot, N trials, results table |

- KR's machine runs `pytest -m "not gpu and not hil"`. CUDA members run `pytest -m "not hil"`. DQK also runs `-m hil`.
- `gpu` tests skip themselves when `torch.cuda.is_available()` is false.
- Every non-trivial function has at least one T0 test that fails if its logic breaks. Every perception module has a T1 test with a numeric threshold.
- Metrics are written as JSON to `reports/<handle>/week-NN/` so results are comparable across weeks.

### 4.2 Datasets (recorded with `tools/record.py`, stored in `data/`, never committed)

| ID | When | Recorded by | Content |
| :-- | :-- | :-- | :-- |
| D1 | End of W1 (door data continues in W2) | DQK (all present) | Room sweeps with the JetBot; **doorway views of 3+ different doors (2026-10-11: the method matches a user-supplied `I_ref`, so it must work for any door; recorded: cafe glass door, classroom door, one more), each with its own `I_ref` photo (colour, front-on, about 2 m), 10+ positions at 1-4 m and about -45 to +45 deg, plus negatives (no door visible, and other doors as cross-door negatives); labels in `assets/d1/doorway_labels_template.csv` format**; 20 obstacles at tape-measured distances 0.3-2.0 m in the room that is mapped (ground truth in `assets/d1/obstacles_template.csv` format); 30+ checkerboard images (done 2026-10-10: 58); ESP32 view of each door (label the camera: GC2145 tile stream or OV2640) |
| D2 | End of W3 | DQK + HNHL | ESP32 entries: each team member x 10 entries; 3+ consenting non-enrolled volunteers x 5 entries; logged walk direction (L/C/R) per entry for sector tests |
| D3 | End of W5 | DQK | JetBot following one or two people: walking, stopping, occlusions, crossing paths |
| D4 | End of W6 | DQK + KR labels | 20+ padded "lunges" (pillow on a stick, never a real strike) + 10 min of normal walking; onset timestamps labelled with `label_events.py` |

Privacy: face photos and recordings of volunteers stay in `data/` and the team Drive, are used only with consent, and are deleted after grading.

### 4.3 Acceptance criteria per feature

| Feature | Metric | Pass threshold | Tier |
| :-- | :-- | :-- | :-- |
| Video uplink | Capture-to-laptop latency (clock-synced), FPS | p95 < 50 ms, >= 20 FPS at 640x480 | T2 |
| Control link | Packet loss; watchdog stop | < 1 % at 30 Hz; motors stop <= 350 ms after link loss | T2 |
| Fisheye calibration | RMS reprojection error | < 1.0 px | T1 |
| Obstacle distance | Relative error vs tape on D1 | median <= 10 %, p90 <= 20 % over 0.3-2.0 m | T1 |
| Obstacle repulsion | Collisions in exploration runs | 0 collisions in 5 x 3-min runs | T2 |
| ORB entrance | Frame-level TPR / FPR on D1, pooled and **per door**; threshold tuned on one door and tested on the others (hold-out) | TPR >= 90 %, FPR <= 5 % pooled; report the worst door | T1 |
| Motion calibration + dead reckoning | Position error after 3 m path | <= 15 cm with ArUco correction, <= 40 cm without | T2 |
| Sweet-spot selection | Chosen spot satisfies the 3 spec conditions | 5/5 runs | T2 |
| ESP32 handshake | I_ref detection when camera faces door / is turned away | 10/10 correct accepts, 10/10 correct rejects | T2 |
| Face verification | TAR @ FAR on D2 | TAR >= 95 % at FAR <= 1 %; report ROC and justify 0.45 or a replacement | T1 |
| OSNet re-ID | Rank-1 on D2/D3 gallery (>= 5 people) | >= 85 %; threshold picked from ROC | T1 |
| Sector logging (optional search prior) | L/C/R accuracy on D2 | >= 90 % | T1 |
| Tracking | ID switches on D3 | <= 1 per minute (2-person scenes) | T1 |
| Pursuit PD | Steady-state distance; centering | 1.2 +/- 0.2 m; bbox centre within +/- 10 % of frame width, 80 % of the time | T2 |
| Hold detector | Target speed in the world frame while the robot yaws | robot rotation alone never triggers HOLD (sim); HOLD exits when target speed > exit threshold | T0 |
| Standoff hold | Trigger delay; re-centering | stops 2.0-3.0 s after the target stops; bbox centre within +/- 10 % of frame width within 1.5 s; no orbiting | T2 |
| Strike detection | Recall; false triggers; latency (frame to command) | recall >= 90 % on D4; <= 1 false trigger / 5 min of walking; <= 150 ms | T1 + T2 |
| Room map | Obstacle cells vs tape-measured positions on D1 | >= 80 % of the 20 obstacles within 20 cm | T1 |
| Coverage planner | 3 synthetic rooms in the recorded-map format | coverage >= 90 % of known-free cells, plan time < 2 s, tour no longer than a lawnmower baseline | T0 |
| Search & re-acquire | T2 present, T1 exits | T2 found during the planned path in >= 4/5 trials; record time to find | T2 |
| Search exhausted | T2 absent (removed from the room) | path completes, T2 dropped from the queue, robot reaches the next target or standby; 3/3 trials, 0 collisions | T2 |
| Full loop | Two consecutive intruders, start to standby | >= 4/5 runs without manual help | T2 |
| GPU budget | All models running together | peak VRAM <= 5.5 GB; pipeline >= 15 FPS | T1 (gpu) |

## 5. Weekly Plan

Each week ends with a **Sunday integration session** hosted by DQK (in person or screen-share): merge PRs, run T0/T1 on main, run that week's T2 protocols, record any dataset due.

### Week 1 (Oct 5-11): Networking & Telemetry

- **DQK**
  - First, run the "Verify on the robot" checks in `JetBot Notes.md` (jetbot version, motor driver address, Python version, camera modes) and record the outputs.
  - Bring up the JetBot (flash image, Wi-Fi on 5 GHz) and configure the Windows dual-band hotspot (ESP32 on 2.4 GHz).
  - `jetson/camera_pub.py`: GStreamer `nvarguscamerasrc` -> JPEG q60 -> ZMQ with the header from section 3.
  - `jetson/robot_udp.py`: (v, w) -> left/right motor speeds, 300 ms watchdog, gamepad e-stop, clock-sync echo.
  - Tests: T0 for packet decode and v/w-to-wheel mixing; T2 latency, FPS, packet loss and watchdog.
- **HNHL**
  - `sentry/net/zmq_rx.py`: latest-frame receiver thread with JPEG decode.
  - `udp_tx.py`: rate-limited 30 Hz sender.
  - `clock_sync.py` and a latency logger that writes CSVs. **Use `time.perf_counter()` for Windows-side timestamps: `time.monotonic()` ticks only every 15.6 ms there, which corrupts RTT and offset estimates (measured 2026-10-04).**
  - GPU baseline: YOLOv8n/s FPS and VRAM at 640 on the RTX 4050; confirm torch, insightface and onnxruntime-gpu run in `sentry` (Python 3.12, see Setup.md), and record versions. HNHL's RTX 5060 measurements must be labelled separately; they do not substitute for the RTX 4050 baseline.
  - Tests: T0 for clock-sync math with synthetic delays.
- **KR**
  - `tools/record.py` + `tools/replay.py`: record both streams with timestamps; replay through the same interface as the live receivers.
  - `tools/sim_robot.py`: UDP sink that integrates (v, w) with unicycle kinematics and logs pose.
  - `esp32/sentry_cam` sketch (based on CameraWebServer, VGA, 15 FPS, static IP). KR holds the ESP32 kit, so KR flashes and tests it directly, and brings it to the Sunday session (needed for the ESP32 door view in D1 and the Week 3 handshake). **Update 2026-10-09:** DQK's modules turned out to be GC2145 (no JPEG); the 640x480 stream for that module is `esp32/tile_stream` + `sentry/espcam.py` (see `docs/ESP32-CAM.md`). KR: check which sensor your board has (`Camera PID=` in the boot log, or run `tile_stream` and read `esp_tile_rx`); an OV2640 board uses the stock sketch.
  - pytest skeleton: `conftest.py`, markers, `config.toml` loader.
  - Tests: T0 record-then-replay round trip gives identical frames and timestamps.
- **Session:** freeze the section 3 interfaces; record **D1**.

### Week 2 (Oct 12-18): Pre-Scanning & Setup

- **DQK**
  - `tools/calibrate_fisheye.py`: `cv2.fisheye` calibration on D1 checkerboards, writing `calib/camera.json`; measure `H_cam`.
  - `tools/calibrate_motion.py`: command fixed (v, w) for set durations, tape-measure the results, fit gains to `calib/motion.json`.
  - Tests: T1 reprojection error; T2 motion repeatability (5 runs each of straight 1 m and 90° turn).
- **HNHL**
  - `perception/obstacle.py`: YOLOv8 on undistorted frames, COCO furniture classes (chair, couch, bed, dining table, potted plant, tv, refrigerator, suitcase), bottom-centre ground distance `d = f*H/(y_max - c_y)` (valid for a level optical axis; with the optional 15° down-tilt wedge use the pitched ground-plane model instead, and skip boxes cut off by the bottom image border, whose `y_max` is not the ground contact), repulsive angular term.
  - `nav/gridmap.py`: occupancy grid (robot pose + obstacle ground points -> occupied, driven/seen floor -> free, rest unknown); saved at the end of Phase 1 for the Week 7 search.
  - `nav/vantage.py`: score candidate stops on the grid for line of sight, 1.5-3.0 m from the door, and nearness to a boundary.
  - Tests: T0 for the distance formula, repulsion sign and grid updates on synthetic data; T1 distance error and map-vs-tape error on D1.
- **KR**
  - `perception/entrance.py`: ORB (2000 features) + Hamming BF matching + Lowe ratio + RANSAC homography; match when inliers > threshold (tuned on D1); entrance bearing from the homography centroid through the camera model.
  - `nav/localization.py`: dead reckoning from `motion.json`, corrected by ArUco pose (`cv2.aruco`, 10 cm markers).
  - Tests: T0 for pose integration (closed square path returns to the origin in sim) and ArUco pose on synthetic renders; T1 entrance TPR/FPR on D1.
- **Session:** T2 exploration with obstacle repulsion, connected end to end.

### Week 3 (Oct 19-25): HCI Deployment & Biometrics

- **DQK**
  - USB speaker playback on the Jetson (`aplay` on `play` packets).
  - Deployment behaviour on the robot: stop at the sweet spot, face the room centre, prompt, wait for validation, reverse to standby.
  - Tests: T2 deployment sequence, 5 runs.
- **HNHL**
  - `perception/face.py`: InsightFace detection + 512-d embedding. Check the insightface 2.0 API first; the spec names MobileFaceNet, so prefer the `buffalo_s` pack.
  - `tools/enroll_whitelist.py`: 3-5 photos per person, stored as **all** normalized embeddings (the spec uses max similarity, so no averaging).
  - Verification with a configurable threshold.
  - Tests: T0 for cosine and max-similarity logic; T1 ROC on D2, recording the chosen threshold and evidence.
- **KR**
  - `sentry/net/mjpeg_rx.py`: ESP32 stream with auto-reconnect.
  - ESP32 handshake check (reuses `entrance.py` on the ESP32 frames).
  - Generate audio prompts offline (Windows SAPI via `pyttsx3`, or another offline TTS) into `assets/audio/`.
  - `app/state_machine.py` skeleton with all phase 1-3 states, transitions and timeouts.
  - Tests: T0 scripted event sequences for every transition, including invalid events, which are ignored and logged.
- **Session:** record **D2**; T2 ESP32 handshake accept/reject.

### Week 4 (Oct 26-Nov 1): Re-ID Handoff & Mid-Term Report

- **DQK**
  - Phase 1 end-to-end HIL: explore -> find entrance -> sweet spot -> prompt -> camera placed -> verified -> standby.
  - Tests: T2, 5 runs.
  - Report: architecture, networking, robot platform, calibration and safety sections (about 5 pages).
- **HNHL**
  - `perception/reid.py`: person crop from YOLO on ESP32 frames -> OSNet via torchreid with **re-ID-trained weights from `python -m tools.fetch_models`** (`osnet_ain_x1_0` domain-generalised, and `osnet_x0_25` Market1501); compare both on D2/D3 and keep the better one. Not `pretrained=True`: that is ImageNet-only.
  - Tests: T1 rank-1 and ROC on D2.
  - Report: perception and biometrics sections with ROC figures (about 5 pages).
- **KR**
  - `app/target_queue.py`: FIFO of intruder records (id, face embedding, appearance vector, sector, snapshot path, timestamps).
  - Sector logging: bounding-box horizontal drift over 2 s -> L/C/R (optional prior for the Week 7 search).
  - Phase 2 replay pipeline on D2, connected end to end.
  - Tests: T0 for the queue and sector classification; T1 sector accuracy on D2.
  - Report: localization, entrance matching, state machine and test methodology sections, plus editing and merging the full 15-20 pages.
- **Milestone:** Mid-Term Report draft complete (all sections, figures, merged document) by Sun 2026-11-01 as the internal deadline; **submission Mon 2026-11-23, with the code.**
- **Submission package (code included):** tag the repo (`midterm`) on `main` after a review by all three; `pytest -m "not gpu and not hil"` passes from a clean checkout; a README section with the run steps (`docs/Setup.md`); `calib/*.json` and the evidence reports included; **never** `data/`, `.env`, `esp32/*/secrets.h`, faces or the host-key pin; list the code in the report appendix (modules, owners, tests) and link the tag.

### Week 5 (Nov 2-8): Pursuit & Obstacle Handling

- **DQK**
  - `nav/controllers.py` PD pursuit (heading from bbox centre, distance from the foot-point ground distance, target 1.2 m) and obstacle override when `d_obs < 0.5 m`.
  - Tune gains from logged step responses.
  - Tests: T2 standoff and centering metrics; record **D3**.
- **HNHL**
  - `perception/tracker.py`: YOLOv8 + ByteTrack (ultralytics tracker) on the JetBot stream; target lock filtered by the OSNet vector, with re-lock after occlusion.
  - GPU profiling of all models together.
  - Tests: T1 ID switches on D3; T1 (gpu) VRAM and FPS budget.
- **KR**
  - Hold detector: target ground speed in the world frame (robot pose and yaw compensated, so the robot's own rotation is not mistaken for target motion) < 0.1 m/s for > 2.0 s -> HOLD; exit when > 0.2 m/s (hysteresis).
  - HOLD behaviour: zero translation, yaw-only PD that keeps the bbox centered (reuses the PD yaw term from DQK's controller). No orbiting: the target would sit 90 degrees off-axis, outside the camera's field of view.
  - Closed-loop tests of PD and hold against `sim_robot` with a scripted target.
  - Tests: T0 for detector timing, hysteresis, and "robot yawing alone never triggers hold".
- **Session:** T2 pursuit + hold.

### Week 6 (Nov 9-15): Threat Evasion

- **DQK**
  - Evasion override in the control path with the highest priority: v = -1.0, w = +/-0.8 for 400 ms, yawing away from the nearer obstacle side, then a cooldown.
  - Measure end-to-end reaction time with a high-FPS phone camera.
  - Tests: T2 padded-lunge trials; record **D4**.
- **HNHL**
  - `perception/pose.py`: YOLOv8-pose and a lunge detector (`dA/A > 0.40` within 100 ms using timestamps, not frame counts; or rapid ankle rise).
  - Tune on D4.
  - Tests: T0 for the detector on synthetic bbox series; T1 recall and latency on D4.
- **KR**
  - `tools/label_events.py`: keypress labeller for onset timestamps.
  - False-trigger harness (false triggers per minute on normal walking).
  - EVADE state + cooldown in the state machine.
  - Tests: T0 for the state machine preempting PURSUE/HOLD with EVADE; T1 false-trigger rate.
- **Session:** T2 strike evasion.

### Week 7 (Nov 16-22): Next-Target Integration

- **DQK**
  - Follow a planned path on the robot (waypoint following with the obstacle override and ArUco pose corrections) and the slow in-place 360° scan at each viewpoint.
  - Measure the effective detection radius `r_det` (distance at which OSNet still matches reliably; 3 people) and write it to `config.toml`.
  - Full-loop HIL with two intruders.
  - Tests: T2 full loop, 5 runs.
- **HNHL**
  - Exit-event detection on the ESP32 (re-ID matches T1 at the door and motion is toward the door).
  - Search-time re-ID matching on the JetBot stream while moving and scanning, with a lock threshold.
  - Tests: T1 exit detection on recorded exits; T1 re-acquisition precision.
- **KR**
  - `nav/coverage.py`: viewpoints chosen greedily on the saved map until the coverage target is met within `r_det` and line of sight; tour ordered by nearest neighbour + 2-opt; legs connected by A* on an obstacle-inflated grid; optional departure-sector prior.
  - Handoff orchestration in the state machine: TARGET_EXITED -> PLAN -> FOLLOW/SCAN -> TARGET_FOUND -> PURSUE, or SEARCH_EXHAUSTED -> drop from queue -> next target or STANDBY.
  - Tests: T0 for the planner on 3 synthetic rooms (coverage, plan time, tour length vs a lawnmower baseline) and for the two-intruder event script, including the not-found drop.
- **Session:** two-intruder rehearsal.

### Week 8 (Nov 23-29): Validation & Defense

- **DQK**
  - Stress tests: low battery, Wi-Fi drop (watchdog), dim and bright lighting, cluttered room.
  - Record demo footage.
  - Presentation: system and robot section.
- **HNHL**
  - Perception stress tests (backlight, partial faces, hats and masks, similar clothing).
  - Final metrics tables against section 4.3.
  - Presentation: perception section.
- **KR**
  - Edge-case state machine tests (empty queue, lost ESP32 stream, T2 never found leading to a timeout and return to standby, intruder leaving during evasion).
  - README, final test report, presentation assembly.
- **Final check:** every section 4.3 row has an evidence link in someone's report.

## 6. Workflow & Reports

**Git:**
- Branch `<handle>/wNN-<topic>` (e.g. `kouun-rokku/w02-orb-entrance`), then a PR to `main` with one approving review and T0 passing.
- Review rotation: DQK's PRs -> KR, KR's -> HNHL, HNHL's -> DQK (a CUDA reviewer for GPU code).
- No direct pushes to `main`.

**Definition of done for a work item:**
1. Code is merged via a reviewed PR.
2. Tests at the tiers listed for it exist and pass.
3. Evidence is in the owner's weekly report.

**Report directories:**
```
reports/<handle>/week-NN.md     # weekly progress log (template: reports/TEMPLATE.md)
reports/<handle>/week-NN/       # test evidence: pytest logs, metrics JSON/CSV, plots, T2 trial tables
```
- Weekly logs are due Sunday night, before the integration session.
- Large media (videos) go to the team Drive and are linked from the log, never committed.

## 7. Assumptions & Open Risks

| # | Item | Plan |
| :-- | :-- | :-- |
| 1 | Spec's strike window of "100 ms" is only 1.5 frames at 15 FPS | Measure the actual JetBot pipeline FPS in W1; use timestamp-based windows; if FPS < 20, widen the window to 2 frames and re-tune the 0.40 threshold on D4 |
| 2 | The spec does not say how "T1 exits" is detected | ESP32 re-ID + direction of motion toward the door (W7, HNHL) |
| 3 | COCO classes miss walls, boxes and bags | Accept for W2; if exploration collisions occur, add a bottom-of-frame floor-edge check or fine-tune on D1 frames |
| 4 | The L/C/R departure sector is in ESP32 camera coordinates, not world, and is now only an optional prior | Record the ESP32 placement pose in phase 1; KR maps it to a world bearing only if the planner uses the prior (W7) |
| 5 | Model package upgrades can change Python, CUDA or API compatibility | **Resolved for the recorded W1 environments:** Python 3.12 verified by HNHL; DQK's InsightFace CUDA detector + embedder about 7 ms, OSNet 11-13 ms and 3-model pipeline 37 FPS under 300 MB (`reports/DoanQuocKien/week-01/gpu_baseline_2026-10-06.txt`). Record versions and rerun checks after upgrades. |
| 11 | torchreid `pretrained=True` gives ImageNet-only weights, not re-ID weights, which would make the 85 % Rank-1 target unreachable | Use the re-ID weights from `tools.fetch_models`; osnet_ain_x1_0 (domain-generalised) vs osnet_x0_25 (Market1501, same-domain) is decided by Rank-1 on D2/D3 |
| 6 | All HIL depends on DQK's availability | Offline-first development; two scheduled sessions per week from W5 onward |
| 8 | The room map only knows floor the robot has seen: YOLO misses walls and unclassified objects | Plan only over known-free cells with inflated obstacles; report the coverage fraction achieved; make sure the Week 4 exploration covers the room |
| 9 | The effective detection radius `r_det` is unknown | Placeholder 3.0 m in `config.toml`; DQK measures it in W7 and the plan is recomputed from it |
| 10 | Dead-reckoning drift along a long search path (no encoders) | Re-localize whenever an ArUco marker is seen; measure path-following error in W7; shorten the path by lowering the coverage target if error is too large |
| 7 | Mid-term due date was assumed to be Nov 1 | **Resolved 2026-10-12 (DQK): due Mon 2026-11-23, includes the code.** The date now falls on the first day of Week 8, so keep Nov 1 as the internal draft date or the report will compete with the final integration |
| 12 | The ESP32-CAM modules (both the Shopee and the local one) carry a GC2145, which has no hardware JPEG: the plan's HTTP MJPEG VGA 15 FPS is impossible with the stock sketch (1.7-7.7 FPS) | **Worked around in software on 2026-10-09:** raw Bayer + changed-tile UDP stream, 14.4 FPS average, 9-10 FPS worst case; needs a fixed camera. Alternative: buy an OV2640 module (about 25 FPS VGA, stock sketch). **Decision 2026-10-11 (DQK): keep the tile stream as the interface.** An OV2640 was also ordered that day as an option (`docs/ESP32-CAM.md`); using it changes the frozen interface, so it needs a PR all three approve. Details: `docs/ESP32-CAM.md` |
| 13 | The second ESP32-CAM board loses its Wi-Fi uplink while the camera runs (cause unknown); the first board is fine | Use the first board for the stream; ask KR to test their board; if a board shows send failures only while the camera runs, swap it |
| 14 | ORB entrance matching on a frameless glass door is weak from the robot's low 160 deg fisheye view (cafe door, 2026-10-11: almost no inlier separation between door-in-view and no-door frames with default ORB; solid doors untested) | Test on the classroom door and at least one more; undistort with the fisheye calibration first; take `I_ref` from the robot's own camera as well as a phone; restrict to stable features (frame, handle, signs); fallback only with the team's approval: a marker on the door |
| 15 | **Open, needs a team decision (audit 2026-10-11).** The full-loop criterion says "without manual help" (section 4.3), but the robot moves only while an operator holds R1 (section 3, Safety) | Decide before Week 5: either keep the operator holding R1 during every trial (and reword the criterion to "without steering or intervention"), or define a supervised mode with its own safety case. Do not loosen the dead-man without that |
| 16 | **Open, needs a team decision (audit 2026-10-11).** The video target p95 < 50 ms is missed on the default 2.4 GHz hotspot (53-62 ms measured, `docs/JetBot Notes.md`), and the spec's simultaneous 2.4 + 5 GHz bands are not what the single-radio Windows hotspot provides | `docs/Hardware.md` section 2 has the router gate (ping p95 > 50 ms): decide whether it has triggered, or record the conditions under which the hotspot meets the target |
