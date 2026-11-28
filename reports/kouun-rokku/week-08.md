# Week 08 — kouun-rokku (2026-11-23 to 2026-11-29)

*Issue #139 prerequisites before the Thu 2026-11-26 classroom session (D4 + D3): D4 keypress onset labeller (`tools/label_events.py`), false-trigger evaluation harness (`sentry/app/strike_eval.py`, `tools/evaluate_strike_false_triggers.py`), EVADE + cooldown state-machine/runner verification and PR #138 follow-ups.*

## Done

- **D4 Keypress Event Labeller (`tools/label_events.py`, `tests/test_label_events.py`):**
  - Cross-platform single-keypress labeller (Windows `msvcrt`, POSIX `termios`/`tty` cbreak, plus stdin fallback) designed to run on the same laptop alongside `python -m tools.record D4 --no-esp32`.
  - Records `t_local` (`time.time()`, matching `jetbot_meta.jsonl`), `t_local_iso`, and `t_perf` (`time.perf_counter()`), and retains `t_local` (raw press time) and `refined_t_local` as two separate columns per `docs/Lunge Protocol.md` §7.
  - Supports `Space`/`Enter`/`l` (`lunge` onset in active Set A..F), `c` (`clap` sync marker), `n`/`h` (`neg_start`/`neg_end` and `hard_neg_start`/`hard_neg_end`), `1`..`6` / `a`,`b`,`d`,`e`,`f`,`C` (set switch), and `x`/`u` (invalidate last lunge). Flushes atomically to CSV on every keypress.
  - Post-recording helpers: `--summary`, `--shift-refined <offset_s>`, `--align <jetbot_meta.jsonl>` (nearest-frame matching with `dt_ms`), and optional `--review <data_dir>` frame scrubber.

- **False-Trigger Harness (`sentry/app/strike_eval.py`, `tools/evaluate_strike_false_triggers.py`, `tests/test_strike_false_triggers.py`):**
  - Evaluates false triggers per minute and per 5 min against the acceptance target (`<= 1` false trigger / 5 min of walking, `Implementation Plan.md` §4.3), gating detections through both `StateMachine` (`EVADE` + `evade_cooldown_s = 1.0`) and `EvasionOverride` from `config.toml`.
  - Works with precomputed predictions JSONL, `label_events.py` CSV negative intervals / onset exclusions, or any pluggable `--detector module:callable` (ready for `sentry/perception/pose.py`), and includes a timestamp-windowed `BboxStrikeBaseline` (`dA/A > 0.40` within `0.10 s`) and synthetic 10-min walking benchmark (`--synthetic`) for T0 testing.
  - Also evaluates labeled lunge onset recall and detection delay (`evaluate_onsets`) when D4 onset labels are provided.

- **EVADE State + Cooldown Hardening & PR #138 Follow-ups:**
  - `sentry/app/phase3_runner.py`: prevented ignored `STRIKE` events (during `EVADE` or cooldown) from overwriting `self._evade_w`, and reset `self.controller` on transition into `State.EVADE` so pre-strike `HOLD` state does not carry over after the evasion pulse.
  - `sentry/nav/evasion.py`: added `math.isfinite` validation (catching `NaN`/`inf` `cooldown_s`) and `threading.RLock()` around state transitions.
  - `tools/pursue_live.py`: bypassed `evasion.step()` once `end["reason"]` is set during shutdown.
  - Added T0 tests in `tests/test_state_machine.py`, `tests/test_phase3_runner.py`, and `tests/test_evasion.py`.

- **Stage A CPU-Only Obstacle Layer & Laptop Fallback Switch (`jetson/obstacle_layer.py`, `sentry/app/edge_fallback.py`, `tests/test_jetson_obstacle_layer.py`):**
  - Implemented `EdgeCameraModel`, `repulsive_w`, `EdgeObstacleLayer`, `FallbackSwitch`, `decode_raw_yolo`, and edge status wire helpers in Python 3.6 using **stdlib and numpy only** (AST-verified `feature_version=(3, 6)`, zero `cv2` / `sentry` imports).
  - Equidistant fisheye Newton-Raphson undistortion and ground-plane projection match OpenCV `CameraGeometry` within `< 1e-4` relative distance error (`calib/camera.json` + `calib/camera_pose_nowedge.json`), well inside the 2 percentage-point Stage A parity target.
  - `decode_raw_yolo` (`process_raw` / `step_raw`) uses class-aware NMS (`iou=0.7`, `max_det=300`, coordinate clipping) matching `tools/stage_a_parity.py::decode` (resolving HNHL's `W8-STAGE-A-PARITY.md` note on legacy `yolo_post.decode`).
  - `FallbackSwitch` + `EdgeFallbackController` enforce laptop takeover within `<= 1.0 s` (`timeout_s = 0.5 s`) on edge switch-off, error, non-finite command, or silence, while keeping all motor commands dead-zone-legal.

- **Cross-PR Integration Fixes (post PR #142/#143):**
  - `tools/label_events.py`: clarified docstring key hint (`1..6` or `a,b,d,e,f,C`, since `c` is `clap`, addressing DQK's PR #142 review nit).
  - `sentry/app/strike_eval.py`: ensured an explicit `--detector` callable (e.g. `sentry.perception.pose:LungeDetector`) always overrides any precomputed `"strike"` column, and reset `BboxStrikeBaseline` across epoch/timestamp resets; verified end-to-end against `LungeDetector` on `tools/detect_lunges.py` JSONL format in `tests/test_strike_false_triggers.py`.

## Tests & Evidence Run

| Tier | Command | Result | Evidence |
| :--- | :--- | :--- | :--- |
| T0 | `.venv/bin/python -m pytest -q tests/test_label_events.py tests/test_strike_false_triggers.py tests/test_jetson_obstacle_layer.py tests/test_stage_a_parity.py tests/test_pose.py tests/test_detect_lunges.py` | **65 passed** | `reports/kouun-rokku/week-08/cpu_tests.log` |
| T0 | `.venv/bin/python -m tools.evaluate_strike_false_triggers --synthetic --out reports/kouun-rokku/week-08/strike_false_trigger_harness.json` | **PASS** (10 min synthetic walking: 0 false triggers/5 min; cooldown gating: 2/4 accepted, 2 suppressed; synthetic burst recall 3/3) | `reports/kouun-rokku/week-08/strike_false_trigger_harness.json` |
| T0 | `.venv/bin/python -m tools.run_cpu_tests` | **1077 passed, 3 skipped, 4 deselected** in 50.66 s | `reports/kouun-rokku/week-08/cpu_tests.log` |

*Scope note: all results above are T0 CPU/synthetic checks. Real D4 T1 false-trigger rate, recall, and reaction-time measurements await the Thu 2026-11-26 classroom recording and HNHL's `sentry/perception/pose.py`; Stage A T2 on-robot engine integration and disconnect safety tests await DQK on the robot before Gate G2 (Sun 2026-11-29).*
