# Autonomous Collaborative Sentry Robot (CS532)

Spec: `docs/Project Specification.md` (source of truth). Plan: `docs/Implementation Plan.md` (owners, interfaces, tests, acceptance thresholds). 8 weeks from 2026-10-05; Mid-Term Report due Week 4.

## Environment
- Conda env `sentry` (Python 3.12, torch 2.9.1+cu128; cloned from the UITRacingCar env, so never modify that one). Run without activating: `C:\Users\admin\miniconda3\envs\sentry\python.exe`. Extra deps in `requirements.txt`. Teammates make their own env the same way.
- Install steps for every machine (GPU laptop, CPU laptop, Jetson) and known problems: `docs/Setup.md`. Verify with `python tools/check_env.py`. Tests: `pytest`.
- `common/` and `jetson/` must stay Python 3.6-compatible (no dataclasses, walrus, `capture_output`); `common/` is stdlib-only.
- Laptop: Windows 11, RTX 4050 6GB. Jetson Nano: Ubuntu 18.04, Python 3.6, so Jetson code lives in `jetson/` with its own minimal requirements; never share `sentry` with it.

## Architecture
- Laptop runs ALL models (YOLOv8, YOLOv8-pose, InsightFace, OSNet) and the state machine. Jetson only captures frames and drives motors.
- JetBot -> laptop: ZeroMQ, JPEG q60 (5 GHz). Laptop -> JetBot: non-blocking UDP (v, omega). ESP32-CAM: MJPEG VGA 15 FPS (2.4 GHz).
- No encoders/IMU: pose = dead reckoning from calibrated (v, omega) + ArUco corrections. Camera is a 160deg fisheye: calibrate and undistort before the ground-distance formula.
- Audio: USB speaker playing pre-generated WAVs (offline TTS rendered on the laptop).

## Constants (keep in one config, never hardcode; hardware needs tuning)
- Obstacle repulsion: 0.6 m (exploration), 0.5 m (pursuit override)
- Whitelist cosine sim threshold 0.45; entrance distance 1.5-3.0 m
- Standoff 1.2 m. Target ground speed <0.1 m/s for >2 s -> HOLD (stop, yaw to re-center, never orbit); exit above 0.2 m/s
- After T1 exits: coverage-path search on the saved room map (r_det placeholder 3.0 m, 90 % coverage); unfound targets are dropped from the queue
- Strike: bbox area growth dA/A > 0.40 in 100 ms -> v=-1.0, omega=+-0.8 for 400 ms

## Conventions
- Team: DoanQuocKien (CUDA, holds the JetBot kit), HuynhNguyenHoaiLoc (CUDA, perception), kouun-rokku (no CUDA, CPU logic/tooling, holds the ESP32-CAM + MB base). Branch `<handle>/wNN-topic`, PR + 1 review.
- Tests: T0 unit (no marker, CPU), `replay`, `gpu`, `hil` markers. Evidence goes to `reports/<handle>/week-NN/`.
- Safety: `jetson/robot_udp.py` refuses to drive unless `jetson/estop.py` (gamepad e-stop, host) is running and armed (hold Select+Start 2 s); any gamepad button stops. Never use `--no-estop` with real motors. Motor tests only with wheels off the ground.
- Robot sessions: run `python -m tools.jetbot_status <ip>` at start/end and between long tests; battery >= 11.1 V OK, < 10.5 V stop and charge (see `docs/JetBot Notes.md`). The robot is school property: keep the return checklist there up to date.
- Keep seeds, logging and calibration knobs in research code. One small `test_*.py` for non-trivial logic.
- Serena: set `languages: [python]` in `.serena/project.yml` once code exists. `.serena/` and `graphify-out/` are gitignored.
