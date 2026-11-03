# Week 05 – kouun-rokku (2026-11-02 to 2026-11-08)

*Focus: Target ground speed hold detector with robot motion compensation (`sentry/nav/hold_detector.py`, `tools/evaluate_hold_detector.py`), pursuit and standoff hold controllers (`sentry/nav/controllers.py`), original ByteTrack vendoring for Python 3.6 edge compatibility (`third_party/bytetrack/`, `tools/evaluate_bytetrack_parity.py`), closed-loop simulation on unicycle kinematics (`tools/sim_pursuit_hold.py`), and Mid-Term Report chapter drafts (Chapters 1, 2, 6, 7, Appendix A, Figures F12, F15, F16).*

## Done

- **Target Ground Speed Hold Detector with Robot Pose/Yaw Compensation (`sentry/nav/hold_detector.py`, `tests/test_hold_detector.py`, `tools/evaluate_hold_detector.py`):**
  - Implemented `HoldDetector`, `HoldConfig`, and `HoldState` according to `Project Specification.md` §4.5 and `Implementation Plan.md` §4.3.
  - Transforms target local observations $(x_f, y_l)$ to the world coordinate frame $(X_w, Y_w)$ using the robot's dead-reckoned unicycle pose $(x_r, y_r, \theta_r)$:
    $$\begin{pmatrix} X_w \\ Y_w \end{pmatrix} = \begin{pmatrix} x_r \\ y_r \end{pmatrix} + \begin{pmatrix} \cos\theta_r & -\sin\theta_r \\ \sin\theta_r & \cos\theta_r \end{pmatrix} \begin{pmatrix} x_f \\ y_l \end{pmatrix}$$
  - Computes ground velocity vector $(v_{x,w}, v_{y,w})$ via ordinary least-squares linear regression over a sliding window ($0,5\text{ s}$), filtering high-frequency vision detection noise ($\pm 2\text{ cm}$).
  - Enforces the strict $2,0\text{ s}$ dwell time requirement: transitions to `HOLD` and dispatches `TARGET_STATIONARY` when $v_{\text{target}} < 0,1\text{ m/s}$ for $> 2,0\text{ s}$.
  - Implemented hysteresis: robot remains in `HOLD` during creeping motions in the $[0,1; 0,2]\text{ m/s}$ band; exits `HOLD` and dispatches `TARGET_MOVING` only when $v_{\text{target}} > 0,2\text{ m/s}$.
  - Verified the core acceptance invariant: **"Robot yawing alone never triggers hold"** (when target is moving, robot spinning at $1,5\text{ rad/s}$ produces 0 false hold triggers; when target is stationary, robot spinning does not disrupt hold).
- **Pursuit PD & Standoff Hold Controllers (`sentry/nav/controllers.py`, `tests/test_controllers.py`):**
  - Implemented `PursuitController`, `HoldController`, and `InterceptionController` according to `Project Specification.md` §4.5 (collaborative reference implementation with DQK, who leads real-robot gain tuning on 2026-11-09).
  - Standardized state and mode naming strictly to `"PURSUE"` and `"HOLD"` across all controllers, telemetry outputs, and state machine transitions.
  - **Motor Dead-Zone & Legal Commands:** Integrated physical JetBot dead-zone rules ($\text{dead} = 0,40$). In HOLD, active recentering commands are boosted to $|w| \ge 0,45\text{ rad/s}$ ($w_{\text{spin}}$) to prevent motor whining and stalling, and stops cleanly ($v=0, w=0$) when within tolerance $\pm 10\%$. In PURSUE, reverse is capped at $v_{\text{min\_reverse}} = -0,45$, and all emitted commands pass `legal()` verification.
  - **Recentering Enforcement:** Measured recentering duration in `HoldController`; verified bbox centering within $\pm 10\%$ frame width well within $1,5\text{ s}$ (`max_recenter_time_s = 1.5`).
  - **Derivative Kick Suppression:** Clamped derivative terms when $\Delta t > 0,2\text{ s}$ to prevent command spikes on dropped/stalled camera frames.
  - **Obstacle Override:** When foreground obstacle distance $d_{\text{obs}} < 0,5\text{ m}$, adds a repulsive yaw deflection offset ($w_{\text{avoid}} = 0,45\text{ rad/s}$) away from the obstacle while preserving target line-of-sight. When $d_{\text{obs}} < 0,35\text{ m}$, cuts forward velocity ($v \le 0$) to prevent impact.
