# Week 06 - DoanQuocKien (2026-11-09 to 2026-11-15)

*Started Mon 2026-11-09 (classroom, alone, no ESP32-CAM on hand; the official session is pushed to next week). See you Wed 2026-11-11.*

## Done so far (Mon 11-09, classroom, glossy tile floor with 0.6 m tiles)
- `self_pose` four times (pitch -4.34 to -4.70 deg, stable); pursuit runner trials in tile steps and the standoff dead band (first live runs, no acceptance; true hold about 1.7 m, the runner read 1.3 m); the motion test (driving does not change the camera view); obstacle retest with a metal-frame chair at 1.2, 1.8 and 2.4 m: **no distance in any frame** (`reports/DoanQuocKien/week-06/classroom_1109/`).
- Fixes for HNHL's review of PR #99 (config, centring units and time basis, pose integration, main-path tests), the yaw-pulse expiry and the save-on-failure fix; reply posted. PR #99 waits for his re-review.
- Plan and report notes: matte-floor work removed, measured limits of monocular floor ranging with a 0.100 m lens (plan risk 31, report plan section 8), labels corrected (the 11-09 tests were in the classroom).
- Robot: shut down cleanly (the power switch is a plain switch: `sudo shutdown -h now` first; an unclean power-off showed an ext4 journal recovery).

## Night of 11-09/10: experiment A (metric range from one camera at 0.10 m): eight rounds, documented
Off-the-shelf metric depth models (six variants, zoom, floor-plane anchor), leg-based body cues and fusion with the foot row all FAIL; the shoulder-to-hip trunk length with a population prior is a lead (bias -0.05 to +0.13 m, noise 0.01-0.03 m, one person, three saved sets) and is in the runner as `--range-source trunk` (PR #99, default off, not run on the robot). Details and numbers: `reports/DoanQuocKien/week-06/classroom_1109/README.md`. Needs for validation: person frames at 1.2, 1.8, 2.4 m from several people.

## Tomorrow (11-10/11): experiment B (glossy floor)
Start: the ORG dataset (7.1 GB Google Drive zip; `gdown` stalled twice, browser download to `data/ORG/ORG.zip` needed), saved D1 glossy-tile sets with tape distances (`data/D1_obstacles_1015`), D5, the 36 chair frames of 11-09. First offline pass: no local detector gives a distance on the glossy floor (`reflection_unresolved` is the blocker). Plan: re-judging script on the saved sets, reflection-threshold sweep, a model trained or fine-tuned on ORG plus our D5/D1, then the live robot check at the same tile marks.

## Planned for tonight (robot available) - done for A, B moves to tomorrow
- **Experiment A:** a metric monocular depth model on the tile marks 1.2, 1.8, 2.4 m (pass: every tile within +/- 0.15 m).
- **Experiment B:** find and test a model that works on the glossy floor (YOLOv8s, YOLO-World, SegFormer floor analyzer, combinations; chair, table and empty-floor frames; pass: distance in >= 10/12 frames within +/- 0.15 m up to 1.5 m and no false stops). Plan: Week 6 section.

## Wed 11-11 (classroom, all three members present in the evening): details in `week-06/classroom_1111_pm/README.md`
- **The robot reached a legal sweet spot on its own** (`tools/approach_door.py`, run `ap_1`): spin until the door is seen, then pulse, re-measure, drive a burst, repeat; range from the door outline area scaled from one tape value; 51 steps, 10 bursts, stopped at an estimated 1.97 m, **tape 1.67 m** (window 1.5-3.0 m), pointing at the door centre. One run. It hunted (turn pulses of about 13.5 deg against a +/- 4 deg window): window now +/- 8 deg (simulation, not yet tried on the robot).
- **Why the earlier attempts failed (measured):** the open-loop drive veers by -16 to +59 deg/m at about the same command (5-6 times the October calibration and of the other sign; F22); triangulating the door from two spin scans gave ranges 45-72 % too long (1.8 m tape vs 3.1 m; 3.42 m vs 4.96 m) with the bearing right to about 1 deg: the first scan's heading accumulates pulse errors (a heading estimator fix is being developed). Two bugs of mine fixed (a start check that refused a board over 2.6 m, a drive loop that gave 0.3 s of command per 1.7 s round).
- **Experiment B controls:** empty glossy floor 24 frames: configured detector 0, fine-tune obstacle class 0, **free-space output 24 of 24 false stops at 0.2 m (glare)**; table set inconclusive.
- **Person frames, three people at 1.2 / 1.8 / 2.4 m** (experiment A validation, F24): foot-row range within about 0.1-0.2 m of the expected value with the 3.5 px offset but 0.25-0.55 m short without it (the box-bottom offset dominates); trunk range within about -0.2 / +0.2 m.
- **D2 face entries on the ESP32 at the door** (100 s per member): the faces are 22-53 px wide (cafe pilot 45-60 px; F25); TAR 0.40 at FAR 0.066 at the 0.45 threshold with buffalo_s; the larger buffalo_l gives AUC 0.79 / 0.84 (frame / entry) and TAR 0.32 at FAR 1 %: not enough. The cheapest lever is the sensor resolution (SXGA about 2x the face width at about 2 fps); a dorm test is planned (no redo tonight, the others went home).
- **Reviews:** approved KR's #107 (scan video guards); #100 approved earlier and merged; #104 and #106 merged; #105 merged; #108 (this work) waits for HNHL; #101 (KR) still has changes requested.
- Not done: the counted T2 run (the ESP32 tower was not ready), the ESP32 handshake re-placement test (dropped: two passes already), F3, F7, F8. The robot was switched off without the clean shutdown at the end (check the boot).

## Open / next (full list: plan, Week 6 section 'Carried over')
- The table retest (robot 1.2, 1.8, 2.4 m from it), `self_pose` after moving the robot; T2 deployment 5 of 5, Part C, the handshake retest and Phase 2 live (need the ESP32-CAM and the real session); classroom-floor `motion_check`; R1-release stop trial; F7, F17, F21; reviews of #99, #100, #102; the supervisor message about the camera.

## Hours
Mon 11-09: to be filled from the chat log (see the Week 5 rule: gaps under 20 min, a floor).
