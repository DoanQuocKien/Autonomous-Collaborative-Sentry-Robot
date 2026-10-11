# Week 02 – DoanQuocKien (2026-10-12 to 2026-10-18)

*Started Monday 2026-10-12 (work done on Sunday 2026-10-11 evening and Monday morning). Items marked **TODO** are not done yet; the classroom D1 session results still need adding.*

## Done
- **Fisheye calibration (T1):** `tools/calibrate_fisheye.py` (+ `tests/test_calibrate_fisheye.py`: synthetic recovery, corrupted-view drop, real-photo replay test). 58 checkerboard photos, 52 used (6 early views dropped for reprojection error > 2.5 px, limit 15 %), **RMS 0.83 px** (target < 1.0 px), odd/even half-splits stable. `fx 309.6, fy 306.2, cx 285.8, cy 239.1`, `calib/camera.json`. Evidence: `week-02/fisheye_metrics.json`, `fisheye_calibration.log`.
- **Motion calibration tool (T2):** `tools/calibrate_motion.py` (`run` records one row per trial including the seconds the wheels really turned, read from the robot's log, the battery voltage and the robot's `k` / `min_pwm`; `fit` computes the gains, drift and repeatability and refuses to write a failed fit). Cloud-review findings fixed; a Ctrl-C restart no longer resets the run count – PR #21.
- **Motion runs on the floor (cafe, speed cap 0.3, v = 1.0 only):** 5 straight runs of about 2.1 m in 5 s and 6 turn runs of 2 s. Straight: forward gain **0.414 m/s**, scatter 0.7 %; drift **-0.19 rad/m** (curves right, 0.27-0.53 m sideways over 2.1 m). Turn: **6.48 rad/s** (about 371 deg/s). Raw rows: `week-02/motion_runs.csv`. **Weak points, see Risks:** only one speed and one turn duration; the turn angles are miscount-prone (the robot spins about two full turns in 2 s) – the first set of readings was discarded and three rows were corrected from 390 to 750 deg after a recount, so the 1 % turn scatter is not a real repeatability figure.
- **Camera height and tilt:** `tools/measure_camera_pose.py` (undistort, two clicks per floor strip, fit of `d = H / tan(pitch + atan((v - cy)/fy))`, roll from the strip slopes) and `tools/tape_angle.py` (tape yaw from its vanishing point: -0.8 deg, no effect) – PR #22. Result with the camera as mounted (screw tightened): **H_cam 0.101 m** (tape 0.100 m), **pitch 2.6 deg down**, fit error 0.8 cm over marks at 0.3-2.0 m. The 1.5 m mark was excluded as an outlier (with it: rms 6.6 cm; it fits a strip at about 1.3 m). Earlier runs gave H 0.088 m / 0.9 deg: they were biased by the same bad mark and a different screw position. **Use the pitched formula**; the level-axis formula in the plan reads about 20 % too far at 2 m. Evidence: `week-02/camera_pose_nowedge.json`, `.jpg`, `_raw.jpg`. The 15 deg wedge is not needed (see Decisions).
- **Robot as a service:** `sentry-estop`, `sentry-camera`, `sentry-control` systemd units (`jetson/systemd/`, `install.sh`) deployed and tested by a reboot with nobody touching it: all three active, video 17 fps, estop log "hold Start 1.5 s to arm"; camera and control start about 1 min after boot (Docker). Arming key is now Start alone, 1.5 s, in all docs – PR #17, #18; dead-zone compensation reverted (motor value = command times max speed, `min_pwm` unchanged) – PR #19.
- **Bug found on the real robot:** `tools.jetbot_status` and the battery read in `calibrate_motion` crash because the robot's `sudo` prints `[sudo] password for jetbot:` on stderr, which ended up in the parsed output; PR #16's tests used a fake client. Fix with a regression test using the robot's real output – PR #20 (**needs a review**; until merged use the by-hand read).
- **D1 prep (Sunday):** cafe door set finished (16 rows, 1,419 manifest frames, see week 01), classroom checklist `docs/D1 Classroom Checklist.md`, `assets/d1/*_template.csv`. ESP32: OV2640 build of `esp32/sentry_cam` (JPEG VGA q12, builds, untested on a board), GC2145 tile stream kept as the working path (about 15 fps).