- **Original ByteTrack Tracker Vendoring for Python 3.6 Edge Compatibility (`third_party/bytetrack/`, `tests/test_bytetrack_vendored.py`, `tools/evaluate_bytetrack_parity.py`):**
  - Vendored the original MIT-licensed ByteTrack tracker (`ifzhang/ByteTrack`, ECCV 2022) into `third_party/bytetrack/` with `LICENSE` and `NOTICE.md`.
  - Ported to pure NumPy and SciPy (`scipy.optimize.linear_sum_assignment`), eliminating the requirement for compiled C++ `lap` binaries on resource-constrained Jetson Nano boards.
  - Cleaned API and parameter names to standard `track_thresh`, `track_buffer`, `match_thresh`, accepting raw NumPy ndarrays `[x1, y1, x2, y2, score, ...]`, fully decoupled from Ultralytics AGPL wrappers.
  - Verified Python 3.6 AST syntax compatibility across all vendored files via `ast.parse(..., feature_version=(3, 6))` with zero `sentry.*` or `dataclasses` imports.
  - Implemented `VendoredByteTrackBackend` in `sentry/perception/tracker.py` as a drop-in backend.
  - Evaluated on a comprehensive multi-scenario benchmark (multi-target random occlusions + explicit crossing track swaps) with strict bipartite Hungarian matching that scores any unmatched/dropped track as a disagreement: achieved **100.0% ID agreement** (407/407 evaluations) against Ultralytics ByteTrack.
- **Closed-Loop Pursuit and Hold Simulation (`tools/sim_pursuit_hold.py`, `tests/test_pursuit_hold_sim.py`):**
  - Built `tools/sim_pursuit_hold.py` driving `SimRobot` unicycle kinematics at 50 Hz with a scripted intruder and obstacle, routing commands through `legal()` dead-zone checks.
  - Verified end-to-end closed-loop pursuit: $100.0\%$ centering ratio, obstacle avoidance deflection, hold trigger at $t=6,34\text{ s}$ ($2,34\text{ s}$ after target stop), zero translation during hold, recentering $\le 1,5\text{ s}$, $100\%$ legal commands, and clean hysteresis resumption at $t=8,26\text{ s}$.
- **Mid-Term Report Drafts & Figures (`Mid-Term Report Plan.md`):**
  - Drafted 5 chapters/appendices owned by KR:
    * `reports/kouun-rokku/midterm-chapter-01.md`: Chapter 1 — Giới thiệu và bài toán (1,0 trang).
    * `reports/kouun-rokku/midterm-chapter-02.md`: Chapter 2 — Các công trình liên quan (1,5 trang, tổng hợp 15 bài báo chuẩn hóa).
    * `reports/kouun-rokku/midterm-chapter-06.md`: Chapter 6 — Hành vi và điều khiển hệ thống (1,5 trang).
    * `reports/kouun-rokku/midterm-chapter-07.md`: Chapter 7 — Kiểm thử và kết quả thực nghiệm (1,5 trang; đối soát trung thực T0/T1/T2, tách bạch ArUco PENDING vs Dead-Reckoning FAIL, cite log thực tế).
    * `reports/kouun-rokku/midterm-appendix-a.md`: Phụ lục A — Bàn giao mã nguồn và hệ thống (1,0 trang).
  - Implemented plotting scripts and generated Figures F12, F15, F16:
    * `F12_entrance_bakeoff.png`: ORB vs XFeat vs DINOv2 AUC and TPR@5%FPR per door (`tools/plot_f12_entrance.py`), with non-obscured labels and clear baseline notation.
    * `F15_dead_reckoning_aruco.png`: Position error & end poses plotted strictly from real measured runs (2026-10-24 tape ground truth vs estimates: 14.5 cm with correction, 98.3 cm without; 2026-10-30 deployment tape offsets; no synthetic paths).
    * `F16_state_machine.png`: Complete Phase 1–3 state machine diagram (`tools/plot_f16_state_machine.py`).

