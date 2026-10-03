# Autonomous Collaborative Sentry Robot (CS532)

Spec: `docs/Project Specification.md` (source of truth). 8-week capstone; Mid-Term Report due Week 4.

## Environment
- Conda env `sentry` (Python 3.10, torch cu121). Run without activating: `C:\Users\admin\miniconda3\envs\sentry\python.exe`. Spec in `environment.yml`.
- Laptop: Windows 11, RTX 4050 6GB. Jetson Nano: Ubuntu 18.04, Python 3.6, so Jetson code lives in `jetson/` with its own minimal requirements; never share the `sentry` env with it.

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
- Keep seeds, logging and calibration knobs in research code. One small `test_*.py` for non-trivial logic.
- Serena: set `languages: [python]` in `.serena/project.yml` once code exists. `.serena/` and `graphify-out/` are gitignored.