## Tests run
| Tier | Command | Result | Evidence |
| :-- | :-- | :-- | :-- |
| T0 | `pytest -m "not gpu and not hil"` on main (without PR #22: 197 with its tests) | 192 passed | week-02/pytest.log |
| T1 | `tools.calibrate_fisheye` on 58 photos | RMS 0.83 px (52 views) **pass** (< 1.0 px) | week-02/fisheye_metrics.json |
| T2 | `tools.calibrate_motion run` 5x straight + 6x turn, then `fit` | fit passes on paper (forward gain CV 0.7 %, turn gain CV 1.0 %) but is **not accepted yet**: only v = 1.0 measured, turn angles unreliable (see Risks); written to `calib/motion.json` and pushed to the robot as a first estimate | week-02/motion_runs.csv |
| T1 | `tools.measure_camera_pose` (6 marks, 0.3-2.0 m, 1.5 m excluded) | H 0.101 m, pitch 2.6 deg, rms 0.8 cm; **provisional** until the classroom obstacle distances confirm it | week-02/camera_pose_nowedge.json |
| T2 | Reboot test of the three systemd units | pass | this log, Done |

## Acceptance criteria status (Implementation Plan §4.3)
- Fisheye calibration RMS < 1.0 px: **pass** (0.83 px)
- Motion calibration repeatability (5 runs each of straight 1 m and 90 deg turn): **partial**. Straight passes (0.7 % gain CV). Turn passes on paper, but the angles are not trustworthy to better than 10-20 % (see Risks); the model is only measured at v = 1.0
- Obstacle distance (median error <= 10 %) and dead-reckoning error (<= 15 / 40 cm at 3 m): **not measured yet** (classroom data; HNHL / KR)

## Decisions
- Camera stays at 2.6 deg down, no 15 deg wedge: from the fisheye geometry the wedge gains about 3 cm of nearer floor and loses the torso of a person at the 1.2 m standoff (highest visible point about 1.2 m -> 0.8 m). To confirm with a 5 min field-of-view check at 1.2 m. The screw must not be touched: a movement of 1 deg changes the distance at 2 m by about 7 %.
- Arming key is Start held 1.5 s (user decision, PR #18); no dead-zone compensation (PR #19); the usable v range is therefore 0.4-1.0 at speed cap 0.3.

## Blockers / risks
- **Motion model measured at one speed (v = 1.0, motor 0.30) and one duration:** the fit assumes speed proportional to command through zero. A motor dead zone would give an offset: at v = 0.4 (motor 0.12) the real speed could be about half of the predicted 0.17 m/s. Spin-up and coast are hidden by 2 s runs. To measure after the classroom session (straight v = 0.4 / 0.7, turn w = 1.0 for 0.5 s and w = 0.5 for 1.5 s), then extend `fit` with an intercept.
- **Drift to the right, 0.19 rad/m at v = 1.0** (about 22 deg of heading over 2.1 m): not compensated anywhere yet; dead reckoning must add it or the motor mix needs a trim; may depend on speed and on the floor (the first floor test drove straight). KR's localization needs this.
- **Turn angles by eye:** two full turns in 2 s; use short turns (about 190 deg) for the next set.
- **Camera pose is one run** with one mark dropped after seeing the data; the obstacle metric on the classroom data is the independent check of H_cam. Do not move the camera screw.
- **Battery:** 11.14 V on Monday morning after about 1.5 h on; charge before the classroom session (target 12.4 V).
- **PR #20 and #21 / #22 need a review** (branch protection). KR has not sent a sensor PID answer or a weekly log; no reviews from KR yet.
- Open from week 1: ORB entrance matching on a glass door (risk 14; classroom door is the real test), OV2640 not arrived (ESP32 door view), the second ESP32 board's Wi-Fi problem (risk 13).

## Next week
- Monday: classroom D1 session (`docs/D1 Classroom Checklist.md`): doorway set, the 20 tape-measured obstacles (checks H_cam and pitch), room sweeps, motion + markers dataset at v = 1.0, 0.7 and 0.4; `tools.d1_manifest` per door; back up `data/D1`.
- After the session: the short motion runs, the speed-dependent fit, drift compensation; update the Implementation Plan (pitched ground-plane formula, `calibrate_motion` status) and tell HNHL the camera pose (`calib/camera_pose_nowedge.json`).
- OV2640: flash `esp32/sentry_cam` when it arrives, expect `PID=0x0026`, measure fps, re-record the door view.
- Week 3 (DQK): USB speaker playback and the deployment behaviour; both need the motion model above.

## Hours
- **TODO**: estimate from chat timestamps at the end of the week.