## Tests run

| Tier | Command | Result | Evidence |
| :-- | :-- | :-- | :-- |
| T0 | `pytest tests/test_hold_detector.py tests/test_controllers.py tests/test_bytetrack_vendored.py tests/test_pursuit_hold_sim.py` | 22/22 passed (timing, hysteresis, robot yaw invariance, PD standoff, obstacle override, hold zero translation, deadzone legal commands, recenter <= 1.5s, Python 3.6 AST, parity) | `reports/kouun-rokku/week-05/pytest.log` |
| T0 / T1 | `pytest -m "not gpu and not hil"` | **600 passed, 5 skipped, 4 deselected** (full CPU test suite clean) | `reports/kouun-rokku/week-05/pytest.log` |
| T0 | `python3 -m tools.evaluate_hold_detector --out reports/kouun-rokku/week-05/hold_detector_metrics.json` | Dwell trigger $2,05\text{ s}$, hysteresis band maintained, 0 false hold triggers under robot yaw $\rightarrow$ **PASS** | `reports/kouun-rokku/week-05/hold_detector_metrics.json` |
| T0 | `python3 -m tools.evaluate_bytetrack_parity --out reports/kouun-rokku/week-05/bytetrack_parity.json` | **100.0% ID agreement** (407/407 evaluations, crossing + multi-track, dropped tracks penalized) vs $\ge 95.0\%$ threshold $\rightarrow$ **PASS** | `reports/kouun-rokku/week-05/bytetrack_parity.json` |
| T0 | `python3 -m tools.sim_pursuit_hold --out reports/kouun-rokku/week-05/sim_pursuit_hold.json` | Closed loop against SimRobot: $100\%$ centering, dwell met at $t=6,34\text{ s}$, zero translation, $100\%$ legal commands, recenter $\le 1,5\text{ s}$, exit met at $t=8,26\text{ s}$ $\rightarrow$ **PASS** | `reports/kouun-rokku/week-05/sim_pursuit_hold.json` |

## Acceptance criteria status (Implementation Plan §4.3)

- **Hold detector (`sentry/nav/hold_detector.py`):** Verified target speed in world frame while robot yaws; robot rotation alone produces 0 false hold triggers; HOLD exits when target speed $> 0,2\text{ m/s}$ $\rightarrow$ **Pass (T0 / Simulation; real-world heading drift impact untested)**.
- **Standoff hold (`sentry/nav/controllers.py`, `tools/sim_pursuit_hold.py`):** Verified stops $2,0–3,0\text{ s}$ after target stops; bbox centered within $\pm 10\%$ width within $\le 1,5\text{ s}$; translation strictly $v = 0,0$ without orbiting; commands overcome dead zone $0,40$ $\rightarrow$ **Pass (T0 / Simulation; physical robot tuning with DQK on 2026-11-09)**.
- **ByteTrack vendored parity (`third_party/bytetrack/`):** Python 3.6 AST compatibility verified with zero sentry imports; achieved **100.0% ID agreement** against Ultralytics ByteTrack on multi-track scenarios vs $\ge 95\%$ target $\rightarrow$ **Pass (T0 / Stage A gate G2; D3 real video $\ge 60\text{ s}$ metric PENDING)**.
- **Mid-Term Report drafts:** Completed drafts for Chapters 1, 2, 6, 7 and Appendix A along with figures F12, F15, F16 $\rightarrow$ **Ready for team review**.

## Blockers / risks

- **Hardware Validation of Pursuit + Hold (Week 6 Session):** Closed-loop pursuit and hold controller verified in 50 Hz unicycle simulation; physical trials on real JetBot with DQK scheduled for Monday session (2026-11-09).
- **IMU Sensor Revival:** MPU6050 postponed by DQK on 2026-11-01; dead-reckoning + ArUco marker feedback remains the primary localization pipeline.

## Next week (Week 6)

- Wire PURSUE and HOLD states to live perception loop (`PersonTracker` + `HoldDetector` + `PursuitController` / `HoldController`).
- Support DQK in real-robot pursuit and standoff hold tuning during the classroom session.
- Editor responsibilities: merge chapter drafts from DQK and HNHL into unified report draft, verify page budgets, and check numeric consistency against evidence files.
