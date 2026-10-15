# Classroom session 2026-10-15 (08:00-12:00): motion model on glossy tile, tools, obstacle data

Robot: JetBot, speed cap 0.3, `min_pwm` 0.12, `calib/motion.json` unchanged. Floor: glossy polished tile. Marker: ArUco id 0, 0.150 m, standing on the floor against a board 1.7-1.9 m away. Speed and turn measured from the marker (range and bearing per frame); no tape, no protractor.
Tools (PR #40): `tools/speed_trial.py`, `tools/turn_trial.py`, `tools/motion_trial.py`, `tools/speedfit.py`, `tools/record_clip.py` (PR #42). Model code: `sentry/nav/wheel_model.py`, `sentry/nav/motion_estimator.py` (PR #40).

## Straight runs, open loop (`speed_runs/classroom_v*.csv`)
Average = net marker range change / wheel seconds from the robot's log. Steady = fit of the range series (`tools/speedfit.py`, start-up lag about 0 on this floor).
| v | battery | wheel s | distance | average m/s | steady m/s | steady per unit | marker bearing start -> at rest |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| 0.4 | 12.09 V | 4.00 | 0.572 m | 0.143 | 0.139 | 0.35 | -0.6 -> -0.2 deg |
| 0.5 | 12.14 V | 4.03 | 0.803 m | 0.199 | 0.185 | 0.37 | -0.2 -> -10.3 deg |
| 0.6 | 12.13 V | 4.06 | 0.896 m | 0.221 | 0.238 | 0.40 | +0.3 -> -7.9 deg |
| 0.7 (run 1) | 12.18 V | 3.07 | 0.849 m | 0.277 | 0.269 | 0.38 | +0.4 -> -28.7 deg (the 25 deg guard stopped it) |
| 0.7 (run 2) | 12.17 V | 3.68 | 1.088 m | 0.295 | 0.283 | 0.40 | -0.3 -> -20.6 deg |
| 0.85 (3 s) | 12.04 V | 2.97 | 1.112 m | 0.375 | 0.357 | 0.42 | -0.3 -> -9.3 deg |
| 1.0 (3 s) | 12.02 V | 2.45 | 0.994 m | 0.406 | 0.435 | 0.44 | +0.1 -> -4.0 deg |
**Fit of the steady speeds:** speed = **0.491 x (v - 0.124) m/s**, residual 0.006 m/s; a proportional law (0.408 x v) has 0.017 m/s. The old gain (0.4135 x v, calibrated at v = 1.0) over-predicts by 19 % at v = 0.4, 12 % at 0.5, 6 % at 0.6, 2 % at 0.7.
`speed_runs/lowbattery_10.97V_head_centre_v0.6_1.csv`: the same command at 10.97 V gave **0.089 m/s** (0.22 m in 2.52 wheel s), about a third of 0.24 m/s at 12.1 V: a low battery changes speed and heading, so the heading test was stopped and the robot put on charge. The offset of the fit was larger at 10.97-11.3 V on 2026-10-14 (0.146 in v, 0.044 motor units).

## In-place turns, marker bearing before / after (`turn_runs/classroom_w*.csv`)
| w | commanded s | wheel s | battery | turned | rate (per wheel second) |
| :-- | :-- | :-- | :-- | :-- | :-- |
| 1.0 | 0.15 | 0.11 | 11.98 V | +34.8 deg | 5.57 rad/s (coarse: 0.11 s of wheel time, +-27 %) |
| 1.0 | 0.25 | 0.27 | 11.82 V | +96.7 deg | 6.27 rad/s |
| 0.5 | 0.40 | 0.34 | 11.80 V | +50.8 deg | 2.62 rad/s |
| 0.4 | 0.60 | 0.65 | 11.78 V | +73.9 deg | 1.98 rad/s |
**Fit:** rate = **7.20 x (w - 0.130) rad/s**, residual 0.03 rad/s (proportional 5.94 x w: 0.36). The old gain 6.48 x w is right only at w = 1.0 and over-predicts by 33 % at w = 0.4. (The first turn file has an older column layout: bearing, not heading.)

## One wheel law (code: `sentry/nav/wheel_model.py`, tested against every point above)
wheel speed = 1.64 x (|motor| - 0.038) m/s, motor = mix(v, w) x 0.3 after the per-wheel dead zone (0.12); v = (vL + vR) / 2, omega = (vR - vL) / 0.137 m. The speed offset (0.037 motor units) and the turn offset (0.039) agree, and the two slopes are consistent with a wheel track of 0.137 m (0.128 m from the first calibration).
Model vs measured steady speeds (v 0.4 / 0.5 / 0.6 / 0.7 / 0.85 / 1.0): 0.135 / 0.184 / 0.233 / 0.282 / 0.356 / 0.430 vs 0.139 / 0.185 / 0.238 / 0.276 / 0.357 / 0.435; turn rates (w 0.4 / 0.5 / 1.0): 1.96 / 2.68 / 6.28 vs 1.98 / 2.62 / 6.27 rad/s.

## Camera pose
`camera_pose_classroom_1015.json` / `.jpg`: 3 strips (0.5 / 1.0 / 1.5 m), one click each (`measure_camera_pose --one-click`), rms 2 mm, **H 0.109 m, pitch -12.2 deg (looking UP)**, roll 0. The mount tilted during transport and is readjusted by hand each time: 5 deg down on 2026-10-14, 12 deg up today. This is why the pose is estimated live from a marker (`LiveTilt`, PR #35 merged, roll fix PR #38). **End-of-session check (11:50, `tools.preflight`, marker in view): live tilt -13.27 deg against -12.20 deg from the strips, a 1.1 deg difference (limit 1.5): the mount held for the session and the marker method agrees with the strips.**

## Heading: a left bias of about 10 deg per metre plus a random spread (11 open-loop runs)
Heading change over about 1 m, from the marker bearing corrected for the approach geometry (positive = right turn): morning (12.0-12.2 V) v 0.4 / 0.5 / 0.6 / 0.7 / 0.7 / 0.85 / 1.0: about 0, -10, -8, -29, -21, -9, -4 deg; afternoon (11.9 V), v 0.6 from the SAME centre spot: **+15 (right)** and -16 deg; from 0.4 m to the left (parallel): about -9 deg; from 0.4 m to the right (parallel): about -10 deg (`speed_runs/head_*.csv`).
**10 of 11 runs turned left or not at all, one turned right.** The size is 0-29 deg (typically 8-16), with no dependence on the start spot (left -9, centre -16 / +15, right -10) or on the speed. So: a left bias (the robot or its start-up, not one tile) of about 10 deg per metre, plus a random spread of about +-10 deg per metre. A trim could remove the mean but not the spread: the heading has to be corrected online from the marker. The marker-bearing P controller of 2026-10-14 does not hold it (about 0.5 s of steering lag); a guard of 25 deg is too tight when the marker starts off to the side (it stopped the left-start run).
Earlier text of this section (superseded): "the veer has no fixed direction" was based on two centre runs only.
Earlier open-loop runs of the morning (all at 12.0-12.2 V):
Open-loop marker bearing at rest after a drive of 1 m or less: 0, -10, -8, -29 / -21, -9, -4 deg at v 0.4 / 0.5 / 0.6 / 0.7 / 0.85 / 1.0: they all ended turned LEFT with **no trend with speed** (the earlier "grows with speed" is withdrawn), none at v = 0.4, which the two centre runs above contradict as a rule: the sign changes. The marker-bearing P controller of 2026-10-14 does not hold the heading (about 0.5 s of steering lag).

## Obstacle data
24 tape-measured rows (ids 6-29), glossy tile, one session pose: `assets/d1/obstacles_2026-10-15/` (PR #42, README inside; only the three clean chair clips in git, sets 2-4 with people at the image edge are in a private zip). Findings (issue #43): the detector finds the chairs but returns no distance for any of them (`reflection_unresolved`, all 9 placements); with all 80 COCO classes none of the 15 small or low objects was detected. A matte control, the heading test, the room sweep and empty-floor clips were not recorded (battery, time).

## Lessons
- R1 timing ruined roughly a third of the drive attempts (late, early, a chattering contact, never pressed). `speed_trial`, `turn_trial` and `motion_trial` now wait for R1 themselves (they poll the e-stop latch and start after 0.5 s held), arming is done once (any other button disarms), and the run aborts after 20 s without R1.
- A marker turns out to be a good ruler for speed (range) and for turns up to about 80 deg (bearing); the full-turn tape protocol was replaced. Several markers around the robot would measure any turn angle, but thin paper on chairs is not stable and a marker on the floor is seen at about 6 deg (5 px tall): a rigid vertical surface is needed.
- Start checks and guards (marker range, heading, lost marker) stop commands early; a start check that looks for only 0.5 s fails when someone walks in front of the board (now 2 s).
- Battery: the speed fell to a third at 10.97 V; calibration and tests at 11.8 V or more, charge before the next session.
