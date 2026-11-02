# W5: Hold detector, pursuit/hold controllers, vendored ByteTrack, and Mid-Term Report drafts

## Behavior

Add `HoldDetector` (`sentry/nav/hold_detector.py`) for target ground-speed tracking in the world coordinate frame: projects local target observations $(x_f, y_l)$ to $(X_w, Y_w)$ via robot dead-reckoned unicycle pose $(x_r, y_r, \theta_r)$. World velocity $(v_{x,w}, v_{y,w})$ is estimated via ordinary least-squares linear regression over a 0.5 s window, eliminating high-frequency detector jitter. Triggers `TARGET_STATIONARY` (state `HOLD`) when $v_{\text{target}} < 0.1\text{ m/s}$ for $> 2.0\text{ s}$; enforces a hysteresis band $[0.1, 0.2]\text{ m/s}$ and triggers `TARGET_MOVING` (state `PURSUE`) only when $v_{\text{target}} > 0.2\text{ m/s}$. The core invariant "robot yawing alone never triggers hold" is strictly satisfied: target motion in the world is decoupled from robot angular velocity.

Add `PursuitController`, `HoldController`, and `InterceptionController` (`sentry/nav/controllers.py`):
- `PursuitController`: PD distance control maintaining $1.2\pm 0.2\text{ m}$ standoff and PD yaw centering. Foreground obstacle override adds repulsive deflection ($w_{\text{avoid}} = 0.45\text{ rad/s}$) when $d_{\text{obs}} < 0.5\text{ m}$ and cuts forward velocity ($v \le 0$) when $d_{\text{obs}} < 0.35\text{ m}$.
- `HoldController`: Strictly zero translation ($v = 0.0$), yaw-only PD recentering without orbiting (preventing target from escaping camera FOV). Centers target within $\pm 10\%$ frame width within $1.5\text{ s}$.
- `InterceptionController`: Closed-loop coordinator mapping `HoldDetector` events to `StateMachine` actions.

Vendor original ByteTrack (`third_party/bytetrack/`): pure NumPy/SciPy implementation (`scipy.optimize.linear_sum_assignment`), eliminating compiled C++ `lap` dependencies. Verified Python 3.6 AST syntax compatibility (`ast.parse`) with zero `sentry.*` imports. Drop-in backend `VendoredByteTrackBackend` in `sentry/perception/tracker.py` achieves 100.0% ID agreement (294/294 matches) against Ultralytics ByteTrack on multi-track scenarios.

Add closed-loop simulation (`tools/sim_pursuit_hold.py`) driving `SimRobot` unicycle kinematics at 50 Hz with moving targets, stopping events, and obstacles.

Draft Mid-Term Report chapters owned by KR (`midterm-chapter-01.md`, `02.md`, `06.md`, `07.md`, `appendix-a.md`) and generate Figures F12, F15, F16.

## Validation

- Full CPU test suite: **597 passed, 5 skipped, 4 deselected in 23.52s**. Log: `reports/kouun-rokku/week-05/pytest.log`.
- Python 3.6 AST validation: all files in `third_party/bytetrack/` pass `ast.parse(..., feature_version=(3, 6))` with zero `sentry.*` or `dataclasses` imports.
- ByteTrack parity evaluation: `python -m tools.evaluate_bytetrack_parity --out reports/kouun-rokku/week-05/bytetrack_parity.json` $\rightarrow$ **100.0% ID agreement** (294/294 matches) vs $\ge 95\%$ target $\rightarrow$ **PASS**.
- Hold detector metrics: `python -m tools.evaluate_hold_detector --out reports/kouun-rokku/week-05/hold_detector_metrics.json` $\rightarrow$ Dwell time trigger $2.05\text{ s}$, hysteresis band maintained, 0 false hold triggers under robot yaw $\rightarrow$ **PASS**.
- Closed-loop simulation: `python -m tools.sim_pursuit_hold --out reports/kouun-rokku/week-05/sim_pursuit_hold.json` $\rightarrow$ $100.0\%$ centering, dwell met at $t=6.34\text{ s}$, zero translation, hysteresis exit at $t=8.26\text{ s}$ $\rightarrow$ **PASS**.
- Figures generated: `F12_entrance_bakeoff.png`, `F15_dead_reckoning_aruco.png`, `F16_state_machine.png` in `reports/kouun-rokku/week-05/`.

## Dependencies and remaining acceptance

Base: main `e487e97`. Config tunables for `[pursuit]` and `[hold]` added to `config.toml`.
Physical hardware trials on the real JetBot with DQK scheduled for Week 6 classroom session (2026-11-09).

Reviewer: HNHL (review rotation: KR's PRs -> HNHL).
