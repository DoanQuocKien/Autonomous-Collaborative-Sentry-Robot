# Autonomous Collaborative Sentry Robot (CS532)

Spec: `docs/Project Specification.md` (source of truth). Plan: `docs/Implementation Plan.md` (owners, interfaces, tests, acceptance thresholds). 8 weeks from 2026-10-05; Mid-Term Report due Week 4.

## Environment
- Conda env `sentry` (Python 3.12, torch 2.9.1+cu128; cloned from the UITRacingCar env, so never modify that one). Run without activating: `C:\Users\admin\miniconda3\envs\sentry\python.exe`. Extra deps in `requirements.txt`. Teammates make their own env the same way.
- Laptop: Windows 11, RTX 4050 6GB. Jetson Nano: Ubuntu 18.04, Python 3.6, so Jetson code lives in `jetson/` with its own minimal requirements; never share `sentry` with it.

## Architecture
- Laptop runs ALL models (YOLOv8, YOLOv8-pose, InsightFace, OSNet) and the state machine. Jetson only captures frames and drives motors.
- JetBot -> laptop: ZeroMQ, JPEG q60 (5 GHz). Laptop -> JetBot: non-blocking UDP (v, omega). ESP32-CAM: MJPEG VGA 15 FPS (2.4 GHz).
- No encoders/IMU: pose = dead reckoning from calibrated (v, omega) + ArUco corrections. Camera is a 160deg fisheye: calibrate and undistort before the ground-distance formula.
- Audio: USB speaker playing pre-generated WAVs (offline TTS rendered on the laptop).

## Constants (keep in one config, never hardcode; hardware needs tuning)
- Obstacle repulsion: 0.6 m (exploration), 0.5 m (pursuit override)
- Whitelist cosine sim threshold 0.45; entrance distance 1.5-3.0 m
- Standoff 1.2 m, orbit R ~1.0 m, stationary <0.1 m/s for >2 s -> circling
- Strike: bbox area growth dA/A > 0.40 in 100 ms -> v=-1.0, omega=+-0.8 for 400 ms

## Conventions
- Team: DoanQuocKien (CUDA, holds all hardware), HuynhNguyenHoaiLoc (CUDA, perception), kouun-rokku (no CUDA, CPU logic/tooling). Branch `<handle>/wNN-topic`, PR + 1 review.
- Tests: T0 unit (no marker, CPU), `replay`, `gpu`, `hil` markers. Evidence goes to `reports/<handle>/week-NN/`.
- Keep seeds, logging and calibration knobs in research code. One small `test_*.py` for non-trivial logic.
- Serena: set `languages: [python]` in `.serena/project.yml` once code exists. `.serena/` and `graphify-out/` are gitignored.
