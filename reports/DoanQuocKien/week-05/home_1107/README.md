# Home session 2026-11-06/07 (DQK): camera check, pursuit runner first runs

Room: DQK's home, light floor with 60 cm tiles, one person (DQK), one robot. NOT classroom evidence. Operator holding the gamepad (e-stop armed, R1) was DQK for every driving run. No obstacle avoidance exists in `tools/pursue_live.py`; the floor was cleared by hand.
Logs here are numbers only (`pursuit/*/log.csv`, `summary.json`). Video frames contain a person and stay local (`data/`, gitignored).

## 1. Camera after the repair (2026-11-05, socket resoldered by a repair shop, free)
Stream works from a cold boot: `imx219 7-0010` bound, `/dev/video0`, about 19 fps, no gaps in 60 frames. `8-0010` probe error = the unused second CSI port.

`tools.self_pose --page-bottom-h 0.0`, lens fixed at 0.100 m (files in `pose/`):

| file | board distance | pitch (+ = down) | roll | spread | frames |
|---|---|---|---|---|---|
| `camera_pose_self_1030_2` (old, 10-30) | – | +2.15 deg | +2.34 | 0.024 | 45 |
| `camera_pose_self_1106_1` | nearer than 1.8 m | -4.68 | +1.03 | 0.21 | 44 |
| `camera_pose_self_1107_1` | 1.8 m | -4.49 | -2.08 | 0.06 | 40 |
| `camera_pose_self_1107_2` (after driving runs) | 1.8 m | -4.55 | +0.29 | 0.05 | 42 |

The mount moved about 6.8 deg between 10-30 and today (the repair is the probable cause; not measured in between). Today it is stable in pitch (-4.49 to -4.68, three measurements, one after driving). Roll varies by up to 3 deg between measurements and is not understood.

## 2. Floor-distance check with the tape (feet on tape marks, lens-to-feet, camera not moving)
Reading = `tools.pursue_live` ground distance of the person box bottom centre.

| mark (tape fwd, left) | runner fwd, left | pose | note |
|---|---|---|---|
| A (1.20, 0) | 1.13, 0.05 | 1106_1 | |
| B (1.20, 0.45) | 1.09, 0.39 | 1106_1 | first B run 1.11, 0.30 was a standing error |
| C (1.80, 0.65) | 1.49, 0.50 | 1106_1 | |
| 1.8 m, feet together | 1.59, 0.07 | 1107_2 | box bottom on the feet (frame checked) |
| 1.2 / 1.8 / 2.4 m (`floor_marks_1107_b_foot_pixels.json`) | 1.02 / 1.57 / 1.63 | 1107_2 | foot rows 293.9 / 283.1 / 282.4 px, each steady to 0.01 m |

Reading: the runner reads 6-17 % short up to 1.8 m, always in the same direction (safe side: it thinks you are nearer). Beyond about 1.8 m the reading hardly changes (1.57 -> 1.63 for a true 1.8 -> 2.4 m): with the lens 0.100 m high, 1 px is about 0.1 m at 1.8 m and 0.2 m at 2.4 m, so distances past about 2 m are not usable from the foot point. The box bottom sits 4.6 / 2.5 / 6.1 px below the ideal contact row at 1.2 / 1.8 / 2.4 m (about 4 px, plus detector noise of about 2 px); bare feet against a floor of similar colour add about 3 px (a dark surface moved the box bottom up 3 px; the surface was 2-3 cm thick, so that reading is not used for the offset).
Unexplained: one static check with "feet on the 1.8 m mark" read 1.20 m (sd small). Not repeated; not used.
Action: `[pursuit] feet_row_offset_px = 3.5` in `config.toml` (one floor, one person; replay of the 1.8 m frames then reads 1.93 m). It is a calibration of today's conditions, not a constant.

## 3. Pursuit runner (`tools.pursue_live`, PR #99), runs in `pursuit/`
| run | what happened | result |
|---|---|---|
| `home_dry_1` | dry-run | ended on target lost: detector warm-up stalled the first frame 4.6 s |
| `home_dry_2` | dry-run, person static | 660 frames, tracked, distance 1.0-1.2 m reported (tape: about 1.2 m forward) |
| `home_1_1`, `home_1_2` | supervised | ended after 5.6 s and 2.0 s (stall before the fix; accidental R1 release) |
| `home_1_3` | supervised, 17.9 s | closed and held (hold at 3.59 s). DQK reported the true distance about 1.8 m while the log said 1.19 m; unresolved (a later static check at 1.8 m read 1.59 m). **Distance in-band figure of this run is withdrawn.** |
| `home_2_1` | supervised, 6.8 s | yaw-only burst (minimum legal turn 0.45 = about 125 deg/s) turned the robot about 30 deg, the person was lost, run ended on the 5 s lost-target rule |
| `home_3_1` | supervised, 31.5 s | no turn bursts, one track ID, six frame gaps of 0.3-1.0 s (video stutter, robot stopped). DQK started 1.4 m away: it hardly had to move. Not a pursuit test |
| `home_4_1` | supervised, 20 s, battery 11.62 -> 11.64 V | started about 2.0 m (reported), closed to 1.34-1.41 m reported, held (TARGET_STATIONARY at 7.4 s), centred (yaw error -0.02), 73 small turn frames. **True hold distance, tape lens-to-feet: 1.25 m** (reported 1.37 m: +0.12 m, 10 % high). Within the plan's 1.2 +/- 0.2 m |

Fixes made because of these runs (all in PR #99, 9 tests): detector warm-up before R1 is needed; a frame that takes > 0.5 s is never driven on; yaw-only commands are one-frame pulses (one on, two off) with no turn inside the +/-10 % centre band; re-lock onto the ONLY person near the last position after an ID change (two people: no); all tracks logged per frame; `feet_row_offset_px`.

## 4. What this does and does not show
- Shows: lock-on, closing to the standoff, centring and the HOLD trigger on live video with legal commands, true hold distance 1.25 m once (n = 1), no stall after warm-up.
- Does NOT show: the plan's 'Pursuit PD' and 'Standoff hold' acceptance. The target mostly stood still: no step response, no walk-back, no sideways step, no hold exit, no re-centring time, no hold timing (2.0-3.0 s after the target stops) measured against the real stop time, no second person. The in-band fractions in the `summary.json` files are first-trial numbers; those of `home_1_3` and the start-near run `home_3_1` mean nothing.
- Known limits: the controller stalls 0.1-0.2 m outside the setpoint (a distance error smaller than the motors' minimum speed sends nothing: 1.37 m reported held at 1.25 m true); distance from the foot point is unreliable beyond about 1.8 m; the runner reads about +/-0.12 m between sessions; no obstacle avoidance; the video link stutters (gaps up to 1.0 s, cause not found); the antenna gap of about 26 dB (-78 vs -52 dBm) on the robot Wi-Fi is not investigated.
- Battery: 12.38 V at the start of the session, 11.62 V at the start of the last run (gate 11.4 V). Charge before the next run.

## 5. Next (home, after charging)
1. Walk-back 0.5 m and stop, then step 0.5 m sideways and stop: `python -m tools.pursue_live --label home_5 --camera-pose calib/camera_pose_self_<today>.json --save-frames`; note the real stop times and tape the true hold distance each time.
2. Re-run `tools.self_pose` first (the mount moves).
3. Fix the stall (controller dead zone) if the walk-back trial shows it matters.
