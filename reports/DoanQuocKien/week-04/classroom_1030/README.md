# Classroom session 2026-10-30 (DQK alone): deployment runs and raw motion data

Everything here was measured as written; the user's own words are quoted where the number is a tape or eyeball reading. Video frames are NOT in the repository (faces possible, `data/` is git-ignored): they stay local, paths below.

## Layout
Start frame: robot start (0, 0) facing +x, y left. Boards (150 mm, A4 page on the floor, centre 0.207 m): id 0 ("board 1") at (1.94, 0) facing the start; id 1 ("board 2") on the robot's right at (0, -2.67); id 2 ("board 3") 1.5 m to the left, (0, 1.5) (my assumption: level with the robot and facing it; forward offsets unmeasured). Sweet spot for the later runs: (0, -1.8), 0.87 m from board 2 (the first run used (0, -3.0)). The room has a very large table that cannot be moved and blocks part of the path (DQK).

## Deployment runs (`deploy/<run>/`: summary.json, log.csv 30 Hz, servo.csv where the board was followed)
| run | method | result as measured |
|---|---|---|
| sup1 | dead reckoning only, sweet spot (0, -3) | DR believed it was 0.115 m from the sweet spot; **the robot veered off the line toward the door and DQK stopped it by hand** (R1 released at 16.8 s). Not a T2 run. |
| sup2 | DR, sweet spot (0, -1.8), provisional correction | STANDBY, handshake verified; DQK: **ended -0.8 m and -0.17 m from the sweet spot, camera completely turned around**. DR said (0.35, -1.66). |
| sup3 | DR + marker fixes (`--anchors`) | STANDBY, verified; **0 marker fixes were applied** (cause not found: the same code gave fixes in one instrumented dry run); outcome position not recorded; DQK: the path is blocked by the table. |
| sup4 | follow board 2 (`--servo-marker 1`) | reached 0.81 m from board 2 straight (bearing within about +-0.05 rad), prompted; **R1 released at 20.4 s** (the turn to the centre used a wrong DR pose: fixed afterwards). DQK: final position "rather accurate". |
| sup5 | follow board 2 + pose reset on arrival | vantage at 10.8 s, turned to the centre (-176 deg), **handshake 0 of 59 frames in view (ESP32 not aimed at the door); R1 released at 18.1 s**. DQK: the tape measure is correct to the sweet spot (no cm given). |
| sup6 | same, ESP32 aimed at the door | **STANDBY at 16.0 s, handshake verified 0.9 s after the prompt** (42 of 42 frames in view; the camera was pre-aimed, so this does not test camera placement). DQK tape: **-0.18 m and +0.19 m from the sweet spot** (0.26 m); the robot's own pose says 0, 0 because the pose is reset to the sweet spot on arrival, so it is not an independent measurement. |

