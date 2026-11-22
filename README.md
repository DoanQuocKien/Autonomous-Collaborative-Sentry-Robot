# Autonomous Collaborative Sentry Robot

CS532 (Computer Vision in Human-Computer Interaction, UIT - VNU-HCM), 13-week capstone, 2026-10-05 to 2027-01-03.
Team: DoanQuocKien (DQK, robot owner and integration), HuynhNguyenHoaiLoc (HNHL, perception), kouun-rokku (KR, state machine, tooling, ESP32-CAM).

A JetBot guards one room together with a fixed ESP32-CAM at the door. The ESP32-CAM checks every person who enters against a face whitelist. An unknown person is queued with an appearance embedding. The robot then follows that person, keeps a safe stand-off distance, holds position when the person stops, steps back if the person lunges, and after the person leaves it searches the saved room map for the next queued target. The system is meant to work in any room: nothing is hard-coded to one room, and the room map, the door reference and the enrolment are made at runtime.

Source of truth: [Project Specification](docs/Project%20Specification.md). Plan, owners, tests and acceptance thresholds: [Implementation Plan](docs/Implementation%20Plan.md).

## How it works

```
 ESP32-CAM (door) --MJPEG/UDP--> laptop: face check (InsightFace) -> whitelist? -> OSNet embedding -> target queue
 JetBot camera ----ZeroMQ JPEG--> laptop: YOLOv8 / pose / ByteTrack / OSNet, state machine, obstacle layer
 laptop --------UDP (v, omega)--> JetBot: motors, behind a dead-man + e-stop (jetson/estop.py)
```

| Phase | What happens | Main code |
| :-- | :-- | :-- |
| 1. Setup | explore the room, match the door against a reference photo (XFeat, DINOv2), choose a vantage point, prompt the user to place the ESP32-CAM, handshake, retract to standby | `sentry/app/deploy_runner.py`, `phase1_runner.py`, `sentry/nav/` |
| 2. Monitoring | face detection and whitelist cosine similarity, re-ID embedding, target queue | `sentry/app/phase2_live.py`, `phase2_pipeline.py`, `target_queue.py`, `sentry/perception/face.py`, `reid.py` |
| 3. Interception | pursue at a stand-off, hold when the target stops, evade a strike, search for the next target | `sentry/app/phase3_runner.py`, `state_machine.py`, `sentry/nav/controllers.py`, `hold_detector.py` |

The robot has no encoders and no working IMU: pose is dead reckoning from calibrated (v, omega) with ArUco marker corrections. The camera is a 160 degree fisheye, so it is calibrated and undistorted before the ground-distance formula is used. The laptop plays the voice prompts and the alarm through its own speakers (the robot has no speaker).

Until the mid-term submission (2026-11-23) the laptop runs all models and the state machine and the Jetson only streams frames and drives the motors. After it, the models move to the Jetson (ONNX to TensorRT 7.1 FP16, each checked against ONNX Runtime) and the laptop becomes the companion app and the backup for any model that cannot run on the Nano. See [Edge Deployment](docs/Edge%20Deployment.md) and the plan, section 5.

## Status (mid-term, 2026-11-22)

| Area | State | Evidence and limits |
| :-- | :-- | :-- |
| Networking, telemetry, e-stop, record/replay | done | video uplink p95 53 ms (6 Oct) and 128 ms (12 Nov) against the 50 ms target |
| Fisheye calibration, ground distance, obstacle detector | done, with limits | no distance on the glossy floor for most furniture; thin floor-level obstacles are not detected |
| Phase 1 (door, vantage, ESP32 handshake) | partly | 7 counted deployment runs; handshake best 9/10 accepts and 10/10 rejects against 10/10 and 10/10; find-door succeeded in 1 of 4 real runs |
| Phase 2 (face check, queue) | partly | face TAR 0.937 at FAR 0/1754 on three team members in one session; the threshold 0.45 is provisional |
| Pursuit and hold | partly | in-band 32 % on 16 Nov against the 80 % goal; hold has not been timed on the robot |
| Strike evasion, coverage search | planned | weeks 8-10 |
| Models on the Jetson | planned | after 2026-11-23; the 13 Nov bench missed the latency goal (14.45 FPS, p95 153 ms) |

The full list of done, partial and open rows, with owners and weeks, is the carry-over table in the Implementation Plan. The mid-term report has the numbers and their limits.

## Repository layout

