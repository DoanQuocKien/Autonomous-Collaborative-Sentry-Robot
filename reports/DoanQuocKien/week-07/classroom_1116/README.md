# Classroom, Mon 2026-11-16: T2 deployment run, handshake rehearsals, first pursuit run, camera pose

**Setup:** DQK alone in the classroom. Glossy tile floor, 0.6 m tiles. Robot 10.169.60.160, ESP32-CAM 10.169.60.9, hotspot 2.4 GHz. Battery 11.91 V at the start of the T2 run, 11.89 V at its end; 11.82 V at the start of the pursuit run, 11.78 V at its end; 11.63 V at the end of the session. Power mode read at the end of the session: 5 W (`nvpmodel -q`); it was not read earlier in the day, so the runs are labelled 5 W on the assumption that it did not change. Robot code on the robot is the version from before the audit fixes (4 files differ from `main`, logrotate not installed, no control key: control packets were unsigned). Measurements are from the RTX 4050 laptop (DQK).

## Camera pose (`calib/camera_pose_self_1116_{1,2,3}.json`)
`python -m tools.self_pose --page-bottom-h 0.0`, H fixed at 0.100 m, 45 marker frames each: pitch down -8.18, -8.01, -8.00 deg; spread 0.063, 0.077, 0.018 deg. File 3 was used for the pursuit run. Saturday's value was -2.0 deg, so the mount moved about 6 deg between sessions.

## T2 deployment run (`deploy/t2_1116_1/`) - passed
Command: `tools.deploy_live --label t2_1116 --vantage 1.510 -0.301 --centre 2.939 -2.352 --handshake data/handshake/class_door_1116 --servo-marker 0 --servo-board 2.814 -0.562 --servo-stop 1.33 --esp-ip 10.169.60.9 --ip 10.169.60.160 --wait 45`.
- Servo on board 0 (273 sightings), start 2.87 m from board 0 (limit 2.3-3.35 m). The robot stopped; the tower was then placed in front of the stop point, aimed at the door (the run is not pre-placed).
- APPROACH_VANTAGE 24.4 s, WAIT_CAMERA, handshake verified at 28.7 s (110 of 110 answers in view, last XFeat inliers 289), RETRACT, STANDBY at 30.7 s.
- Tape answers: robot-to-door 2.93 m (window 1.5-3.0 m), line of sight clear, furniture within 1 m: yes (0.35 m), collisions 0.
- Dead reckoning at the vantage was 0.593 m off the typed target (`dr_error_at_vantage_m`); the tape distance decides the pass.
- This is the 7th counted T2 run. Not tested: obstacle stop (no `--camera-pose`/`--floor` on this run), tower avoidance, signed control packets.

## Handshake rehearsals (laptop only, `deploy/rehearsal_1116_*`, `deploy/dry_1116_1`)
Door references and negative sweep in `data/handshake/class_door_1116` (local, not committed; frames). The first 90 sweep frames showed the door and were moved out (a door frame among the negatives set the threshold to about 939); recalibrated, threshold 27 with the clean sweep.
| folder | what | result |
| :-- | :-- | :-- |
| `rehearsal_1116_1` | first rehearsal, references from another tower spot | not verified, 12 of 460 answers in view |
| `rehearsal_1116_2` | laptop only, no handshake frames | time limit, nothing measured |
| `rehearsal_1116_p1_1` | Part 1, first try | not verified, 0 of 285 answers in view, time limit (cause not established) |
| `rehearsal_1116_p1_2` | Part 1: ESP32 aimed at the door | verified 8.6 s after the prompt, 50 of 50 in view |
| `rehearsal_1116_p2_1` | Part 2 (aimed away) | invalid: the tower was not turned away, so it verified (83 of 83 in view) |
| `rehearsal_1116_p2b_1` | Part 2 redone, tower aimed away, then turned back by hand | no verification while aimed away; verified at 40.2 s after turning back (67 of 203 answers in view) |
| `dry_1116_1` | dry run, robot connected, no motor commands | STANDBY reached, 111 of 111 in view |
One valid run of each kind: this is not the 10 accepts / 10 rejects of the plan.

## First live pursuit run (`pursuit/pursuit_1116_1/`, `--floor glossy`, one person, DQK as target)
60 s, no HOLD stage tried (not tested this session; the run did not include a deliberate stand-still).
- Target tracked 99.7 % of the run, 1 re-acquire (about 46 s).
- Distance within 1.2 +/- 0.2 m: 32 % of the run. Box centre within +/- 10 % of the frame width: 91 %. Plan threshold is 80 % for both: the distance fraction is far below it, so this is NOT a pass; the logged distance ranged about 1.0-3.9 m while the target also moved at will.
- 90 frames flagged obstacle-blocked with no measured obstacle distance (glossy floor, unresolved); no obstacle was placed. HOLD events: 0.
- `pursuit_1116_dry_1`: dry run, 241 frames, nobody tracked.

## Not done / not counted
- `tools.motion_check` (two attempts' worth of boards, `data/motion_check/class_1116_1`): only 2 of 6 segments had a board pose at both rests (boards 2.1-2.54 m away); nothing was fitted and nothing here relies on it. Earlier runs (`dorm_1`, `class_1`, `class_2`) also give no fit. Not planned; the dead-reckoning gains remain the Week 2 ones (known limit).
- F3 photos: `../figures/F3_devices_door_1116.png`, `F3_devices_marker_1116.png`.
- Local only (faces or frames, git-ignored): `data/handshake/class_door_1116`, `frames/` folders under `data/deploy`.