T2 (5 runs, pass: tape distance to the door 1.5-3.0 m, clear line of sight, wall/furniture within 1 m, verified, STANDBY, 0 collisions): **0 of 5 counted**. sup6 reached STANDBY with a verified handshake but the door distance, line of sight, furniture and collision answers were not given (the tool's prompts got empty input), and DQK judged the information sufficient to continue; I do not count it as a pass. Battery 11.58-11.73 V throughout (no run below the 11.3 V start guard).

## Motion data for the calibration math (`motion_check_class_1/`, `calib/`)
- `motion_check_class_1`: spin left / spin right / forward x2 with only board id 0 at about 2 m (anchors `calib/anchors_class_1030.csv`), raw commands + segments + the per-segment result. Marker poses at a 2 m board are noisy (still robot: yaw -17..+8 deg frame by frame, median within about 1.5 deg / 3 cm of the truth). Results: spin right 1: measured -41.4 deg vs model -49.8 (ratio 0.83); forward 1 and 2: ratio 1.07 and 1.04, **heading change +12.6 and +10.1 deg over 0.44 m (drift +0.50, +0.41 rad/m, left)**; spin left and the second spin right had no marker pose (board out of view). The fit was refused (no measurable left spin). A second pass with boards at +-90 deg (`class_2`, anchors `calib/anchors_class_1030b.csv`) never ran (R1 not armed).
- `calib/motion_session_1030_provisional.json`: HAND-MADE from the numbers above (scale 1.05, left turn 1.0, right turn 0.79, drift +0.45 rad/m), NOT a tool fit; used for sup2-sup6.
- Speed from following board 2 (`deploy/sup4_1..sup6_1/servo.csv`, range vs time while driving; ratio = measured / the model with the provisional correction): **0.936 (sup4), 1.027 (sup5), 1.028 (sup6)** -> true speed scale about 0.98-1.08 x 1.05.
- **Turn rates from the board are not valid**: the video lags the motors by about a second, so the bearing keeps changing after a spin pulse ends (the tool printed -0.1, -0.008, -0.122 for the right turn: ignore). To compute: the still-before to still-after bearing change of each pulse in `servo.csv` (rows with cmd_v = 0 and cmd_w = +-0.45; the pauses between pulses are rows with cmd_w = 0) against the model's turn per pulse.
- Local only: `data/motion_check/class_1/frames` (the marker frames; `python -m tools.motion_check --label class_1 --anchors data/anchors_class_1030.csv --replay-only` re-analyses), `data/deploy/sup5_1/frames` (320) and `sup6_1/frames` (281), all robot video of the runs. `calib/camera_pose_self_1030_2.json` is today's camera pose from `tools/self_pose.py` (pitch +2.15 deg, roll +2.34 deg, spread 0.02 deg, 45 frames).

## Not done / open
Turn-rate calibration (left and right), a valid fit from `tools.motion_check`, T2 runs 2-5 and the tape answers, the Part C Phase 1 chain, the obstacle-detector blindness on this glossy floor (1 of about 5 chairs found; `deploy_live` does not avoid, DQK held R1 and the path was cleared by hand).

## t2_1 (2026-10-30, after the table above was written)
Same method as sup6 (follow board 2). STANDBY at 17.8 s, handshake verified 2.1 s after the prompt (62 of 62 frames in view, camera pre-aimed), vantage at 13.6 s (slower than sup6: 10.8 s). **Battery 11.44 V at the start, 11.43 V at the end; the speed ratio from board 2 was 0.75** (earlier runs 0.94-1.03), cause unknown: **t2_2 at a lower voltage (11.40 V) gave 0.93**, so the battery alone does not explain 0.75 (the Week 2 note says the wheel offset grows at low voltage, which may add to it). Door, from the sweet spot (tape, DQK): (1.94, -0.30) m = 1.96 m, clear line of sight, tables and chairs within 1.5 m of the path (the pass rule says within 1 m: not confirmed). Collisions and the offset from the mark: not yet given. Frames (349) local in `data/deploy/t2_1/frames`.

## What went wrong today and the rules (DQK: "today's work is VERY inefficient")
1. A DR pose was reported as the result of sup1; the robot had veered. A logged pose is not ground truth: ask what happened physically.
2. Two hours of dead-reckoning corrections and motion fits before the simple closed loop (follow board 2 by its bearing), which worked at once. Use a visible landmark as feedback first; calibrate later.
3. Optional calibration tooling displaced the required T2 runs. In a room slot, do the required graded runs first; record data for optional maths and do the maths at home.
4. The motion check was built without looking at the live measurement: spins of 200 deg, a blending bug beyond 0.8 m, a 2 m board too noisy. Look at the measurement live, robot still, before building on it.
5. Four runs were started before the operator was ready (R1 not armed in 60 s). Announce what the run needs and wait for "go".
6. The tape answers were never saved (stdin was /dev/null). Capture grading inputs at run time.
7. sup3 and a dry run applied 0 marker fixes, an instrumented run 72: cause not found. A feature that silently does nothing must be reported or removed.
8. The battery fell to 11.44 V before t2_1 and no charge was possible: runs 2+ were taken at 11.40 V with the guard lowered to the project rule (11.1 V). Read a speed ratio together with the voltage; do not claim a cause for one odd value (t2_1 0.75 vs t2_2 0.93 at a lower voltage).

## t2_2 (11.40 V, guard 11.1 V)
Vantage at 11.7 s, then **R1 released at 17.9 s with the handshake at 0 of 57 detector frames in view** (the ESP32 was not aimed at the door); not a pass, not graded. Speed ratio from board 2: 0.93. Battery 11.396 -> 11.384 V. Frames (320) local.

## T2 grading, tape answers as given by DQK (2026-10-30)
Door from the sweet spot: (1.94, -0.30) m = 1.96 m (the tape distance for every run, corrected by each run's offset below, stays inside 1.5-3.0 m); clear line of sight. **Collisions: none in any run, "there are no collision or any obstacle"** (DQK; applies to sup6, t2_1, t2_3). Furniture: tables and chairs within 1.5 m of the path; DQK also said there is no obstacle on the path, so whether something stands within 1 m of the sweet spot (the pass rule) is NOT settled; the table is very large and cannot be moved.
| run | STANDBY | handshake | offset from the sweet spot (tape) | counted |
|---|---|---|---|---|
| sup6 | yes, 16.0 s | verified (42/42) | (-0.18, +0.19) m = 0.26 m | COUNTED |
| t2_1 | yes, 17.8 s | verified (62/62) | (+0.25, -0.10) m = 0.27 m | COUNTED |
| t2_2 | no (R1 released 17.9 s) | 0 of 57 in view (ESP32 not aimed) | < 0.04 m | no |
| t2_3 | yes, 16.5 s (battery 11.36 V) | verified (52/52) | (-0.31, +0.23) m = 0.39 m | COUNTED |
**COUNTED = 4 of 5 (sup6, t2_1, t2_3, t2_4), by DQK's decision 2026-10-30:** each reached STANDBY with the handshake verified, 0 collisions, door distance 1.96 m, clear line of sight, and tables and chairs within 1.5 m of the path. The pass rule says furniture within 1 m; DQK reported 1.5 m and decided it counts: stated here as a deviation from the rule's 1 m wording. Offsets from the sweet spot 0.26, 0.27, 0.39 m. t2_2 is not counted (incomplete). t2_4 (11.31 V, STANDBY at 18.0 s, verified 68/68, speed ratio 0.72) ended **(-0.60, +0.53) m = 0.80 m from the sweet spot, the largest miss**; the door at 1.94, -0.30 from the sweet spot is then about 2.67 m from the robot if the offset is in the same axes (inside 1.5-3.0 m), and the rule has no limit on the offset, so it is counted. Speed ratio from board 2 over these runs: 0.75, 0.93, 0.80 (and 1.03 for sup6): unexplained scatter.

## t2_5 (11.28 V): incomplete, not counted
Vantage reached at 16.9 s (the slowest so far: 11-13 s in the earlier runs), **R1 released at 22.9 s, 6 s after the vantage, with no ESP32_VERIFIED event although all 47 detector frames of the run were in view** (the reason it did not verify within 6 s is not found; whether the release was deliberate is not recorded). Speed ratio from board 2: 0.65. **Speed ratio against battery voltage, run by run: sup6 11.58 V 1.03; t2_1 11.44 V 0.75; t2_2 11.40 V 0.93; t2_3 11.36 V 0.80; t2_4 11.31 V 0.72; t2_5 11.28 V 0.65.** A falling trend with voltage (t2_2 is the exception): consistent with the wheel offset growing at low battery, not proven (one pack, no repeats at one voltage). T2 count stays 4 of 5.
t2_5 offset from the sweet spot where it was stopped (tape, DQK): **(-0.60, +0.97) m = 1.14 m**, the largest miss; still not counted (no handshake verification, R1 released at 22.9 s).

## motion_check class_2 (boards ahead, 90 deg left and 90 deg right; 11.2 V; 3 repeats of spin left, right, right, left, forward; 0.8 s spins, 1.5 s drives)
Two earlier attempts stopped 1.6 s and 0.3 s after the start (e-stop latch appeared; cause not found); the third ran the whole sequence. **Only 6 of 15 segments had a marker pose before and after** (no board within 3.0 m at the other rests: boards out of view at the rest or the assumed board positions wrong), so **the fit was refused (scatter) and no session file was written**. Measured turn against the model's 104 deg per 0.8 s spin: left 0.89, 1.20, 1.13; right 1.18, 0.80 (so single spin pulses vary by about +-20 %, and the left and right means are not distinguishable from this); forward_2 measured 0.49 m vs 0.31 m predicted (ratio 1.59, heading -1.0 deg, drift -0.04 rad/m), one drive only. Not proven whether the scatter is the robot (start-up lag, unlevel floor) or the marker pose at 2.7 m (yaw noise of several degrees). Raw commands, segments, per-segment results here; frames local in `data/motion_check/class_2/frames`; backup zips refreshed in `D:\CS532\classroom_1030_backup`. Use for the home analysis with `python -m tools.motion_check --label class_2 --anchors data/anchors_class_1030b.csv --quad --replay-only` (the anchors are my assumptions, not tape).

## Furniture check (tools/furniture_check.py, robot still, glossy floor, camera pose `calib/camera_pose_self_1030_2.json` from this morning: the mount may have moved since)
| tape (camera to nearest point on the floor) | detector found it | with a distance |
|---|---|---|
| chair 1.20 m (an ArUco board stood on it) | 12 of 12 frames, class 56, confidence 0.49-0.85 (plus a class 59 box on the image border, 0.26-0.42, rejected as border-truncated) | **0 of 12**: "no_ground_intersection_or_out_of_range"; the chair's box ends at row 231 of 480, above where its legs should be (about row 275 at 1.2 m): probable cause, not proven |
| chair 2.40 m | **0 of 12** | none |
The big table was not tested (stopped by DQK, time). Two spots, one chair: not a recall measurement. Frames local in `data/furniture/<label>/frames`. The detector sees the chair at 1.2 m but gives no usable distance here; the distance step needs fixing at home (e.g. use the box width or the contact point instead of the box bottom).

## CORRECTIONS from the full analysis (analysis/README.md, results.json; written after the sections above; these supersede them)
- **Withdrawn: "speed ratio falls with battery" (0.65-1.03).** The tool's ratio fitted one line across several drives with stops and spins between them. Per drive the speed is 0.2239-0.2245 m/s at 11.58-11.70 V (sup4-sup6) and 0.2156-0.2159 m/s at 11.39-11.44 V (t2_1, t2_2): about -3.9 %.
- **Why the big tape misses happened:** t2_3, t2_4, t2_5 lost sight of board 2 (at 1.80, 1.82, 1.41 m) and drove 0.79-0.97 m on dead reckoning; their misses were 0.39, 0.80, 1.14 m; the runs that kept the board missed by at most 0.27 m. Why the board was lost is not found.
- **Withdrawn: turn ratios and the hand-made right-turn scale 0.79** (noisy marker yaw). Measured: 0.438 rad per 0.2 s pulse (sd 0.030, n = 12); turn = 2.395 rad/s x (T - 0.017 s) over all spin lengths (n = 20). The video lags the motors by less than 0.16 s, not about a second.
- **Drift:** +0.38 rad/m steady (5 runs), +0.57 rad/m on drives from rest (4 runs): left; the provisional +0.45 is fine as a mean.
- **Camera pitch:** the robot's own video shows 6.0-6.2 deg down in the deployment runs, NOT the 2.15 deg of `calib/camera_pose_self_1030_2.json` (the mount moved or that pose was wrong). With the 6 deg pitch the 1.2 m chair box bottom gives 1.194 m against the tape's 1.20 m, so the "box ends above the legs" explanation above is withdrawn; the distance step failed because of the stale pitch. The chair at 2.4 m is not detected even at confidence 0.05 (the detector, not the threshold).
- **Stop overshoot** 0.043 m (sd 0.014, n = 5); t2_5 stopped 3.28 s after the vantage (the ENDED line adds 2.3-2.8 s of shutdown in every run); it did not verify because too few or stale ESP32 answers arrived after the prompt.
- **Not the cause of 0 marker fixes:** `--motion-session` (replay: 18 vs 23 fixes). Still unresolved: why sup3 and dry_fix_1 got no fixes, why board 2 was lost, the early motion_check stops (the robot's `estop.log` may say), left vs right turn (2 left pulses only).
