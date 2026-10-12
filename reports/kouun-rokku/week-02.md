# Week 02 – kouun-rokku (2026-10-12 to 2026-10-18)

*Focus: ORB entrance detection & bearing estimation, motion model dead reckoning, ArUco fiducial localization, and T0 test suite.*

## Done

- **ORB Entrance Feature Matching (`sentry/perception/entrance.py`):**
  - Implemented `EntranceMatcher` class conforming to the CPU callable contract `__call__(frame_bgr, t) -> EntranceResult` with no global state.
  - Extracts ORB descriptors (2000 features), performs Hamming Brute-Force KNN matching with Lowe's ratio test (threshold 0.75), and estimates robust RANSAC homography.
  - Calculates entrance centroid in frame pixel space and converts it to continuous horizontal bearing angle (`bearing_rad`, `bearing_deg`) using calibrated camera intrinsics from `calib/camera.json`.
  - Respects coordinate convention: positive yaw indicates target is on the left (yaw left / +w to face entrance).
  - Designed for reuse in Week 3 ESP32 camera placement verification.
- **Dead Reckoning & ArUco Localization (`sentry/nav/localization.py`):**
  - Implemented `LocalizationTracker` integrating normalized `(v, w)` commands with exact unicycle kinematics and circular arc integration.
  - Ingests empirical motion parameters from `calib/motion.json` (`v_gain_m_per_s = 0.4135`, `w_gain_rad_per_s = 6.4802`, curvature drift `drift_rad_per_m = -0.1859`).
  - Detects `DICT_4X4_50` ArUco markers using `cv2.aruco`, computes 6-DoF pose (`solvePnP` with fisheye point undistortion), and estimates range and horizontal bearing.
  - Implemented anchor fusion: updates dead-reckoned robot pose in room coordinates when known marker anchors (`MarkerAnchor`) are observed.
  - **Interoperability with HNHL (PR #27):** added `x_m`, `y_m`, `yaw_rad` property aliases to `RobotPose` to match `Pose2D`, and implemented `calculate_door_world_xy` / `estimate_door_world_xy` to supply `VantageSelector` with world-frame doorway coordinates.
- **Unit Testing Suite (`tests/test_entrance.py`, `tests/test_localization.py`):**
  - `test_entrance.py`: validates match detection on rich synthetic doorframes, bearing shifts for off-center targets, rejection of blank/noise frames, strict threshold enforcement, and world-coordinate estimation.
  - `test_localization.py`: validates pose integration, angle normalization, exact closed-square path closure (error < 1 mm in simulation), synthetic ArUco pose estimation, anchor filter fusion, and Pose2D attribute compatibility.
- **Compatibility & Bug Fixes:**
  - Resolved `AttributeError: module 'cv2' has no attribute 'CALIB_RECOMPUTE_EXTRINSIC'` in `tools/calibrate_fisheye.py` by supporting both `cv2.fisheye` and top-level OpenCV module attributes.
  - Re-exported nav and perception classes gracefully in `sentry/nav/__init__.py` and `sentry/perception/__init__.py`.

## Tests run

| Tier | Command | Result | Evidence |
| :-- | :-- | :-- | :-- |
| T0 | `pytest -m "not gpu and not hil"` | 290 passed, 4 skipped, 1 deselected in 13.55 s | [pytest.log](week-02/pytest.log) |
| T0 | `pytest tests/test_entrance.py -v` | 10 passed, 2 skipped in 2.3 s | [pytest.log](week-02/pytest.log) |
| T0 | `pytest tests/test_localization.py -v` | 6 passed in 1.6 s (including closed square path & ArUco detection) | [pytest.log](week-02/pytest.log) |


## Acceptance criteria status (Implementation Plan §4.3)

- **ORB entrance logic & bearing:** Functional on synthetic scenes with sub-degree bearing accuracy and clean rejection of negative frames -> **Pass (T0)**. T1 TPR/FPR threshold evaluation pending D1 dataset delivery.
- **Pose integration (closed square path):** Robot executes a 1 m x 1 m square path in simulation and returns to origin `(0, 0, 0)` -> **Pass (T0)** (< 1 mm residual drift).
- **ArUco pose estimation on synthetic renders:** Detects `DICT_4X4_50` markers, extracts 3D translation vector and horizontal bearing -> **Pass (T0)**.

## Blockers / risks

- **Awaiting D1 Dataset (Classroom & Doorways):** Real-world evaluation (T1 TPR >= 90%, FPR <= 5%) requires DQK's recorded doorway photos and manifests from the D1 classroom session.
- **Awaiting Sunday HIL Session:** Real-world motion repeatability and ArUco 3 m path accuracy (T2 <= 15 cm with ArUco) will be evaluated on the physical JetBot with DQK.

## Next steps (Week 3 prep & integration)

- Evaluate `entrance.py` on D1 doorway dataset once shared; tune `min_inliers` and Lowe ratio thresholds.
- Implement `sentry/net/mjpeg_rx.py` with auto-reconnect for ESP32 stream.
- Wire `entrance.py` into the ESP32 placement handshake protocol.
- Generate offline speech prompts (`assets/audio/`) using TTS.
