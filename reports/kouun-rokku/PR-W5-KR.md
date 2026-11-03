# W5: Hold detector, pursuit/hold controllers, vendored ByteTrack, and Mid-Term Report drafts

## Behavior

- **Target Ground-Speed Hold Detector (`sentry/nav/hold_detector.py`):**
  Projects local target observations $(x_f, y_l)$ to world coordinates $(X_w, Y_w)$ via dead-reckoned unicycle pose $(x_r, y_r, \theta_r)$. World velocity $(v_{x,w}, v_{y,w})$ is estimated via ordinary least-squares linear regression over a 0.5 s window with `min_samples = 5` and `min_window_span_s = 0.2 s`, eliminating vision jitter and cluster spikes. Triggers `TARGET_STATIONARY` (state `HOLD`) when $v_{\text{target}} < 0.1\text{ m/s}$ for $> 2.0\text{ s}$; enforces hysteresis band $[0.1, 0.2]\text{ m/s}$ and triggers `TARGET_MOVING` (state `PURSUE`) only when $v_{\text{target}} > 0.2\text{ m/s}$. When target is lost for $> 1.0\text{ s}$, resets history and releases `HOLD`. Invariant verified: robot yawing alone never triggers hold.
- **Pursuit & Standoff Hold Controllers (`sentry/nav/controllers.py`):**
  - Standardized mode strings strictly to `"PURSUE"` and `"HOLD"` across all controllers and transitions (matching `sentry.app.state_machine.State.PURSUE`).
  - Single Source of Truth: All physical thresholds (`standoff_m`, `standoff_tolerance_m`, `obstacle_pursuit_m`, `stationary_speed_mps`, `stationary_time_s`, `stationary_exit_speed_mps`) are loaded strictly from `[thresholds]` in `config.toml`.
  - Motor Dead-Zone Enforcement: All motion commands obey JetBot dead zone ($\text{dead} = 0.40$). In HOLD, translation is strictly $v = 0.0$ and active recentering outputs $|w| \ge 0.45$ ($w_{\text{spin}}$), stopping cleanly $(0, 0)$ when within $\pm 10\%$ tolerance. In PURSUE, reverse is set to $v_{\text{min\_reverse}} = -0.45$. All commands pass `sentry.nav.explore.legal()` checks.
  - Recentering Tracking: Enforces and measures recentering duration in `HoldController`, verifying centering within $\le 1.5\text{ s}$ (`max_recenter_time_s = 1.5`).
  - Derivative Kick Suppression: Limits derivative terms when $\Delta t > 0.2\text{ s}$ to eliminate derivative kick on stalled/dropped frames.
  - Obstacle Override: Deflects with $w_{\text{avoid}} = 0.45\text{ rad/s}$ when $d_{\text{obs}} < 0.5\text{ m}$ and suppresses forward speed when $d_{\text{obs}} < 0.35\text{ m}$.
  - Ownership: Reference control logic implemented collaboratively for W5; physical robot parameter tuning will be led by DQK on 2026-11-09.
- **Original ByteTrack Tracker Vendoring (`third_party/bytetrack/`):**
  Clean MIT lineage from `ifzhang/ByteTrack` (ECCV 2022). Standalone pure NumPy and SciPy implementation (`scipy.optimize.linear_sum_assignment`), eliminating compiled C++ `lap` binaries. Uses standard NumPy ndarrays `[x1, y1, x2, y2, score, ...]`, free of AGPL wrappers. Verified Python 3.6 AST syntax compatibility with zero `sentry.*` or `dataclasses` imports.
- **Closed-Loop Simulation (`tools/sim_pursuit_hold.py`):**
  Simulates closed-loop pursuit, obstacle avoidance, and standoff hold at 50 Hz against `SimRobot` with full motor dead-zone enforcement through `legal()`.
- **Mid-Term Report Drafts & Figures:**
  Drafts for Chapters 1, 2, 6, 7 and Appendix A. Figures F12 (labels clear of legend), F15 (plotted strictly from real measured physical runs: end poses & tape ground truth, 14.5 cm with correction, 98.3 cm without, 10-30 deployment offsets; no synthetic paths), and F16.

## Validation

- Full CPU test suite: **604 passed, 5 skipped, 4 deselected in ~25s**. Log: `reports/kouun-rokku/week-05/pytest.log`.
- Python 3.6 AST validation: all files in `third_party/bytetrack/` pass `ast.parse(..., feature_version=(3, 6))`.
- ByteTrack parity evaluation: `python -m tools.evaluate_bytetrack_parity --out reports/kouun-rokku/week-05/bytetrack_parity.json` $\rightarrow$ **100.0% ID agreement** (407/407 evaluations across multi-object and crossing track swaps, with unmatched/dropped tracks penalized as disagreements) $\rightarrow$ **PASS**.
- Hold detector metrics: `python -m tools.evaluate_hold_detector --out reports/kouun-rokku/week-05/hold_detector_metrics.json` $\rightarrow$ Dwell time trigger $2.0\text{ s}$, hysteresis band maintained, 0 false hold triggers under robot yaw $\rightarrow$ **PASS**.
- Closed-loop simulation: `python -m tools.sim_pursuit_hold --out reports/kouun-rokku/week-05/sim_pursuit_hold.json` $\rightarrow$ 100% legal motor commands, $100.0\%$ centering, dwell met at $t=6.34\text{ s}$, zero translation, recentering $\le 1.5\text{ s}$, hysteresis exit at $t=8.26\text{ s}$ $\rightarrow$ **PASS**.
- Figures generated: `F12_entrance_bakeoff.png`, `F15_dead_reckoning_aruco.png`, `F16_state_machine.png` in `reports/kouun-rokku/week-05/`.

## Dependencies and remaining acceptance

Base: main `e487e97`. Config tunables for `[pursuit]` and `[hold]` in `config.toml` respect Single Source of Truth (`[thresholds]`).
Physical hardware trials on the real JetBot with DQK scheduled for Week 6 classroom session (2026-11-09).

Reviewer: HNHL (review rotation: KR's PRs -> HNHL). DQK completed preliminary technical reviews.
