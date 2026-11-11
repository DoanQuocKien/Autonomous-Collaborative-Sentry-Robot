# Classroom, Wed 2026-11-11 (evening session): the robot finds and approaches the door on its own

**People:** all three members were available this session, a rare occasion (DQK at the robot; HNHL and KR available). Decision recorded here by DQK: do first everything that needs the three members (see "Needs the three members" below); robot-only work comes second.
**Floor:** glossy tile, 0.6 m tiles. Robot at 10.169.60.160. Battery 12.45 V at the start, 11.53 V at the end of the last run (gate 11.4 V). Pose `calib/camera_pose_self_1111_2.json`: pitch -4.28 deg, spread 0.01 deg, 45 of 45 marker frames, boards on the floor (page bottom 0.000 m, an assumption).
Tools (branch `DoanQuocKien/w06-find-door`): `tools/find_door.py`, `tools/locate_door.py`, `tools/approach_door.py`, `tools/speed_trial.py --max-start-m`, tests `tests/test_find_door.py`, `tests/test_locate_door.py`, `tests/test_approach_door.py`. Data here in `data/`.

## Result: autonomous arrival at a legal sweet spot (`approach_door`, run `ap_1`)
The robot started with the door behind-right (about 3.42 m by tape, about -130 deg), spun right to find it, then repeated: measure the door (median of 5 frames: bearing from the entrance detector, outline area) -> turn a short pulse until the bearing is within +/- 4 deg, or drive a 0.6 s burst at v = 0.85 -> stop, hold 0.8 s, measure again. Range = 3.42 m * sqrt(A0 / A) with A0 the outline area of the first sighting (the only manual number is that tape value). It stopped at an estimated 1.97 m after 51 steps, 10 drive bursts, about 2.5 minutes, no human input during the run.
**Tape afterwards: 1.67 m, pointing at the door centre.** The legal window is 1.5-3.0 m, so this is a usable sweet spot. Range-from-area error +0.30 m (+18 %; the estimate was too long, consistent with the two triangulation runs below). One run, one door, one day.
Observed weakness: about 35 of the 51 steps were turn pulses hunting around the 4 deg window (+8 / -8 deg alternation: the shortest useful pulse turns more than 4 deg). Planned: accept about 8 deg before driving, or a shorter pulse. The "pulse and re-check" scheme itself (never trust the open-loop heading, re-measure after every move) is what made the arrival work and is the candidate strategy for the approach.

## Why the earlier attempts failed (all measured, same day)
- **Open-loop forward drive veers, unpredictably.** Degrees of turn per metre (left +), from every logged speed run with a marker in view: v 0.4: -1; 0.5: +13; 0.6: +10; 0.7: +32 / +19; 0.85: +8; 1.0: +4; the four `head_*` runs at 0.6: -16, +18, +23, -3; low battery (10.97 V) 0.6: +22; today at 0.55: +59 (three drives: 12-15 deg/s). Same command, different outcomes: no fixed trim fixes it. At 0.85 the two find_door drives veered about 25 deg/m. The calibration `calib/motion.json` (2026-10-11) says -0.186 rad/m (about -11 deg/m): today's veer is 5-6 times larger and of the other sign. Likely causes (unproven): the floor, lower battery (11.5-12 V), low motor values near the dead zone (JetBot Notes, 2026-10-06).
- **Triangulating the door from two spin scans** (`find_door`, baseline drive between): the second scan's door bearing agreed with the tape to about 1 deg, but the range was too long both times:

  | run | tape (distance, bearing) | robot estimate | error |
  |---|---|---|---|
  | `fd_4` | 1.8 m, -65 deg | 3.1 m, -63.6 deg | range +72 %, bearing 1.4 deg |
  | `fd_6` | 3.42 m, -130 deg | 4.96 m, -128.9 deg | range +45 %, bearing 1.1 deg |

  Back-calculated from the tape, the FIRST scan's door direction was off by -3.8 deg and -5.5 deg (same sign), enough to stretch the range at a ray angle of 10-13 deg. Probable source (partly verified): the scan heading is a running sum of about 15 pulse angles (spread about 2 deg each); the only two scans with a board at both the first and the last stop show the sum off by -1.7 and -8.2 deg. The board-fit residual was 0.1-0.3 m with 2 common boards, 150 mm markers at 3 m. `fd_5` failed (residual 0.29 m, heading contradicting the commanded turn). The tool flagged `fd_5` as unreliable by baseline and ray angle only; the residual check is still to be added. Not fixed: the raw per-sighting headings were not saved. Needed: per-sighting headings, loop closure, at least 3 boards common to both scans within 2.5 m.
- **Bugs of mine, fixed:** `speed_trial` refused a board farther than 2.6 m (the robot "did not move"); the first baseline drive ran 0.3 s of command per 1.7 s round (an SSH check per round; now a 30 Hz thread); the door bearing was the median of all sightings, which also fire at wrong headings (now the dominant cluster, raw sightings saved).
- **Scan turn calibration is stable:** 26.6 and 25.8 deg per 0.2 s pulse (spread 0.03 rad), 23-26 deg in the later scans; full circle in 13-16 stops.
- Two scans by hand-carried baseline (1.37 m by the boards, ray angle 24.6 deg): door at (2.92, -1.25) m in the first frame, 3.18 m from the first spot, spread 2.79-3.73 m with +/- 2 deg bearing noise (too optimistic, see above).

## Experiment B controls (same session)
- **Empty floor** (`empty_floor_1111_a`, 24 frames, one position, a chair and a person's legs at the far right edge outside the lane): configured detector 0 of 24, fine-tune obstacle class 0 of 24, **fine-tune free-space output 24 of 24 false stops at 0.19-0.21 m** (glare). Data `results/empty_floor_1111.json` (branch `DoanQuocKien/w06-empty-floor-control`).
- **Table** (`table_pedestal_big_1p2`, 24 frames, tape 1.2 m from the front): inconclusive (the frame shows a table leg and six chairs behind). Configured detector: a "chair" in 24 of 24, with a distance in 1 (3.07 m, wrong); obstacle class: a lane prediction in 9 of 24 (1.24-1.83 m); free space 0 of 24. To be redone with a traditional table.
- Not done: ESP32 handshake re-placement test (dropped: two passes already, see `classroom_1111`), counted T2 runs (the ESP32 was shut down and the door approach was not solved earlier). The sweet spot is now reached by the robot; the handshake and the reverse to standby are the next steps.

## Needs the three members (do first while all are available)
1. Person frames at 1.2, 1.8 and 2.4 m from several different people (experiment A validation; needs more than one person; frames stay local).
2. A full T2 run with a second person walking in: the queue and the lock, with HNHL and KR watching the laptop (the ESP32 handshake at the sweet spot, then the walk-through).
3. Review and decisions: HNHL to review PRs #104-#107 (audit fixes, deploy-live fixes, F17, find_door); KR's PR #101 (changes requested); agree the door-approach strategy (pulse and re-check) and the report text (limits, the +18 % range error, the veer table).
4. F3 (photo of the JetBot, gamepad and ESP32-CAM at the door) needs all of them in one place.
