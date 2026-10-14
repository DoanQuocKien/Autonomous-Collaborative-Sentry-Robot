# Motion on a second floor (rugged, hard carpet-like), 2026-10-14/15

The first motion set (v 1.0, cafe) and the classroom drive runs were on smooth / glossy floors. This floor is slightly rugged, like a hard carpet with a cloth texture. Same robot, battery 12.2-12.3 V during the runs below (11.8-12.0 V under load in the tape runs), speed cap 0.3, `min_pwm` 0.12, `calib/motion.json` unchanged (no trim on the robot: the robot's log shows equal wheel values).

## Straight runs, tape (`../motion_v07_rugged_tape.csv`, run by `scripts/motion_trial.py`, operator measured with a string between two crosses)
v = 0.7, 4 s commanded, five runs: wheel time 3.85-4.03 s, forward 0.785-0.83 m, **0.204-0.209 m/s per wheel second (CV 0.8 %)**, sideways +0.00 to +0.08 m (left). The old model predicts 0.289 m/s (0.4135 x 0.7).

## Straight runs, marker as the ruler (`speed_runs/`, `scripts/speed_trial.py`; ArUco id 0 at the far end, start about 1.9 m)
Average speed per wheel second = net marker range change / wheel seconds from the robot's log. The continuous fit of steady speed and start-up lag is NOT reliable on this floor (the marker is found only 2-6 times a second while the robot moves, 17-20 when it stands closer), so only the net displacement is used.
| v | run | distance | wheel time | average speed | glossy-floor line 0.48 (v - 0.146) |
| :-- | :-- | :-- | :-- | :-- | :-- |
| 0.5 | open loop | 0.53 m | 3.88 s | 0.137 m/s | 0.170 |
| 0.6 | open loop | 0.64 m | 3.94 s | 0.162 m/s | 0.218 |
| 0.6 | marker-steered, gain 0.8 | 0.735 m | 4.01 s | 0.183 m/s | 0.218 |
| 0.6 | marker-steered, gain 2.5 | 0.782 m | 4.00 s | 0.195 m/s | 0.218 |
| 0.7 | open loop | 0.87 m | 3.98 s | 0.219 m/s | 0.266 |
| 0.85 | open loop, **hit a bean bag** | 0.92 m | 4.04 s | (0.228, cut short, not used) | 0.338 |
(`rugged_v0.7_disturbed.csv`: the robot was moved before the recording ended; not used.) Rugged / glossy about **0.75-0.9, typically 0.8, for the 4 s average from rest**. **Caveat added 2026-10-15:** replaying the same runs through `sentry/nav/motion_estimator.py` (PR #40), the *steady* speed on the rugged floor comes out at 0.9-1.08x the glossy line (v 0.5: 0.154 m/s; the two marker-steered v = 0.6 runs: 0.233 and 0.236 m/s against 0.218). So the lower averages are probably a start-up lag of 0.5-1 s (static friction), not a lower steady speed. Not shown yet: the duration test (v = 0.7 for 2 s and 6 s) is in the 2026-10-15 session plan.
The glossy-floor line comes from marker-range fits of the classroom drive runs (steady speed 0.122 / 0.212 / 0.260 m/s at v 0.4 / 0.6 / 0.7, battery 10.97-11.3 V) plus the cafe v = 1.0 gain 0.4135 m/s: all four points lie on speed = 0.48 x (v - 0.146); the proportional model `v_gain * v` over-predicts by 35 % at v 0.4, 16 % at 0.6, 9 % at 0.7.

## Heading: open question
In the unsteered runs the marker bearing ends 22-49 deg to the right (the robot's heading turns left by that much over 0.5-0.9 m), far more than the start aim (-2.4 deg) can explain (about -4 deg for a straight line). In the v = 0.5 run about 17 of the 20 deg come in the first 0.45 m of motion. Candidate causes, NOT separated: (a) a start-up swerve from static friction (one wheel breaks free first), (b) floor unevenness steering the chassis (the last steered run ended turned to the RIGHT, +10 deg, which a constant wheel mismatch does not explain, but a P controller with about 0.5 s of lag can overshoot), (c) a wheel mismatch. The tape runs from the same cross showed only 0-0.08 m of sideways drift. A separating test (same command from three start spots / headings) was not run. The marker-bearing P controller (gain 0.8, then 2.5) did not keep the marker centred: the robot answers steering with about 0.5 s of lag.

## Turn gain: inconclusive
`scripts/turn_test.py` (stop-and-look pulses of w 0.5, marker bearing as the sensor) was run twice. The first run was spoiled by R1 not being held (several cycles with no motion). The second, with the robot's log read after every pulse: one clean cycle gave 14.2 deg in 0.142 s of wheel time (54 % of the nominal rate for w 0.5), another 21 deg in 0.130 s (87 %), but other cycles are not physical (36 deg from 0.023 s of wheel time; 0.306 s logged for a 0.067 s command): the robot was probably touched or the log and the camera were out of step. **No turn gain is derived.** Next time: tape + protractor with w 1.0 for 0.5 s and w 0.5 for 1.5 s (the original protocol), where R1 only has to be held once.

## Lessons
- The first speed trials sent straight commands with no steering and a guard that only watched the marker range: the robot veered into a bean bag (v 0.85, no damage reported). Drive tests need the surroundings cleared, a heading guard and a start check.
- A missed R1 hold looks like a floor effect in the data. `moving_s` from the robot's log (calibrate_motion) is the check; the turn test now flags pulses whose wheel time is under half of the commanded time.
- The floor changes the speed by about 20 % and the heading by tens of degrees, so a single calibrated profile cannot be right everywhere: the case for estimating speed and heading online from the marker (design in the Week 2 log, not built yet).
