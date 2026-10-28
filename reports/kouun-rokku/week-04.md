# Week 04 – kouun-rokku (2026-10-26 to 2026-11-01)

*Focus: Intruder FIFO target queue (`sentry/app/target_queue.py`), departure sector classification from 2.0 s horizontal bounding-box drift (`sentry/perception/sector.py`, `tools/evaluate_sector_accuracy.py`), end-to-end Phase 2 monitoring replay on D2 (`sentry/app/phase2_pipeline.py`, `tools/replay_phase2.py`), and T0/T1 verification tests.*

## Done

- **Intruder Target FIFO Queue (`sentry/app/target_queue.py`, `tests/test_target_queue.py`):**
  - Implemented `IntruderRecord` dataclass storing intruder ID, normalized 512D face embedding (InsightFace/MobileFaceNet), 512D appearance vector ($\vec{a}_{\text{target}}$ from OSNet), departure sector (`"left"`, `"center"`, `"right"`, `"unknown"`), snapshot path, timestamp, and status tracking (`queued`, `active`, `completed`, `dropped`).
  - Implemented `TargetQueue` thread-safe FIFO queue with `push`, `pop`, `peek`, `active_target`, `complete_active`, and `drop_active` (for unlocated intruders during coverage search, `Project Specification.md` §4.6 step 5).
  - Added JSON serialization and state machine event bridge (`to_state_machine_event`), ensuring strict validation (512-dim unit vector normalization, finite timestamps, valid sectors).
- **Departure Sector Logging from Bounding-Box Drift (`sentry/perception/sector.py`, `tools/evaluate_sector_accuracy.py`, `tests/test_sector.py`):**
  - Implemented `DepartureSector`, `SectorConfig`, `SectorTracker`, and `classify_sector` according to `Project Specification.md` §4.6 and `Implementation Plan.md` §4.3.
  - Measures horizontal bounding-box displacement $\Delta x = x_{\text{end}} - x_{\text{start}}$ over up to 2.0 s observation window in ESP32-CAM coordinates.
  - Classifies into Left ($\Delta x < -0.08$), Center ($|\Delta x| \le 0.08$), and Right ($\Delta x > +0.08$) using robust median start/end smoothing and least-squares drift estimation to eliminate single-frame detector jitter.
  - Supports both streaming frame updates (`SectorTracker.update`) and batch trajectory classification (`classify_sector`), with auto-detection for normalized $[0, 1]$ or pixel coordinates.
  - Evaluated on 300 benchmark trajectories across varying speeds, noise, and durations: achieved **99.67% accuracy** (exceeding the $\ge 90\%$ T1 requirement).
- **End-to-End Phase 2 Replay Pipeline on D2 (`sentry/app/phase2_pipeline.py`, `tools/replay_phase2.py`, `tests/test_phase2_replay.py`):**
  - Built `Phase2Pipeline` connecting the complete access-control monitoring loop:
    $$\text{ESP32-CAM stream} \rightarrow \text{FaceVerifier} \rightarrow \text{OSNet Appearance} \rightarrow \text{SectorTracker} \rightarrow \text{TargetQueue} \rightarrow \text{StateMachine}$$
  - Whitelisted entries ($\text{score} \ge 0.45$) are authorized and logged; robot remains in `STANDBY`.
  - Unregistered individuals ($\text{score} < 0.45$) trigger intruder detection $\rightarrow$ extract OSNet re-ID embedding $\rightarrow$ log departure sector $\rightarrow$ push to `TargetQueue` $\rightarrow$ dispatch `INTRUDER_QUEUED` event to `StateMachine`.
  - Robot transitions from `STANDBY` to `PURSUE`, emits commands with `play="intruder_detected"` and actions `("engage_target", "pursue_target")`. Subsequent intruders arriving during active interception are queued into `TargetQueue` without disrupting pursuit.
  - Integrated target exit and handoff (`TARGET_EXITED` $\rightarrow$ `SEARCH` $\rightarrow$ `TARGET_FOUND` / `SEARCH_EXHAUSTED` drop $\rightarrow$ next queued target).
  - Executed full 30-entry D2 leave-one-out replay with DQK and HNHL: **0 false accepts, 0 false rejects, 10/10 intruders queued, 100.0% sector accuracy**.

## Tests run

| Tier | Command | Result | Evidence |
| :-- | :-- | :-- | :-- |
| T0 | `pytest tests/test_target_queue.py tests/test_sector.py tests/test_phase2_replay.py` | 21/21 passed (FIFO ordering, validation, streaming tracker, thread safety, end-to-end replay) | `reports/kouun-rokku/week-04/pytest.log` |
| T1 | `python3 -m tools.evaluate_sector_accuracy` | **99.67 %** accuracy on 300 benchmark trajectories (Left 99.0 %, Center 100.0 %, Right 100.0 %) vs $\ge 90.0 \%$ threshold $\rightarrow$ **PASS** | `reports/kouun-rokku/week-04/sector_accuracy.json` |
| T1 | `python3 -m tools.replay_phase2` | 30/30 entries correctly processed on D2 leave-one-out replay (20 authorized, 10 intruders queued, 0 FA / 0 FR, **100.0 %** sector accuracy) $\rightarrow$ **PASS** | `reports/kouun-rokku/week-04/phase2_replay_summary.json` |

## Acceptance criteria status (Implementation Plan §4.3)

- **Target Queue FIFO (`app/target_queue.py`):** Verified FIFO order, 512D unit embedding validation, snapshot path storage, and unlocated intruder drop logic $\rightarrow$ **Pass (T0)**.
- **Sector logging (optional search prior):** Achieved **99.67 %** classification accuracy on synthetic and D2 entrance walk trajectories vs the required $\ge 90.0 \%$ threshold $\rightarrow$ **Pass (T1)**.
- **Phase 2 end-to-end replay on D2:** Complete monitoring pipeline runs cleanly from replayed frames to face verification, OSNet appearance vector extraction, sector logging, FIFO queueing, and state machine transition into pursuit $\rightarrow$ **Pass (T0 / T1)**.

## Blockers / risks

- **OSNet Live Inference on Robot:** OSNet feature extraction on the Jetson Nano (Extra Stage B) requires PyTorch/TensorRT model export verification by HNHL and DQK; CPU pipeline on laptop runs completely offline and verified.
- **Mid-Term Report Outline:** Agree on chapter page allocations and chapter drafts with DQK and HNHL by Mon Nov 2 (KR owns Chapters 1, 2, 6, 7 and Appendix A).

## Next week (Week 5)

- Implement target ground speed hold detector in world coordinates ($v_{\text{target}} < 0.1\text{ m/s}$ for $> 2.0\text{ s}$ $\rightarrow$ `HOLD`; exit when $> 0.2\text{ m/s}$) with robot rotation compensation.
- Implement HOLD behavior (zero translation, yaw-only PD tracking bbox center without orbit).
- Vendor ByteTrack tracker into `third_party/bytetrack/` for Python 3.6 Jetson compatibility.
- Draft Mid-Term Report chapters from Week 1-4 experimental evidence.
