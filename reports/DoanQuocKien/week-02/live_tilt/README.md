# Live camera tilt, drive runs (2026-10-13/14, classroom, JetBot, matte-white wall marker)

Marker: ArUco `DICT_4X4_50` id 0, black square 0.150 m, lower edge 0.132 m above the floor (A4 page standing on the floor, the print layout of `tools/make_markers.py` fixes it; measured 0.135 with the paper's few mm).
Reference tilt: `../camera_pose_tilt_ref.json` (3 tape strips at 0.5, 1.0, 1.5 m: H 0.097 m, **5.03 deg down**, rms 1.5 cm, so only about +-0.5-1 deg).

## What each run measures
For every frame the marker pose (PnP, independent of the tilt) gives the TRUE ground distance to the point where the wall meets the floor under the marker (along the robot heading). The same pixel is then converted to a distance twice with `CameraGeometry.ground_point`: with the **fixed** strips tilt (5.03 deg) and with the **live** tilt (`LiveTilt`, `sentry/perception/camera_pose.py`). Columns: `t, true_fwd, fixed_belief, live_belief, live_pitch, left, perp` (servo files also `bearing, w, omega_int`). Distances in m, angles in deg.
A tape reading at the first stop (0.64 m) agreed with the marker pose (perpendicular 0.62-0.65 m).

## Runs
| File | Speed | Filter window | Notes | Median abs error, whole run: fixed / live |
| :-- | :-- | :-- | :-- | :-- |
| run 1 (rows not kept) | v 0.4 | 15 | started 2.0 m; veered right 0.38 m | 0.181 / 0.076 m |
| run 2 (rows not kept) | v 0.4 | 15 | straight | 0.084 / 0.025 m |
| run 3 (rows not kept) | v 0.7 (0.29 m/s) | 15 | stood about 9 s at 2 m before R1; veered right 0.52 m | 0.439 / 0.061 m (dominated by the standing phase; moving: live 20 % off, no better than fixed) |
| `run4_v0.7_rows.csv` | v 0.7 | 15 | frames recorded; veered right 0.15 m | window replay below (whole-run median not computed) |
| `run5_v0.4_rows.csv` | v 0.4 | 5 | started 2.37 m; frames recorded | 0.216 / 0.177 m |

Window replay on the recorded frames (median abs error while moving; fixed tilt for reference): run 4: fixed 0.093; window 15 / 9 / 5 / 3 / 1 = 0.061 / 0.042 / 0.036 / 0.037 / 0.029 m. Run 5: fixed 0.207; window 15 / 9 / 5 / 3 / 1 = 0.310 / 0.315 / 0.194 / 0.126 / 0.110 m. `LiveTilt` default is now a median of 3 frames.
Standing at 2.0-2.4 m the live tilt removed most of the fixed tilt's error (run 5: fixed +0.92 m = +39 %, live +0.11 m = +5 %; run 3: -0.44 m vs -0.06 m), but at 2 m the marker is small and the estimate is the noisiest part. One run per setting, one floor, one marker: a direction, not a measured figure.

## Steering runs (marker kept centred while driving to the 0.5 m mark)
| File | Setting | Result |
| :-- | :-- | :-- |
| `servo1_rows.csv` | v 0.6, Kp 1.5, start 2.0 m, bearing +5.8 deg (0.21 m aside) | bearing RMS 0.76 deg, max 2.9 deg after the first 2 s; ground distance median error fixed 0.053 / live 0.017 m; stopped 0.446 m from the wall (live belief 0.459 vs truth 0.453) |
| `servo_partial_rows.csv` | v 0.6, Kp 1.5, start bearing +26.8 deg | stopped by the guard after 0.4 s of motion (marker blurred out for 0.3 s); the robot had turned about 19 deg in about 0.5 s |
| `servo2_rows.csv` | v 0.6, Kp 0.8, lost-marker allowance 0.5 s, start bearing +30.7 deg (1.04 m aside), battery 10.97 V | R1 pressed at t = 17 s (first 14 s are standing rows, ignore the printed run totals); bearing +30 to about 0 in about 2 s, then within +-2.6 deg; stopped 0.444 m from the wall, lateral 0.0 m, bearing -0.7 deg; live belief 0.458 vs truth 0.454 m |
Turn rate check (hand-timed, rough): commanded w 0.108 = 0.70 rad/s = 40 deg/s; measured about 30-35 deg/s (75-90 %), low battery. A clean `w_gain` check needs the in-place test (`scripts/turn_test.py`, not yet run on the robot: logic checked offline with a simulated plant).

## Findings
- Tilt differs between floor spots by up to **1.7 deg** (4.3 to 6.0 deg) and by about 0.3 deg per cm of repositioning: the chassis follows tile edges under a 10 cm wheelbase. A fixed tilt cannot be right everywhere (ground distance error 14-39 % at 1-2.4 m in these runs).
- The geometry's **camera roll** (-1.85 deg in the pose file, from tape-strip clicks) is wrong: at a 27 deg bearing it makes the wall-base distance 2.87 m instead of 1.86 m (+54 %); roll 0 gives 1.92 m (+3 %). Open: replace it with a measured value.
- Code issues found and fixed on the way (PR #32): ArUco corners were whole pixels (0.19 deg steps; now sub-pixel); off-axis markers use the filter's roll (the marker's own roll is poor off-axis); detection in the raw fisheye frame (the remapped image loses markers beyond about 25 deg); window 15 lagged about 1 s.
- An Opus agent checked the calibration (58 views, leave-one-out, 7 variants), the OpenCV 5 fisheye functions and undistort-then-detect against detect-then-undistort: no bug in them (the 1 m jump was the robot's own tilt at that spot).
- Safety lesson: `v < 0.4` is a clean stop at speed cap 0.3 (motor value below `min_pwm` 0.12): the first drive attempts sent v = 0.3 and could not move. A guard that allowed 1.5 s without a marker let one run drive 1.3 m past its stop (0.33 m from the wall, no contact); guards now stop commands after 0.3-0.5 s without a detection.
- Battery: 12.31 V at the start of the session, 10.97 V at the last run (LOW, above the 10.5 V stop line); charge before the next session. The turn gain was calibrated at 11.7-12.1 V.

Raw frames of runs 4, 5 and the servo runs (about 700 JPEGs) are kept locally, not in git.
