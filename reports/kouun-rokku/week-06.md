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
  - **Motor Dead-Zone Projection:** Enforces JetBot physical motor dead zone ($\text{dead} = 0,40$):
    * In `HOLD`, commands are strictly $v = 0,0$ with $|w| \ge 0,45$ or full stop $(0, 0)$ when centered $\pm 10\%$.
    * In active drive, projects $(v, w)$ so that the inner wheel never falls below $\text{dead}$ after differential mix normalization: $|w| \le \frac{1 - \text{dead}}{1 + \text{dead}} |v| = 0,428 |v|$. All emitted commands pass `legal()`.
- **Closed-Loop Replay Tool (`tools/replay_phase3.py`):**
  - Replays closed-loop Phase 3 multi-target scenario against `SimRobot`: T1 pursuit, dwell trigger at $t=6,32\text{ s}$, standoff hold with zero translation, T2 FIFO queue stacking, hysteresis exit at $t=8,26\text{ s}$, strike evasion pulse, and two-target sequential handoff upon exit.
  - Evaluates metrics and outputs structured JSON summary to `reports/kouun-rokku/week-06/phase3_replay_summary.json`.
- **Unit Tests for Phase 2 $\rightarrow$ Phase 3 Event Chain (`tests/test_phase3_runner.py`):**
  - Added 8 comprehensive unit tests covering: standby monitoring, intruder activation, stationary dwell trigger, yaw recentering within tolerance, hysteresis exit, multi-target queue sequencing, strike evasion pulse, and obstacle repulsion.
- **Mid-Term Report Editor Consolidation (`reports/midterm_report_draft.md`, `tools/check_midterm_page_budget.py`):**
  - Merged chapter drafts across all members: KR (Ch 1, 2, 6, 7, Appendix A), HNHL (Ch 5, Ch 7 rows, Appendix inputs), and DQK outlines (Ch 3, 4, 8, section 5.x).
  - Developed audit tool `tools/check_midterm_page_budget.py`: verified **5.591 words**, estimated **12,4 trang** (chuẩn hóa nằm trong dải quy định 10–15 trang).
  - Tracked 6 canonical figures (F1, F9, F10, F12, F13, F15) and 15 verified citations.

## Tests run

| Tier | Command | Result | Evidence |
| :-- | :-- | :-- | :-- |
| T0 | `pytest tests/test_phase3_runner.py` | 8 passed (intruder queued deploy, hold dwell trigger, hold zero translation, hysteresis exit, multi-target FIFO handoff, strike evade pulse, obstacle deflection, 100% legal commands) | `reports/kouun-rokku/week-06/pytest.log` |
| T0 | `pytest -m "not gpu and not hil"` | **625 passed, 5 skipped, 4 deselected** (full CPU test suite clean, 0 regressions) | `reports/kouun-rokku/week-06/pytest.log` |
| T0 | `python -m tools.replay_phase3 --out reports/kouun-rokku/week-06/phase3_replay_summary.json` | Dwell trigger $t=6,32\text{ s}$, zero translation verified, recenter time $0,26\text{ s} \le 1,5\text{ s}$, hysteresis exit $t=8,26\text{ s}$, 2 targets completed, 0 illegal commands $\rightarrow$ **PASS** | `reports/kouun-rokku/week-06/phase3_replay_summary.json` |
| T0 | `python -m tools.check_midterm_page_budget --file reports/midterm_report_draft.md` | Total words: 5.591, estimated pages: **12,4 pages** (target 10–15 pages), 9 chapters complete $\rightarrow$ **PASS** | `reports/midterm_report_draft.md` |

## Acceptance criteria status (Implementation Plan §4.3)

- **Phase 2 $\rightarrow$ Phase 3 Event Chain (`sentry/app/phase3_runner.py`):** Verified `INTRUDER_QUEUED` deploys robot; multi-target queue handles concurrent entrants without disrupting active pursuit; `TARGET_EXITED` hands off to next target $\rightarrow$ **Pass (T0 / Simulation)**.
- **Standoff Hold (`sentry/nav/controllers.py`, `sentry/app/phase3_runner.py`):** Verified dwell time trigger $\approx 2,0\text{ s}$; zero translation ($v=0,0$ strictly); recenter time $0,26\text{ s} \le 1,5\text{ s}$; commands overcome motor dead zone ($0,40$) $\rightarrow$ **Pass (T0 / Simulation; physical robot tuning with DQK pending classroom session)**.
- **Mid-Term Report Draft:** Merged full draft (Ch 1–8 + Appendix A) with page budget audit (12,4 pages vs 10–15 pages target) $\rightarrow$ **Ready for team review**.

## Blockers / risks

- **Hardware Validation of Pursuit + Hold:** Real-robot tuning of pursuit PD and standoff hold gains on JetBot with DQK scheduled for the upcoming classroom session.
- **Robot Camera Replacement:** Robot camera status and tilt recalibration pending resolution with DQK.

## Next week (Week 7)

- Final review of merged Mid-Term Report with DQK and HNHL; integrate DQK's final figures and measurements.
- Prepare clean-checkout validation package for `midterm` git tag.
