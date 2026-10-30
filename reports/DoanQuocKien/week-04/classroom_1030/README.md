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
