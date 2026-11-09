# Week 06 - DoanQuocKien (2026-11-09 to 2026-11-15)

*Started Mon 2026-11-09 (classroom, alone, no ESP32-CAM on hand; the official session is pushed to next week). See you Wed 2026-11-11.*

## Done so far (Mon 11-09, classroom, glossy tile floor with 0.6 m tiles)
- `self_pose` four times (pitch -4.34 to -4.70 deg, stable); pursuit runner trials in tile steps and the standoff dead band (first live runs, no acceptance; true hold about 1.7 m, the runner read 1.3 m); the motion test (driving does not change the camera view); obstacle retest with a metal-frame chair at 1.2, 1.8 and 2.4 m: **no distance in any frame** (`reports/DoanQuocKien/week-06/classroom_1109/`).
- Fixes for HNHL's review of PR #99 (config, centring units and time basis, pose integration, main-path tests), the yaw-pulse expiry and the save-on-failure fix; reply posted. PR #99 waits for his re-review.
- Plan and report notes: matte-floor work removed, measured limits of monocular floor ranging with a 0.100 m lens (plan risk 31, report plan section 8), labels corrected (the 11-09 tests were in the classroom).
- Robot: shut down cleanly (the power switch is a plain switch: `sudo shutdown -h now` first; an unclean power-off showed an ext4 journal recovery).

## Planned for tonight (robot available)
- **Experiment A:** a metric monocular depth model on the tile marks 1.2, 1.8, 2.4 m (pass: every tile within +/- 0.15 m).
- **Experiment B:** find and test a model that works on the glossy floor (YOLOv8s, YOLO-World, SegFormer floor analyzer, combinations; chair, table and empty-floor frames; pass: distance in >= 10/12 frames within +/- 0.15 m up to 1.5 m and no false stops). Plan: Week 6 section.

## Open / next (full list: plan, Week 6 section 'Carried over')
- The table retest (robot 1.2, 1.8, 2.4 m from it), `self_pose` after moving the robot; T2 deployment 5 of 5, Part C, the handshake retest and Phase 2 live (need the ESP32-CAM and the real session); classroom-floor `motion_check`; R1-release stop trial; F7, F17, F21; reviews of #99, #100, #102; the supervisor message about the camera.

## Hours
Mon 11-09: to be filled from the chat log (see the Week 5 rule: gaps under 20 min, a floor).
