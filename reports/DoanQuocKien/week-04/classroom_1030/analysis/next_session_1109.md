# Next classroom session, 2026-11-09: what still needs the room

This list comes from `README.md` in this folder.

**Words used below:**
- **Pass** = the stated criterion is met as measured on the day.
- **Record** = typed into the run's summary or the session README at the time, not from memory afterwards.

**Rule for this session: the graded runs come first. Measurements for the maths come after them, and the maths is done at home.**

## A. Tool changes to make at home BEFORE 11-09 (each one avoids a loss seen on 10-30)

| # | change | why (10-30 evidence) |
|---|---|---|
| 1 | `deploy_live --servo-marker`: when the board has not been seen for 0.6 s, **do not fall back to the dead-reckoning go-to**. Stop, pulse-spin toward the last bearing, and stop the run with a reason after N s. | t2_3, t2_4 and t2_5 lost board 2 at 1.4-1.8 m and drove 0.79-0.97 m blind. Their tape misses were 0.39 / 0.80 / 1.14 m, against ≤ 0.27 m for the board arrivals. |
| 2 | Stop margin: arrive when range ≤ stop - v × 0.20 s, i.e. stop the motors 0.044 m early at 0.22 m/s. | Measured overshoot 0.043 m (sd 0.014, n = 5). |
| 3 | Grading answers are not read from stdin. Use a `--answers` JSON file, or a small command run after the run that adds them to `summary.json`. Ask for offsets in **named axes** (x forward from the start, y left), plus "furniture within 1 m: yes/no, measured distance". | Every `tape_answers` field of 10-30 is empty (stdin was /dev/null), and the offsets have no axes. |
| 4 | Log every handshake answer (t, in_view, inliers) and every robot frame's `seq`/`t_cap` (the ZMQ header has both). Count MarkerFix `measure()` calls and non-None results in the summary. | The t2_5 handshake cause and the sup3 0-fix cause could not be decided without these. The video latency could only be bounded. |
| 5 | Remove the `servo_motion` ratios from the summary and the print, or replace them with the per-drive fit (`tools/analyse_classroom_1030.drive_fits`). | The printed 0.65-1.03 "speed ratio" and the turn ratios were artefacts. |
| 6 | `tools.motion_check`: measure turns from board **bearings** and drives from **range** (as `motion_check_analysis` here). `--replay-only` must not overwrite `data/.../summary.json`. | The rest-pose yaw at 2-2.7 m gave 0.80-1.59 ratios; the bearing method gave 0.95-1.09. Replay currently rewrites the raw summary. |
| 7 | `calib/motion_session_1030_provisional.json`: set `w_scale_right` to 1.0 and `scale` to about 1.05, or build the model with `tools/floor_model.wheel_model(fm, V)`. | Right pulses measured 0.438 rad against 0.385 predicted. |
| 8 | Operator prompt: after "place the camera", tell the operator to hold R1 until the 2 beeps, at least 10 s. Print "STANDBY: release R1". | Verification took 0.94-2.10 s, and t2_5 was released 3.28 s after the prompt without verifying. |
| 9 | Battery: graded runs at ≥ 11.4 V. Read `jetbot_status` before each graded run and charge in between when below. | The speed model is fitted for 11.28-11.70 V. All three blind runs were at 11.28-11.36 V; this is not proven to matter. |

## B. In the room: ordered list (about 2 h)

