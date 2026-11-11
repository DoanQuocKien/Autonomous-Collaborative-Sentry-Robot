### Week 6 (Nov 9-15): Pursuit + Hold on the Robot, Model Optimization

- **DQK**
  - Pursuit and hold on the robot: final gains, T2 pursuit PD and standoff hold protocols.
  - Chain Phase 2 -> Phase 3: `INTRUDER_QUEUED` -> deploy -> pursue -> hold, driven by the state machine.
  - Record the robot shots of the demo video (`Mid-Term Report Plan.md` section 5).
  - Tests: T2 pursuit PD and standoff hold (section 4.3 thresholds).
- **HNHL**
  - Model optimization for the report: FP16 (and TensorRT if it installs cleanly) vs FP32 for YOLOv8n and OSNet on the RTX 4050: latency, VRAM, accuracy change on D1/D2. Keep FP32 if accuracy drops.
  - Laptop screen recordings of the perception overlays for the video.
  - Tests: T1 (gpu) before/after optimization, same protocol as `tools.gpu_baseline`.
- **KR**
  - State machine: PURSUE/HOLD wired to the hold detector and the controller commands; Phase 1-3 transitions replayed from logged events.
  - Report editor: merge the chapter drafts, check the page budget, start the code appendix.
  - Tests: T0 for the Phase 2 -> Phase 3 event chain.
- **Extra (proposed):** DQK refreshes figures F20 and F21 (`Mid-Term Report Plan.md` section 3) with a person in view, the door thread and a battery run, and writes the 'Optimization and on-device deployment' section of chapter 5 with HNHL's laptop FP32 against FP16 numbers beside the robot's; figures frozen Mon Nov 16. No new edge features.
- **Carried over from Weeks 4-5, NOT done (snapshot 2026-11-08, DQK; the classroom session of 11-09 is pushed to next week, so this all lands on top of the Week 6 plan above):**
  - **Classroom, graded:** T2 deployment, 5th counted run and a rerun with the board-loss fix (4 of 5 counted); Part C (`deploy_live --door`, never run on the robot); handshake retest with the live rule (7/10 and 9/10 earlier, plan needs 10/10 and 10/10); Phase 2 live at the door (ESP32 -> face -> re-ID -> queue); pursuit PD and standoff hold protocols (only first supervised live runs exist: no step response, hold timing, hold exit or re-centring time); obstacle detector retest on the glossy floor and the G2 decision (Stage A never built); the Phase 2 -> Phase 3 chain on the robot.
  - **Calibration, classroom floor:** a clean `motion_check` at full battery (turns left/right n >= 10, speed at 0.55 and 0.75, reverse speed, video lag with `t_cap`); validate the bearing-based rest heading (unvalidated); `self_pose` before every run (the camera pitch drifted 3.6 deg by itself on 11-08, cause not found).
  - **Home / laptop:** the R1-release stop trial (the 0.35 s link-cut limit is not demonstrated: 0.48-0.52 s upper bounds); rehearsals (`deploy_live --no-robot`, robot dry run); PR #99 (HNHL's remaining findings: config into the controller, centring units and time basis, command-based pose integration, main-path fault-injection tests), reviews of #99, #100 and #102; tell the supervisor about the camera damage and repair; the Week 6 log with hours (Sun 11-15).
  - **Team items:** HNHL D3 reviewed tracking and re-ID protocol (needs a `tools.record` -> `track_replay` manifest converter, offered, not written; >= 60 s two-person scenes, >= 5 identities), FP16 vs FP32 numbers, overlay recordings; KR PURSUE/HOLD wiring and Phase 1-3 replay, the 3-consecutive handshake rule concern, door pictures and the ESP32 view, report editor.
  - **Report (DQK):** figures F3, F7 (video latency CDF), F8, F11, F14, F17 (pursuit distance and bbox error against time), F18; refresh F20/F21 with a person in view; the 'Optimization and on-device deployment' section of chapter 5; my chapters (3, 4, 8 final in Week 7); the demo video robot shots (entrance found, sweet spot, prompt, camera placed, verified, standby, Phase 2, pursuit) and the cut by Wed 11-18.
  - **Unresolved questions to write up honestly:** why the camera pitch drifts (the repaired FPC socket is a guess); sup3 zero marker fixes; board-loss causes in t2_3 to t2_5; MPU6050 faulty and postponed.
- **Session (Mon Nov 16, classroom):** T2 pursuit + hold; pick-up shots for the video. **Milestone:** experiments for the mid-term closed and figures frozen (T-7 days). Anything not working by now goes into the report as "in progress" with its plan; it is not rushed.


| D5 | W3 (collection), grows with every session | DQK records, all three label | **Floor-level objects from the robot's own camera (lens 0.10 m): legs and feet, wires (black, white, straight, curled), footwear, backpacks, bags, plus furniture and empty-floor negatives (20 %).** At least 150 labelled images per class, the glossy presentation floor (matte dropped 2026-11-08), 2+ rooms, 3+ lighting conditions, 0.3-1.5 m; one whole session kept out of training for the T1. Stays in `data/`; people's legs only with consent and no faces in frame |
