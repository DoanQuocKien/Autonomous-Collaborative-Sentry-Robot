# Week 02 – kouun-rokku (2026-10-12 to 2026-10-18)

*Focus: XFeat + DINOv2 entrance detection & bearing estimation, per-wheel motion model (`WheelModel`) dead reckoning (issue #41), ArUco fiducial localization, and T0/T1 test suite.*

## Done

- **Entrance Detection & Bearing Estimation (`sentry/perception/entrance.py`, `tools/enroll_entrance.py`):**
  - Replaced the initial ORB baseline with `EntranceDetector(camera)(frame_bgr, t) -> EntranceResult(in_view, inliers, similarity, bearing_rad, quad)` using **XFeat** (vendored in `third_party/xfeat/`, `top_k = 2048`, mutual nearest-neighbour matching, RANSAC homography, hull scale check) and **DINOv2** (CLS + GeM patch tokens, cosine similarity for phone-photo reference / secondary check).
  - Implemented `EntranceFilter` with hysteresis debouncing (`enter = 3`, `exit = 5`) and median bearing smoothing to emit `ENTRANCE_FOUND` / `ENTRANCE_LOST` events for the state machine.
  - Per-room calibration (`EntranceDetector.calibrate`, `save` / `load`) sets the XFeat inlier threshold above a sweep of room negatives (minimum 27 inliers) and projects the enrolled door ROI through the homography to compute horizontal bearing (`bearing_rad`, positive = left / `+w` via calibrated fisheye intrinsics from `calib/camera.json`).
  - **D1 Classroom Door Evaluation (T1, `reports/DoanQuocKien/week-02/d1/entrance_bench_2026-10-12.md`):** On the primary demo door (classroom white door, reference position excluded), `EntranceDetector` with XFeat achieves **TPR 1.00 (210/210) and FPR 0.00 (0/52)**, passing the plan target ($\text{TPR} \ge 90\%$, $\text{FPR} \le 5\%$), with projected door-centre bearing within $\sim 6^\circ$ at 1.5–3.0 m. On the secondary/optional cafe glass door, XFeat reaches TPR 0.87 / FPR 0.055–0.081.
- **Dead Reckoning on `WheelModel` & ArUco Localization (`sentry/nav/localization.py`, Issue #41):**
  - Switched `LocalizationTracker` dead reckoning from the legacy single-speed proportional gains (`v_gain * v`, `w_gain * w`) to the per-wheel motion law **`WheelModel`** (`sentry/nav/wheel_model.py`, `calib/motion.json`: $v_{\text{wheel}} = \text{scale} \cdot 1.64 \cdot (|\text{motor}| - 0.038)\text{ m/s}$ above `min_pwm = 0.12` at `max_speed = 0.3`, wheel track $0.137\text{ m}$), matching the 2026-10-15 classroom marker measurements across $v \in [0.4, 1.0]$ and $w \in [0.4, 1.0]$ while preserving steering while driving (e.g. $v = 0.6, w = 0.065$).
  - Exposed online tuning knobs (`scale`, `min_pwm`, `max_speed`) on `LocalizationTracker` delegating directly to `self.wheel_model`.
  - Addressed PR #36 / #37 review items: default marker size read from `config.toml` (`aruco_marker_m = 0.15 m`, `DICT_4X4_50`), `solvePnPGeneric` (`SOLVEPNP_IPPE_SQUARE`) with iterative fallback and positive-$Z$ front-of-wall validation, anchor range gating (`max_marker_distance_m = 1.5 m` with linear alpha decay beyond `0.8 m`), and heading jump rejection ($> 25^\circ$ after convergence).
  - **Interoperability with HNHL (PR #27):** `x_m`, `y_m`, `yaw_rad` aliases on `RobotPose` to match `Pose2D`, and `calculate_door_world_xy` to supply `VantageSelector` with world-frame doorway coordinates.
- **Unit Testing Suite (`tests/test_entrance.py`, `tests/test_localization.py`, `tests/test_wheel_model.py`):**
  - `test_entrance.py`: validates XFeat homography & bearing sign, degenerate hull rejection, negative-sweep threshold calibration, DINOv2 phone-reference calibration, `and`/`or` policies, save/load round-trip, `EntranceFilter` debouncing, and equidistant fisheye bearing symmetry.
  - `test_localization.py`: validates `WheelModel` speed/turn integration against the 2026-10-15 marker measurements (issue #41), per-wheel deadzone during simultaneous steering and driving, closed-square path closure (error $< 1\text{ mm}$ in simulation), synthetic ArUco pose estimation, range gating & alpha decay, and `Pose2D` compatibility.

## Tests run

| Tier | Command | Result | Evidence |
| :-- | :-- | :-- | :-- |
| T0 | `python -m pytest -m "not gpu and not hil"` | 342 passed, 4 skipped, 1 deselected in 16.07 s | [pytest.log](week-02/pytest.log) |
| T0 | `python -m pytest tests/test_entrance.py -v` | 10 passed, 2 skipped in 3.75 s | [pytest.log](week-02/pytest.log) |
| T0 | `python -m pytest tests/test_localization.py tests/test_wheel_model.py -v` | 15 passed in 3.39 s (WheelModel odometry, closed square path & ArUco fusion) | [pytest.log](week-02/pytest.log) |
| T1 | Classroom door evaluation (`sentry/perception/entrance.py`, XFeat `auto`) | TPR 1.00 (210/210), FPR 0.00 (0/52) | [entrance_bench_2026-10-12.md](../DoanQuocKien/week-02/d1/entrance_bench_2026-10-12.md) |

## Acceptance criteria status (Implementation Plan §4.3)

- **Entrance recognition (XFeat + DINOv2, primary demo door = classroom door):** **TPR 1.00 ($\ge 90\%$), FPR 0.00 ($\le 5\%$)** with per-room negative calibration on D1 classroom dataset $\rightarrow$ **Pass (T1)** (secondary cafe glass door reported without threshold: TPR 0.87 / FPR 0.06).
- **Pose integration (`WheelModel`, closed square path):** Robot executes a $1\text{ m} \times 1\text{ m}$ square path in simulation using `WheelModel` and returns to origin `(0, 0, 0)` $\rightarrow$ **Pass (T0)** ($< 1\text{ mm}$ residual error); speeds and turn rates match 2026-10-15 marker measurements within 6–8%.
- **ArUco pose estimation on synthetic renders:** Detects `DICT_4X4_50` ($0.15\text{ m}$) markers, extracts 3D translation vector and horizontal bearing, and fuses anchor observations within $1.5\text{ m}$ $\rightarrow$ **Pass (T0)**.

## Blockers / risks

- **Open-loop floor heading veer:** As measured on 2026-10-15 (`calib/motion.json`), open-loop drives on the classroom glossy tile show a random per-run spread ($\approx \pm 10^\circ/\text{m}$ with a left bias), so fixed drift compensation is disabled in `WheelModel` and online marker correction is used when anchors are in view.
- **Sunday T2 Session (2026-10-18):** T2 3 m dead-reckoning path with ArUco correction ($\le 15\text{ cm}$ with correction, $\le 40\text{ cm}$ without) and T2 end-to-end exploration with obstacle repulsion to be run at the Sunday integration session.

## Next steps (Week 3 prep & integration)

- Run the Sunday T2 3 m dead-reckoning + ArUco correction protocol with DQK.
- Implement `sentry/net/mjpeg_rx.py` with auto-reconnect for the OV2640 ESP32 stream (alongside `sentry.espcam.TileReceiver` for GC2145).
- Wire `sentry/perception/entrance.py` into the ESP32 placement handshake check (enrolled with an ESP32 reference frame).
- Generate offline speech prompts (`assets/audio/`) and implement `sentry/app/state_machine.py` skeleton.
