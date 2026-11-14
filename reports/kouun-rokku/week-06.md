# Week 06 – kouun-rokku (2026-11-09 to 2026-11-15)

*Focus: Wiring PURSUE/HOLD states in State Machine to HoldDetector and closed-loop controllers (`sentry/app/phase3_runner.py`), multi-target queue handoff, Phase 2 -> Phase 3 event chain verification (`tests/test_phase3_runner.py`), full closed-loop replay tool (`tools/replay_phase3.py`), and Mid-Term Report editor consolidation (`reports/midterm_report_draft.md`, `tools/check_midterm_page_budget.py`).*

## Done

- **Phase 3 Interception Runner (`sentry/app/phase3_runner.py`):**
  - Implemented `Phase3Runner` and `Phase3Settings` bridging `StateMachine` (`sentry/app/state_machine.py`), `InterceptionController` (`sentry/nav/controllers.py`), and `TargetQueue` (`sentry/app/target_queue.py`).
  - **Deterministic State Transition Wiring:**
    * When in `STANDBY`, receiving `INTRUDER_QUEUED` activates target and triggers deployment $\rightarrow$ `PURSUE`, dispatching audio prompt `intruder_detected`.
    * During `PURSUE`, target ground speed is continuously estimated by `HoldDetector` with unicycle world compensation. When $v_{\text{target}} < 0,1\text{ m/s}$ for $> 2,0\text{ s}$, dispatches `TARGET_STATIONARY` $\rightarrow$ transitions `PURSUE` to `HOLD` and plays `hold_position`.
    * During `HOLD`, translation is strictly zero ($v = 0,0$, no orbiting), and yaw-only recentering turns target to center.
    * When target accelerates past $0,2\text{ m/s}$ (hysteresis exit), dispatches `TARGET_MOVING` $\rightarrow$ resumes `PURSUE`.
    * If target lunges (`STRIKE`), preempts active pursuit/hold into `EVADE` with an evasive reverse pulse ($v=-1,0$) steering away from the obstacle for 400 ms, then auto-resumes `PURSUE`.
    * Upon `TARGET_EXITED`, completes active intruder, pops next target from FIFO `TargetQueue` $\rightarrow$ searches and resumes pursuit. When queue is empty, returns cleanly to `STANDBY`.
  - **Target Observation Freshness & Identity Separation:**
    * Separates control ticks from observation updates. `HoldDetector` / dwell timer is strictly updated only upon genuine new target observations (qua `step(target_pos=...)` hoặc `observe_target(...)`, mỗi timestamp chỉ dùng một lần).
    * Enforces freshness contract (`obs_freshness_timeout_s = 0,25\text{ s}`): when an observation goes stale, motor commands safely drop to $(0, 0)$ instead of driving towards phantom positions.
    * In `HOLD`, when observation gap exceeds `target_lost_timeout_s = 1,0\text{ s}`, cleanly releases `HOLD` via `TARGET_MOVING` back to `PURSUE`.
    * On target handoff (or active identity change), observation caches, dwell timer, filter history, and controllers are immediately reset; requires a fresh observation associated with the new target before pursuit.
  - **Piecewise Motor Dead-Zone Projection (`project_legal_command`):**
    * Satisfies JetBot physical motor dead zone ($\text{dead} = 0,40$):
      - In `HOLD`, commands are strictly $v = 0,0$ with $|w| \ge 0,45$ or full stop $(0, 0)$ when centered $\pm 10\%$.
      - In active drive, accounts for differential mixing across both unscaled regime ($|w| \le |v| - \text{dead}$) when $|v| \le \frac{1 + \text{dead}}{2}$ and saturated normalized regime ($|w| \le \frac{1 - \text{dead}}{1 + \text{dead}} |v|$) when $|v| > \frac{1 + \text{dead}}{2}$.
      - Re-verifies legality via `legal()` and fails safe to zero $(0, 0)$ if any boundary edge case occurs. Finite inputs are projected and rechecked; NaN/±Inf stop before saturation. Validation covers the finite grid and nonfinite regressions below.
- **Closed-Loop Replay Tool (`tools/replay_phase3.py`):**
  - Replays closed-loop Phase 3 multi-target scenario against `SimRobot`: T1 pursuit, dwell trigger at $t=6,32\text{ s}$, standoff hold with zero translation, T2 FIFO queue stacking, hysteresis exit at $t=8,26\text{ s}$, strike evasion pulse, and two-target sequential handoff upon exit.
  - Evaluates metrics and outputs structured JSON summary to `reports/kouun-rokku/week-06/phase3_replay_summary.json`.
