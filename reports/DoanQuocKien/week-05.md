# Week 05 - DoanQuocKien (2026-11-02 to 2026-11-08)

*Written Sunday 2026-11-08 evening. Evidence: `reports/DoanQuocKien/week-05/` (F15 on main; the home session folder `home_1107/` is on PR #99). Numbers as measured, not rounded up.*

## Done
- **Reviews and merges:** reviewed #88-#91, #93 (twice), #95 (approved, merged), #97 (approved, merged); #94 (F15) and #96 (session checklists) merged; #98 (Week 5 leftovers) merged on 11-05 after HNHL's review found a `NameError` that I had introduced (removed `servo_motion` took its constants line with it; would have aborted the next supervised run) - fixed and regression-tested.
- **Board-loss fallback** in `deploy_runner` (#90): when the servo board is lost the runner spins towards the last bearing.
- **MPU6050:** installed 2026-11-01, faulty on 11-02/03, postponed again; plan and notes changed (not used).
- **F15 redrawn from the real runs** (#94): the first version was a simulated curve presented as measured (KR's); replaced by end poses and tape offsets only.
- **Report figures from existing evidence** (#98): F1, F2, F4, F5, F6, F19, F20, F21 (`tools/plot_dqk_report_figures.py`).
- **Leftover tool work** (#98): stop margin, `tape_answers`, `--answers` validation, handshake and frame logs, operator prompts, 11.4 V gate, bearing-based rest heading in `motion_check` (**unvalidated**: replaying class_2 gave the same ratios).
- **Session checklists** for the home session and the Week 6 classroom (`docs/Home Session Checklist 2026-11-04.md`, `docs/Classroom Tasks Week 6.md`); plan fitted to the lateness (G2 not met, Stage A never started, tasks moved to Week 6).
- **Robot camera damaged and repaired (2026-11-05):** the 15-pin flat-cable socket tore off the camera board (boot log probe error -121, no `/dev/video0`); a repair shop resoldered it the same day, free. After it: stream about 19 fps, no module replaced, calibration file still used. The supervisor has NOT been told yet; return checklist updated.
- **Live pursuit runner `tools/pursue_live`** (PR #99, open, HNHL requested changes twice): detector + ByteTrack + foot-point distance + `InterceptionController` + UDP with the R1 interlock. Fixes made because of the runs: detector warm-up before R1, slow frames never driven on, yaw-only turns as one-frame pulses with a centre dead band, sender-side pulse expiry, re-lock of the only person after an ID change, all tracks logged, per-session `--feet-row-offset-px`, evidence saved in a `finally`. 11 tests. HNHL's open points: config not loaded into the controller, centring metric units and time basis, command-based pose integration, main-path fault-injection tests.
- **Home session 2026-11-06 to 11-08** (`home_1107/README.md`): `self_pose` after the repair, tape-mark distance checks, 15 recorded runs. Shown: the runner locks, closes to the standoff, centres, holds and follows a walk-back on live video. **Not shown:** the plan's 'Pursuit PD' and 'Standoff hold' thresholds.

## What went wrong (for the record)
- **Several of my explanations were guesses that the data contradicted:** a slipped camera mount, a physical jolt, the person's stance, the phone distance. The data later pointed at the camera pitch drifting by itself (-4.26 to -0.64 deg, 3.6 deg, nobody touching the robot; cause not found) and at the detector box bottom sitting 3-7 px below the feet (about 0.4 m at 1.8 m). I asked 'did you touch it?' when I should have measured; DQK had not touched it. Lesson (again): measure before explaining.
- **Distance numbers were unreliable for much of the session** because the pose drifts; two early 'results' (`home_1_3` in-band fraction, `home_3_1`) are withdrawn. In `home_6_1` the robot moved only about 0.1 m (tape 1.77 m) while the log said it had arrived at 1.27 m.
- **HNHL's reviews caught bugs I would have run on the robot** (the `NameError`, a one-frame yaw pulse that the sender could repeat for 0.25 s, results lost on an SSH error).
- The camera-damage plan entry and the repaired entry were committed after #98 merged and did not reach `main`; they are in this log's PR.

## Findings for the report (design, not patches)
- A 0.100 m lens makes monocular ranging weak in the working band: foot-row range is good to about 1.2-1.5 m with a fresh pose; ankle keypoints do not work as a floor point (the ankle is about level with the lens); box-height ranging works only beyond about 2.2 m (the head clips at the top of the frame closer); between 1.5 and 2.2 m neither is reliable. A higher camera mount would fix it (not planned).
- Pursuit evidence in the report: first supervised live trials, limits stated, no acceptance numbers.

## Open / next
- **Workload note (DQK, 2026-11-08):** next week (Nov 9-15) carries about two to three weeks of work: the classroom session that was pushed (graded T2 runs, Part C, handshake retest, Phase 2, obstacle retest, calibration, F7/F17), the open PR work (#99, #100, #102), the remaining figures and the report sections, with the figure freeze on Mon Nov 16 and the draft on Wed Nov 18. Cut line if time runs short (highest first): must = `self_pose`, T2 deployment 5 of 5, Part C; should = handshake retest, Phase 2 live; cut and report as 'in progress with its plan' = pursuit/hold trials beyond the first live runs, obstacle retest, clean `motion_check`, F7/F17.
- **Supervisor:** tell them about the camera damage and the repair (robot is school property).
- **PR #99:** HNHL's remaining findings; then merge. **PR #100 (HNHL):** needs DQK's review.
- **Classroom Mon 2026-11-09 (G2 day):** `self_pose` first (it drifts), T2 deployment runs 5 of 5 (4 counted so far), Part C, handshake with the live rule (7/10 and 9/10 earlier), obstacle retest, clean `motion_check`. Home items not done: `motion_check` at full battery, D3 recording (HNHL), link-unplugged safety (done on 11-08: 0.48-0.52 s upper bounds, the 0.35 s plan limit is NOT demonstrated; R1-release stop not done); the matte-floor D5 batch was removed from the plan on 11-08.
- **Report:** remaining figures F3, F7, F8, F11, F14, F17, F18; my sections; the hold-exit and re-centring trials if time allows.
- **Unresolved:** why the camera pitch drifts (the repaired FPC socket is a guess); sup3 zero marker fixes; board-loss causes in t2_3 to t2_5; the bearing-based rest heading; the MPU6050.

## Hours
Taken from the chat log (time between messages under 20 min; work away from the chat, and days with long unattended agent runs, are NOT counted, so this is a floor): Mon 11-02 0.3 h, Tue 11-03 0.6 h, Thu 11-05 0.9 h, Fri 11-06 0.2 h, Sat 11-07 1.0 h (the late-night session to 00:58), Sun 11-08 0.7 h (to 17:42; the session continued after this log). **Total 3.7 h** (to be updated with the rest of Sunday's session).
