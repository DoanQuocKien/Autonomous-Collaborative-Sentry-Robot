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

## Person frames, three people (experiment A validation; `data/person_ranges_1111.json`, `scripts/person_ranges.py`)
A = DQK, B = HNHL, C = KR; 9 sets x 12 frames at the tape marks 1.2 / 1.8 / 2.4 m (measured from the robot FRONT; the lens sits about 0.2-0.26 m behind it, unmeasured, so the lens-referenced truth is about the tape + 0.2 m), pose `calib/camera_pose_self_1111_3.json` (pitch -4.11 deg, spread 0.05), glossy tile. Label corrections: set A at 1.8 m was first recorded under 1.2 (DQK said so at once; relabelled, noted in its result file). Frames (local, not committed): every set has one person with feet and torso visible; heads are cut off at 1.2 m for B (top touching the frame edge) and C (face above the frame); a bystander is visible at the far right near the table in A at 1.8 m and B at 1.2 m (in the background, outside the lane). Median forward range per set (m), 12 of 12 frames had a person:

| tape (front) | person | foot row, offset 0 px | foot row, 3.5 px | foot row, 5 px | trunk, prior 0.50 m |
|---|---|---|---|---|---|
| 1.2 | A / B / C | 1.13 / 1.17 / 1.15 | 1.29 / 1.35 / 1.33 | 1.38 / 1.44 / 1.42 | 1.41 / 1.35 / 1.31 |
| 1.8 | A / B / C | 1.72 / 1.66 / 1.65 | 2.14 / 2.04 / 2.03 | 2.39 / 2.27 / 2.26 | 2.19 / 1.89 / 1.90 |
| 2.4 | A / B / C | 2.13 / 2.03 / 2.13 | 2.80 / 2.63 / 2.81 | 3.24 / 3.02 / 3.26 | 2.57 / 2.54 / 2.41 |

Expected with the lens 0.2-0.26 m behind the front: about 1.4-1.46 / 2.0-2.06 / 2.6-2.66.
- **The foot-row range depends mostly on the box-bottom offset, not on the person:** the detector's box bottom sits 3-7 px below the feet, one pixel is about 0.19 m at 2.4 m (d^2 * 0.0033 / 0.100), so 0 px reads 0.25-0.55 m short and 5 px reads up to 0.6 m long at 2.4 m. With the 3.5 px used in the pursuit sessions it is within about 0.1-0.2 m of the expected value at all three marks, for all three people. The offset itself is a per-session constant that nobody measures for a new person: an uncertainty of +/- 1.5 px is +/- 0.3 m at 2.4 m.
- **The trunk range** (shoulder-to-hip 0.50 m, no offset to tune) is within about -0.1 / +0.2 m of the expected value (1.8 m: A +0.2 above the expected; 2.4 m: -0.2..-0.05), the spread between the three people at the same mark is 0.05-0.30 m. One run per set, three bodies, a tape reference with an unmeasured offset: a lead, consistent with the 2026-11-09 sets (bias -0.02..+0.16 m), not an accepted method.
- Frame noise within a set is small (the 12 frames were taken within seconds); this validates the earlier single-person result on two more bodies, not the range limit itself.

## Needs the three members (do first while all are available)
1. Person frames at 1.2, 1.8 and 2.4 m from several different people (experiment A validation; needs more than one person; frames stay local).
2. A full T2 run with a second person walking in: the queue and the lock, with HNHL and KR watching the laptop (the ESP32 handshake at the sweet spot, then the walk-through).
3. Review and decisions: HNHL to review PRs #104-#107 (audit fixes, deploy-live fixes, F17, find_door); KR's PR #101 (changes requested); agree the door-approach strategy (pulse and re-check) and the report text (limits, the +18 % range error, the veer table).
4. F3 (photo of the JetBot, gamepad and ESP32-CAM at the door) needs all of them in one place.