- **Unit Tests for Phase 2 $\rightarrow$ Phase 3 Event Chain (`tests/test_phase3_runner.py`):**
  - Expanded suite to 26 comprehensive unit tests, adding regression coverage for review items: single-observation disappearance without false hold, FIFO identity handoff cache reset, handoff while T1 in HOLD with unseen T2, recovery of known case $(0,55, 0,30)$, and exhaustive 441-point input sweep across custom explore settings.
- **Mid-Term Report Consolidation & Honest Audit (`reports/midterm_report_draft.md`, `tools/check_midterm_page_budget.py`):**
  - Reconciled consolidated Chapter 5 with HNHL primary evidence: D5 307/90 same-session dev-val, Wire recall 0,000, 8/9 chair distance points, Face TAR 82,99% with FAR 46,40% non-acceptance, ByteTrack Python 3.6 backend parity (non-person identity), and RTX 5060 sequential workload profiling caveats.
  - Repaired 5 broken local Markdown image paths (F1, F15, F10, F13, F9_gpu.png).
  - Upgraded audit tool `tools/check_midterm_page_budget.py`: verified **6162 words**, estimated **13,7 trang** (nằm trong dải quy định 10–15 trang), validates 9/9 required chapters, verifies existence of all 6 image assets, and scopes rendered compliance honestly as an estimate.

## Tests run

| Tier | Command | Result | Evidence |
| :-- | :-- | :-- | :-- |
| T0 | `pytest tests/test_phase3_runner.py` | **13 passed** (deploy, dwell, hold zero-translation, hysteresis exit, FIFO handoff, strike evade, repulsion, single-sample disappearance, handoff cache reset, handoff in hold, v=0.55 w=0.3 projection, 441-point legality sweep) | `reports/kouun-rokku/week-06/pytest.log` |
| T0 | `pytest -m "not gpu and not hil"` | **630 passed, 5 skipped, 4 deselected** (full CPU test suite clean, 0 regressions) | `reports/kouun-rokku/week-06/pytest.log` |
| T0 | `python -m tools.replay_phase3 --out reports/kouun-rokku/week-06/phase3_replay_summary.json` | Dwell trigger $t=6,32\text{ s}$, zero translation verified, recenter time $0,00\text{ s} \le 1,5\text{ s}$, hysteresis exit $t=8,26\text{ s}$, 2 targets completed, 0 illegal commands $\rightarrow$ **PASS** | `reports/kouun-rokku/week-06/phase3_replay_summary.json` |
| T0 | `python -m tools.check_midterm_page_budget --file reports/midterm_report_draft.md` | Total words: 6162, estimated pages: **13,7 pages** (target 10–15 pages), 9/9 chapters complete, 6/6 assets verified $\rightarrow$ **PASS** | `reports/midterm_report_draft.md` |

## Acceptance criteria status (Implementation Plan §4.3)

- **Phase 2 $\rightarrow$ Phase 3 Event Chain (`sentry/app/phase3_runner.py`):** Verified `INTRUDER_QUEUED` deploys robot; multi-target queue handles concurrent entrants without disrupting active pursuit; `TARGET_EXITED` hands off to next target $\rightarrow$ **Pass (T0 / Simulation)**.
- **Standoff Hold (`sentry/nav/controllers.py`, `sentry/app/phase3_runner.py`):** Verified dwell time trigger $\approx 2,0\text{ s}$; zero translation ($v=0,0$ strictly); recenter time $0,26\text{ s} \le 1,5\text{ s}$; commands overcome motor dead zone ($0,40$) $\rightarrow$ **Pass (T0 / Simulation; physical robot tuning with DQK pending classroom session)**.
- **Mid-Term Report Draft:** Merged full draft (Ch 1–8 + Appendix A) with page budget audit (13,7 pages vs 10–15 pages target) $\rightarrow$ **Ready for team review**.

## Blockers / risks

- **Hardware Validation of Pursuit + Hold:** Real-robot tuning of pursuit PD and standoff hold gains on JetBot with DQK scheduled for the upcoming classroom session.
- **Robot Camera Replacement:** Robot camera status and tilt recalibration pending resolution with DQK.

## Next week (Week 7)

- Final review of merged Mid-Term Report with DQK and HNHL; integrate DQK's final figures and measurements.
- Prepare clean-checkout validation package for `midterm` git tag.

## PR #101 re-review fixes — 2026-11-14

The latest validation supersedes the historical test counts above: **754 passed,
5 skipped, 4 deselected** on the merged-main tree. The Phase 3/controller/hold/
state-machine/queue selection passed **71 tests**, including 26 Phase 3 tests.
Details, Linux test launcher and remaining report limitations:
[review fixes](week-06/pr101-review-fixes.md). The page estimate and asset count
above were refreshed from [the current audit](week-06/pr101-page-audit.json);
rendered page compliance remains unverified.