| step | what | command (laptop) | time | pass / what to record |
|---|---|---|---|---|
| 0 | Battery, link, and the 10-30 e-stop log (read only) | `python -m tools.jetbot_status <ip>`; `ssh jetbot@<ip> tail -n 300 /home/jetbot/sentry/estop.log` | 5 min | ≥ 11.4 V to start graded runs. Copy the log lines from 10-30 10:34-10:36 and 11:42-11:43 (local time): they give the cause of the motion_check stops (R1 released / button / gamepad lost). |
| 1 | Camera pitch at the start spot (ArUco page standing on the floor, 1-2 m ahead) | `python -m tools.self_pose --page-bottom-h 0.0` | 5 min | Pass: ≥ 15 frames and spread < 0.4 deg. Record the pitch. 10-30 measured 6.0-6.2 deg from 11:10 on, against 2.15 in the morning file. |
| 2 | **T2 graded runs, 5 plus 1 spare**, same layout as 10-30 (board 2 at (0, -2.67), sweet spot (0, -1.8), door (1.94, -0.30) from the sweet spot) | `python -m tools.deploy_live --label t2b --servo-marker 1 --servo-stop 0.87 --servo-board 0 -2.67 --vantage 0.0 -1.8 --centre -2.0 -1.8 --handshake data/handshake/class_door --motion-session <corrected file> --min-battery 11.4 --seconds 60 --wait 60` (with the changes of part A) | 45 min | Pass per run (spec): STANDBY, ESP32 verified, 0 collisions, tape door distance 1.5-3.0 m, clear line of sight, wall or furniture **within 1 m measured**. Record: the tape offset of the robot in x/y **before** the retract (photo of the tape) and after it, the battery, and whether R1 was released deliberately. |
| 3 | Turn per pulse, left and right, and video lag (robot still, board ahead at 1.5 m, a second board 1.5 m to the side) | `python -m tools.motion_check --label class_3 --anchors <today's csv> --spin-s 0.2 --repeats 6 --drive-s 0.6 --rest 1.5 --quad` (with change A6). Frames run at 10 fps; with A4 the `t_cap` gives the latency. | 10 min | Record: battery at start and end. Target: ≥ 10 left and ≥ 10 right pulses with a board in view before and after. Pass: left and right means compared with n ≥ 10 each. |
| 4 | Speed at two commands, to separate k from m0 | `motion_check --label class_4 --v 0.55 --drive-s 1.5 --repeats 2`, then the same with `--v 0.75`, board ahead at 2.5 m | 10 min | Record the battery. The range slope per drive gives the speed. Repeat steps 3 and 4 at the end of the session (lower voltage) if time allows. |
| 5 | Reverse speed (the retract) | `motion_check` with `--v -0.45` is not supported: add `--reverse` at home, or let deploy_live retract three times in front of a board | 5 min | Speed at v = -0.45 from the board range. The retract explains 0.26-0.27 m of the 10-30 offsets only if it is about 0.3 m. |
| 6 | Furniture at known distances, after step 1's pitch is in the pose file | `python -m tools.furniture_check --label chair_<d> --tape <d> --camera-pose <the step 1 file> --floor glossy`, with d = 0.8, 1.2, 1.6, 2.0, 2.4 m; then the big table at 1.0 and 2.0 m | 15 min | Record: frames with a detection and with a distance, and the error against the tape. On 10-30 the box bottom with the right pitch was within 0.006 m at 1.2 m (1 placement). Pass for the obstacle stop: a distance in ≥ 10 of 12 frames within ±0.15 m up to 1.5 m. |
| 7 | Part C (Phase 1 chain), only if 1-6 are done | as in the checklist | rest | |

## C. What can be done at home now, without the room

| task | data to use |
|---|---|
| Build changes A1-A9 and test them in the simulator | `tools/floor_model.py` with `floor_model_1030.json` (wheel law, spin rate, drift 0.45 ± 0.12, latency 0.12 s, overshoot) |
| Replay the board-following controller against the real sightings: when is the board lost, and what would change A1 have done? | `data/deploy/t2_3, t2_4, t2_5/servo.csv` + `log.csv`, aligned with `align_t0` |
| Look at the frames just after the board was lost (local only, faces possible) | `data/deploy/t2_3/frames` after loop t = 6.9 s, t2_4 after 7.9 s, t2_5 after 10.8 s (wall time = t0_wall + t, in `results.json`) |
| Obstacle distance from the box bottom with a live pitch from ArUco pages; known-width rule (0.446 m chair) as a fallback | `data/furniture/chair_1.2m` (12 frames, tape 1.20 m); deploy frames give the pitch (6.0-6.2 deg) |
| Tune the handshake rule against live answer rates (2.3-4.3 answers/s): subsample the trial frames to the live rate and replay | `data/handshake/class_door/trials` + `results.json` (`windowed_verify`) |
| Check MarkerFix along a real approach | `marker_fix_on_frames` on sup6 / t2_2 frames (119 / 64 fixes) |
| Update the plan, the checklist and the Week 4 log with the corrected numbers (speed 0.216-0.2245 m/s, turn 0.438 rad per pulse, latency ≤ 0.153 s, pitch 6 deg) | this folder |
