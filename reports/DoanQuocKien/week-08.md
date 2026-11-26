# Week 08 - DoanQuocKien (2026-11-23 to 2026-11-29), DRAFT of 2026-11-23

## Done
- Strike evasion override `sentry/nav/evasion.py`, `tools/pursue_live.py --evade` (key `e` injects a STRIKE), 12 tests - PR #138 (open, not reviewed). Decision C12 recorded: the 0.3 is the robot's `--max-speed` command scale, not m/s; the model values (about -0.215 m/s, 72 deg) are still NOT measured. Wheels-off trials 2026-11-23 (week-08/evasion_wheels_off_1123): commanded pulse 0.37-0.41 s (robot log), screen flash 404-421 ms; at the 0.3 cap the strike drives ONE wheel (-0.30, the other -0.033 falls under min_pwm 0.12), a reverse pivot and not a straight reverse; wheel start delay and angle NOT measured (video measure unreliable). Both wheels turn forward and in reverse at 0.30 (eyes plus robot log).
- Live window `tools/sentry_ui.py` (camera, marker overlay, tower registration wizard with the reason for every rejection; `tests/test_sentry_ui.py`); `tower_register.save_pose()` split out so both tools share it. Not committed.
- Boot power/health logger `jetson/boot_log.py` + `sentry-bootlog.service` (installed on the robot, 12 h window, `/home/jetbot/sentry/bootlog.log`). Diagnostic only; remove when the boot crashes are explained.
- Edge notes: the robot idles in 5 W mode (2 cores, 918 MHz); MAXN gives 4 cores. Recorded in `docs/Edge Deployment.md`. Not committed.

## Tests run
| Tier | Command | Result | Evidence |
| :-- | :-- | :-- | :-- |
| hil | `tools.tower_register` (via `sentry_ui`), 4 faces at 39-49 cm | camera pitch **+0.48 deg** (faces +0.17 to +0.83, spread 0.25 deg); a first fit at 13-20 cm gave +1.31 deg and is superseded. 20/11 fits were -11.67 and -11.29 deg: the mount is loose and now points about 12 deg higher | week-08/camera_pose_tower_1123_2.json (and _1) |
| hil | `tools.motion_check`, boards at 1.8 m ahead and 1.2 m ahead / 0.6 m left and right, 12.1-12.3 V, classroom floor, 2 repeats (class_1123c) | first repeat unmeasurable (the tool's own spread limits), second: spin left 1.09, spin right 0.88, forward 1.25 (drift +0.228 rad/m); a fit was written with ONE measurable segment per kind: NOT valid, do not use `calib/motion_session_1123_1.json` | week-08/motion_check_1123/class_1123c |
| hil | same, 3 repeats (class_1123d) | all 9 segments measurable; spin ratios 0.86-1.10, forward ratios 1.65 / 0.94 / 1.50, drift +0.495 / -0.078 / -0.406 rad/m: **fit refused** (scatter limit 0.15) | week-08/motion_check_1123/class_1123d |
| hil | `tools.link_cut_test --wheels-on-ground-ack`, in-place spin w 0.45, R1 held, 12.25-12.28 V, laptop path (carry-over C2) | 5 valid trials in 2 runs: stop seen 0.490 / 0.541 / 0.557 / 0.560 / 0.598 s after the last confirmed packet (median 0.56 s); limit 0.35 s NOT shown. Values are UPPER BOUNDS read from the video (include the video delay and the 0.05 s frame period). 2 further trials were invalid (R1 released at the cut) and a first run (home_1) had no camera frames: neither is evidence | week-08/link_safety_home_2, week-08/link_safety_home_3 |
| hil | wheels off the ground, `pursue_live --evade --evade-only` + phone at 240 fps (evade_2: 6 strikes), plus `send_cmd` +-1.0 for 8-10 s | robot log: strike = `motors -0.30 +0.00` for 0.37-0.41 s, one wheel only; screen flash 404-421 ms x 6; both wheels turn at equal speed forward and in reverse at 0.30 (DQK's eyes + log). Wheel delay and angle NOT measured (video measure unreliable, not used) | week-08/evasion_wheels_off_1123 |

An earlier run (class_1123, boards at 2.4 m, 18 px wide) measured nothing usable and is not kept as evidence.

## Acceptance criteria status (Implementation Plan section 4.3)
- Motion calibration (carry-over C5): NOT closed. Spin ratios scatter about +-12 % around 0.95; the forward drive was 0.68 / 0.38 / 0.62 m for the same 2 s command and the drift changes sign. In the spin segments the board-based forward position reads -0.01 to -0.26 m although the robot does not move, so the measurement noise (about 0.2 m with 25-40 px boards at 1.3-1.8 m) is as large as the 0.4 m drive. DQK decided on 2026-11-23 to stop here and report these as limits. A tape-measure forward test (5 drives, reset between them) was proposed and not done.
- Link-loss stop (C2): 0.49-0.60 s upper bound (5 valid trials) against <= 350 ms: NOT met by this method and not shown to be met; the on-robot 'Edge safety' row decides. Reported as measured.
- Camera calibration: `calib/camera.json` unchanged; pitch only (+0.48 deg), the mount is unstable (tightenable), refit after any bump.

## Blockers / risks
- **Camera slot CAM0 on the Jetson is faulty or its cable end is bad** (2026-11-23): on CAM0 the sensor probes but delivers no frames (CSI lane errors, `No cameras available`, even after reseating and a reboot); on CAM1 (`imx219 8-0010`) it streams at about 20 FPS. The camera must stay on CAM1. Cause not established. Tell the supervisor (school property).
- **Robot crashed repeatedly a few seconds after boot** (reported 2026-11-23; uptimes of 1-9 min seen all afternoon). The 6-pin cable tested fine with a DT-830 (0.1-0.2 Ω per wire after the 0.3 Ω probe offset, no break in the wiggle test); battery 12.41 V idle, 12.25 V at turn-on. A live probe slipped and caused a spark with a power drop, then the robot recovered (do not probe live pins by hand). Since then the robot ran on one boot for 48 minutes (same boot id in the log, including both motion runs; 12.09 V at the end) in 5 W mode. Cause NOT found; the boot logger is running. Tegrastats shows no 5 V input power on this L4T.
- After a power-up the camera service can fail with 'Connecting to nvargus-daemon failed: Connection refused' (seen 2026-11-23, 256 times in `camera_pub.log`); restarting `nvargus-daemon` alone did not help, `docker restart jetbot_jupyter` then `systemctl start sentry-camera` did. Cause not established.
- The robot's boot crashes may be linked to the camera slot fault: not tested.
- The unsigned control packets limit stays (no `data/control.key`, C15).

## Next week
- Stage A and the engine build wait for HNHL's ONNX; D3 and D4 need all three people.
- Evasion on the floor (Thu 11-26, tape and ruler, no video): back-up distance and turn angle per strike (not measured wheels-off), and decide the pivot design of the strike (C12: at the 0.3 cap it drives one wheel only).
- Decide whether to run the tape-measure forward test.
- Commit the uncommitted files (sentry_ui, boot logger, notes, calibration files) after the user says which ones.

## Hours
-