| Path | Contents |
| :-- | :-- |
| `sentry/` | laptop code: `app/` (runners, state machine, queue, audio), `nav/` (map, vantage, controllers, localization), `net/` (ZeroMQ, UDP, MJPEG, clock sync), `perception/` (obstacle, face, re-ID, tracker, entrance) |
| `jetson/` | robot code, Python 3.6 and stdlib/numpy only: `robot_udp.py`, `camera_pub.py`, `estop.py`, TensorRT bench and parity tools |
| `common/` | wire protocol and command mixing shared by both sides; stdlib only, Python 3.6 compatible |
| `esp32/` | ESP32-CAM firmware (`sentry_cam` for the OV2640 MJPEG board, `tile_stream` for boards without JPEG) |
| `tools/` | live runs (`deploy_live`, `pursue_live`, `find_door`, `session_run`), calibration, recording, evaluation and report tooling |
| `tests/` | pytest suite (about 990 tests) |
| `config.toml` | all thresholds and tuning values; keep them here, do not hard-code them |
| `calib/` | camera and motion calibration files |
| `docs/` | specification, plan, setup, hardware, ESP32-CAM, JetBot and edge notes |
| `reports/` | weekly logs and evidence per person, the mid-term report |
| `data/`, `team_data/`, `weights/` | datasets and model weights; ignored by git (faces and recordings are never committed unzipped, see [Team Data Sharing](docs/Team%20Data%20Sharing.md)) |

## Getting started

Install steps for the GPU laptop, the CPU-only laptop and the Jetson, with the versions we verified, are in [docs/Setup.md](docs/Setup.md). Short version for a laptop (Python 3.12, torch 2.9.1):

```bash
pip install -r requirements.txt          # CPU-only laptop: requirements-cpu.txt
python tools/check_env.py                # must end with ALL GOOD (--cpu-ok without a GPU)
python -m tools.fetch_models             # re-ID, face and XFeat weights (add --dino b for DINOv2)
pytest -m "not gpu and not hil"          # about 1 to 2 minutes, no robot needed
```

Test tiers: T0 unit tests (CPU, no marker), `replay` (recorded data), `gpu` (needs CUDA, skipped otherwise) and `hil` (real robot, only with `--hil`).

## Running

Rehearse without hardware first. The laptop can simulate the robot pose and use a real ESP32-CAM:

```bash
python -m tools.deploy_live --label cafe --vantage 1.2 0.6 --centre 3.0 0.0 --handshake data/handshake/cafe_arch --no-robot
python -m tools.sim_pursuit_hold         # pursuit and hold controllers in the closed-loop simulator
python -m tools.replay_phase3 --help     # replay a recorded session through the state machine
```

With the robot (supervised only):

```bash
python -m tools.jetbot_status <ip>                               # battery and Wi-Fi, at the start and end of every session
python -m tools.self_pose --page-bottom-h 0.0                    # fresh camera pitch before any distance result
python -m tools.session_run --label take1 --camera-pose calib/camera_pose_self_<today>.json -- --handshake data/handshake/<set> --tower-place --wait 120
```

Always use `--ip auto` or let the tools discover the robot: the address changes with every hotspot restart. Robot, ESP32-CAM and laptop share one 2.4 GHz hotspot.

## Safety rules

- `jetson/robot_udp.py` refuses to drive unless `jetson/estop.py` runs on the robot host, is armed (hold Start for 1.5 s) and R1 is held. Releasing R1 or pressing any other button stops the motors.
- Never use `--no-estop` with real motors. Motor tests only with the wheels off the ground, at low speed (default cap 0.3).
- Battery 11.1 V or more is fine; the live tools refuse below 11.4 V and below 10.5 V you stop and charge ([JetBot Notes](docs/JetBot%20Notes.md)). The robot is school property: keep its return checklist up to date.
- Faces and recordings are personal data: enrol only consenting volunteers and delete volunteer data after grading.

## Documentation

[Specification](docs/Project%20Specification.md), [Implementation Plan](docs/Implementation%20Plan.md), [Setup](docs/Setup.md), [Hardware](docs/Hardware.md), [ESP32-CAM](docs/ESP32-CAM.md), [JetBot Notes](docs/JetBot%20Notes.md), [Edge Deployment](docs/Edge%20Deployment.md), [Edge Feasibility](docs/Edge%20Feasibility.md), [Mid-Term Report Plan](docs/Mid-Term%20Report%20Plan.md).

## Working agreement

Branch `<handle>/wNN-topic`, then a pull request to `main` with one approving review and the tests passing; no direct pushes to `main`. Review rotation: DQK's PRs go to KR, KR's to HNHL, HNHL's to DQK. Evidence goes to `reports/<handle>/week-NN/`, the weekly log to `reports/<handle>/week-NN.md` (template: `reports/TEMPLATE.md`). `common/` and `jetson/` must stay Python 3.6 compatible.

## Mid-term review

[Report (editable source)](reports/midterm_report_draft.md), [code appendix](reports/kouun-rokku/midterm-appendix-a.md), [Week 7 validation and provenance](reports/kouun-rokku/week-07.md).

```bash
python -m tools.run_cpu_tests
python -m tools.check_midterm_package --ref HEAD
python -m tools.build_midterm_package --ref HEAD --out /tmp/submission.zip
```

For PDF reproduction install `requirements-report.txt`, then run `python -m tools.render_midterm_report`. Report sources distinguish CPU tests, pilot/dev-val data and hardware measurements. Pending acceptance remains explicit. The submission ZIP excludes data, team_data, recordings and weights using Git pathspecs; D5 and the D2 archive stay tracked in the development tree. The PDF is generated for review and committed only at the freeze tag. Building a ZIP does not sanitize old repository history.
