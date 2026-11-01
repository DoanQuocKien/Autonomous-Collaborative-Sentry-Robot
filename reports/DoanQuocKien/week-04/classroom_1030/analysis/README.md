# Classroom 2026-10-30: analysis of every saved run (DQK data, analysed at home on the laptop)

Every number below comes from `python -m tools.analyse_classroom_1030 [--yolo]` (writes `results.json`, `catalogue.csv`, the PNG and the two model JSONs in this folder), except where a source file is named. No robot, no network, no raw file changed. Frames were read on the laptop for marker bearings, pitch and the furniture check only; none is copied here.
Words used: **measured** = computed from the files named; **probable, not proven** = consistent with the data but another cause is not excluded; **n** = number of independent items (pulses, segments, runs); **sd** = sample standard deviation; **CI** = 95 % interval of the mean (1.96 sd / sqrt n) unless stated.
The session's tape answers (offsets from the sweet spot, door distance) are from `../README.md` and are treated as true; their axes were not recorded.

## Findings first (one page)

| # | Finding | Numbers (source) |
|---|---|---|
| 1 | **The steady drive speed hardly changed. The 0.65-1.03 "speed ratio" printed by `servo_motion` does not measure speed.** It fits one line through every drive row of the run, and those rows come from several drives with spins and stops between them. | Per-drive range-slope fit, v = 0.55: sup4 0.2239, sup5 0.2244, sup6 0.2245 m/s (11.58-11.70 V); t2_1 0.2159, t2_2 0.2156 m/s (11.39-11.44 V). SE ±0.0010-0.0015 each, 81-138 sightings over 4.0-6.9 s. That is -3.9 % (0.0087 ± 0.0019 m/s). Measured / default wheel model = 1.04-1.08. t2_3/t2_4/t2_5 have no drive that qualifies (≥ 15 sightings over ≥ 2 s). |
| 2 | **The large tape misses are the runs that lost board 2 and finished on dead reckoning.** | Board arrivals (sup4, sup5, sup6, t2_1, t2_2) stopped 0.814-0.850 m from the board (target 0.87). Tape offsets: 0.26, 0.27, < 0.04 m. Dead-reckoning arrivals: board 2 last seen at 1.80 / 1.82 / 1.41 m, then 3.6 / 4.4 / 6.0 s and 0.79 / 0.92 / 0.97 m of driving with no board in view (0 board detections in 69 / 84 / 81 frames). Tape offsets: t2_3 0.39, t2_4 0.80, t2_5 1.14 m. **Why the board was lost is not found** (see 8). |
| 3 | **Turn per 0.2 s spin pulse = 0.438 rad (25.1 deg), sd 0.030, n = 12 right pulses, CI ±0.017.** The provisional right-turn scale 0.79 is wrong. It came from one noisy marker-yaw reading. | Default wheel model 0.4645 rad (measured / model 0.94). Provisional right model 0.385 rad: it predicts 12 % too little. Total turn = 2.395 rad/s × (T - 0.017 s) for spin lengths T = 0.2-0.82 s (n = 20). class_1 spin_right_1 from the same board's bearing: 0.921 rad (52.8 deg) against the model's 0.948. The tool's -41.4 deg came from the marker yaw. |
| 4 | **The video lag is under 0.16 s, not "about a second".** `servo_motion`'s turn ratio is invalid for another reason. No frame received during a 0.2 s pulse shows the turn: frames stay unchanged 0.06-0.17 s after the pulse starts, and frames during the motion give no detection. | Earliest frame showing the final bearing: 0.153 s after a pulse end (best pulse; mean 0.217, n = 14). Last unchanged frame: 0.064-0.165 s after a pulse start (mean 0.124, n = 13). Drive onset: 0.137 s (sd 0.105, n = 7). One exception: sup5 at 1.4 s, where frames look 0.5-0.7 s stale at the start of the run (probable, not proven). |
| 5 | **Heading drift is to the LEFT, +0.38 rad/m steady (sd 0.12, n = 5 runs), +0.57 rad/m on drives from rest (sd 0.10, n = 4).** The provisional +0.45 sits between the two. As a mean it is justified; the run-to-run spread is not modelled. | Steady value: the steering the board controller needed (mean w -0.012). Drives from rest: class_1/class_2 forward drives, bearing geometry. |
| 6 | **The camera pitched 6.0-6.2 deg down from 11:10 to 11:52, not the 2.15 deg in `calib/camera_pose_self_1030_2.json`.** With the marker pitch, the chair box bottom gives 1.194 m against the tape's 1.20 m. **The box did not cut off the legs** (the "probable cause" in `../README.md` is withdrawn). | Pitch from the ArUco page next to the chair: 6.21 deg (sd 0.12, 12 frames). Deploy runs: 6.00 / 6.04 / 6.03 / 6.09 / 6.14 deg (sup5, sup6, t2_1, t2_3, t2_5). The glossy-floor reflection estimator puts the contact at row 221 instead of 231: 1.96 m even with the right pitch. |
| 7 | **The 2.4 m chair is missed by the detector itself, not by the confidence threshold.** | YOLOv8n found nothing at confidence ≥ 0.05 in all 12 frames (classes 56/57/59/60). At 1.2 m the chair was 115 × 210 px with confidence 0.49-0.86. |
| 8 | **t2_5 stopped 3.28 s after the vantage, not 6 s.** The "R1 released at 22.9 s" is the ENDED print time, which includes 2.27-2.77 s of shutdown in every run. With all 47 answers in view, the rule failed on the number or freshness of the answers, not on the in-view share (proven from the code, see 8b). | Prompt to verified in the other runs: 0.94-2.10 s. Detector rate over the whole run: 2.29 answers/s in t2_5 (the lowest), 2.97-4.27 in the others. |
| 9 | **The 0 marker fixes are not caused by `--motion-session`.** The premise that sup3 / dry_fix_1 had no spin pulses is false: both logs show 3 pulses of 0.20 s with 0.5 s pauses. | Control-loop replay with the same fake fix feed: 23 fixes without the session, 18 with it. dbg2_1 = 0 is explained: its board was at 1.95-2.0 m, beyond the 1.5 m limit set at 10:52. MarkerFix on the saved approach frames gives 119 / 281 (sup6) and 64 / 320 (t2_2) fixes. sup3 and dry_fix_1 remain **unexplained** (no frames were saved before 11:10). |
| 10 | **Time to the vantage (10.6-16.9 s) depends on the number of spin pulses and on the blind drive, not on speed.** | Drive time was 8.1-9.0 s in every run except t2_5 (11.1 s). Spin pulses: 4-11 per run, about 0.71 s each including the pause. |
| 11 | **The Part A windowed rule (5 s / 6 answers / 70 %) is not proven safe.** Replayed on all the dense trial frames, it accepts 7 of 10 accept trials and correctly rejects 6 of 10 reject trials. Four reject trials verify within 1.9-2.2 s on a short in-view burst. | Live, the rule never verified with the ESP32 aimed away, but those runs had 0 % in view: a burst was never tested live. |

The two model files are `speed_vs_battery.json` and `floor_model_1030.json` (loader: `tools/floor_model.py`). The next-session protocol is `next_session_1109.md`; the file list with hashes is `catalogue.md` / `catalogue.csv`.

---

## 1. Data catalogue
See `catalogue.md`: 132 entries, sha256 of every CSV/JSON in `catalogue.csv`. 4 901 frames (99 MB) stay local.

## 2. Speed vs battery (`speed_vs_battery.json`, `speed_and_turn_vs_battery.png`)
Method: for each drive (cmd_v = 0.55 in log.csv, after aligning servo.csv to it), a line fit of range against time over [start + 0.8 s, end + 0.15 s], divided by cos(mean bearing). The loop start on the wall clock comes from a vote over all command changes recorded in both files (14-133 of 15-135 recorded changes agree per run, best-offset spread ≤ 0.012 s).

| run | battery V (start → end) | speed m/s ± SE | sightings / span | old `speed_ratio` |
|---|---|---|---|---|
| sup4 | 11.704 → 11.688 | 0.2239 ± 0.0012 | 92 / 4.6 s | 0.936 |
| sup5 | 11.648 → 11.640 | 0.2244 ± 0.0010 | 135 / 6.9 s | 1.027 |
| sup6 | 11.584 → 11.600 | 0.2245 ± 0.0012 | 138 / 6.9 s | 1.028 |
| t2_1 | 11.444 → 11.432 | 0.2159 ± 0.0015 | 81 / 4.0 s | 0.748 |
| t2_2 | 11.396 → 11.384 | 0.2156 ± 0.0012 | 112 / 6.2 s | 0.931 |
| t2_3 / t2_4 | 11.36 / 11.31 | no qualifying drive (board seen 3.9-4.9 times/s against 10-15) | | 0.802 / 0.717 |
| t2_5 | 11.284 → 11.280 | 0.2136 ± 0.0186 (1 drive, 1.05 s: **not used**) | 15 / 1.0 s | 0.652 |
| class_1 forward 1/2 (11.6 V, open loop from rest) | | 0.227 ± 0.015, 0.182 ± 0.007 (board 0, 9-12 moving frames) | | |
| class_2 forward 1/2 (11.2 V) | | 0.194 ± 0.018, 0.123 ± 0.021 (9 frames each, includes start-up) | | |

Fit, wheel law `speed = k (motor - m0)`, today's 5 runs, one command (motor 0.165):
- **Option a (k = 1.64 fixed): m0 = 0.0314 - 0.0203 (V - 11.5)** motor units. Residual sd 0.0011. Bootstrap 95 % CI of the slope: -0.029 to +0.0035, which includes 0. With 5 points this bootstrap is rough; the two-group difference above is clearer.
- **Option b (m0 = 0.038 fixed): k = 1.725 + 0.262 (V - 11.5)**.
- Speed at v = 0.55 from both options: 0.2092 / 0.2125 / 0.2158 / 0.2191 / 0.2225 / 0.2258 m/s at 11.2 / 11.3 / 11.4 / 11.5 / 11.6 / 11.7 V. The full table is in the JSON.

**What the data cannot separate:**
- (a) from (b): every run used the same command. The options differ only at other commands; option a predicts a 2-3 % faster spin at the top voltage.
- Voltage from time in the session: the voltage fell steadily, so motor warm-up or floor dust are confounded with it.
- Today from Week 2: Week 2 (12.0-12.2 V) gives m0 = 0.038, **higher** than today's 0.031 at 11.5 V. Across the two days the offset did not grow as the voltage fell; combined fit: slope +0.006 per V, CI -0.003 to +0.021.

The README's "falling trend 1.03 → 0.65" is an artefact of the `servo_motion` method (finding 1), not a battery effect.

## 3. Turning (`results.json` → `turning`, `turn_vs_duration`, `motion_check`)
Method: still-to-still bearing change of board 2 for each approach pulse with a still pause (≥ 0.4 s) before it and no command until the next one. turn = -(bearing after - bearing before). Excluded:
- sup5 1.42 s: -1.03 rad. The "before" frames look stale (two pulses in one).
- t2_1 14.37 s: 0.007 rad. A turn-to-centre pulse with no visible turn.
- Every pulse that followed a drive: no still "before" bearing.

The camera sits ahead of the axle, so a bearing change differs from the heading change by about (d/r) × cos(bearing) ≈ 1-3 % (d about 0.06 m: an assumption).

| set | n | mean | sd | min-max | model |
|---|---|---|---|---|---|
| right pulses, 0.20-0.21 s | 12 | **0.438 rad** | 0.030 | 0.394-0.487 | default 0.4645; provisional right 0.385; Week 2 fit 7.2 (w - 0.13) gives 0.461 |
| left pulses | 2 | 0.494 | 0.079 | 0.438-0.550 | provisional left 0.488 |
| class_1 0.41 s spins, same board 0 | 1 L, 1 R | 0.955 L, 0.921 R | | | 0.948 |
| class_2 0.82 s spins, cross-board, repeat 1 only, robot assumed at (0, 0), board 3's position assumed (±0.09 rad) | 2 L, 2 R | 2.079, 1.905 L; 1.877, 1.819 R | | | 1.90 |

- All 20: **turn = 2.395 rad/s × (T - 0.017 s)** for w = 0.45, T = 0.2-0.82 s, battery 11.2-11.7 V.
- Turn against battery: r = -0.10 (14 pulses): no trend seen.
- **Left against right: not distinguishable** (2 left pulses).
- The tool's class_2 rest-pose ratios (0.80-1.20) scatter because of marker yaw at 2-2.7 m. The bearing method gives 0.95-1.09 of the model.
- Video lag bounds: see finding 4. Measuring it properly needs the frame capture time (`t_cap` in the ZMQ header, not saved), see `next_session_1109.md`.

## 4. Drift / straightness
| source | n | drift rad/m (left +) | method |
|---|---|---|---|
| servo drives (closed loop, steady part) | 5 runs | **0.384**, sd 0.119 (0.311, 0.337, 0.311, 0.366, 0.593) | drift rate = -d(bearing)/dt - model turn rate of the steering command + v sin(b)/r, divided by the measured speed. Mean steering w -0.012 (sd 0.003). |
| class_1 forward 1, 2 (11.6 V) | 2 | 0.456, 0.534 | board 0 bearing and range before / after, constant-curvature lateral offset. Tool: 0.50, 0.41 |
| class_2 forward 1, 2 (11.2 V) | 2 | 0.686, 0.596 | same method. Tool: forward_2 -0.04 with "0.49 m": the range geometry says **0.30 m** (1.5 s), so the tool's ratio of 1.59 is marker noise |

All 9 values are left and nothing turned right. +0.45 is justified as a mean for this floor and pack. The sd of 0.12 between runs means a 1 m blind drive misses by about ±0.06 m of lateral offset per 0.12 rad/m. The drift was not separable by battery: all runs fall in 11.3-11.7 V.

## 5. Stopping accuracy
| run | arrival | last range before the vantage | range after the stop (n frames) | overshoot | tape offset at the end | retract after? |
|---|---|---|---|---|---|---|
| sup4 | board | 0.839 | 0.818 (9) | 0.052 | "rather accurate" | no (R1 released) |
| sup5 | board | 0.871 | 0.850 (6) | 0.020 | "correct" (no cm) | no |
| sup6 | board | 0.847 | 0.814 (8) | 0.056 | 0.26 | yes |
| t2_1 | board | 0.858 | 0.829 (2) | 0.041 | 0.27 | yes |
| t2_2 | board | 0.851 | 0.824 (9) | 0.046 | < 0.04 | no |
| t2_3 | dead reckoning | 1.802 (3.6 s before) | - | - | 0.39 | yes |
| t2_4 | dead reckoning | 1.819 (4.4 s before) | - | - | 0.80 | yes |
| t2_5 | dead reckoning | 1.414 (6.0 s before) | - | - | 1.14 | no |

- **Overshoot: 0.043 m (sd 0.014, n = 5) at 0.215-0.225 m/s, i.e. 0.195 s of driving.** This matches speed × (lag + stop) from section 3.
- **Proposed rule: stop when range ≤ target + v × 0.20 s** (0.044 m at 0.22 m/s; scale it with the speed table at other voltages).
- The tape offsets of the board runs that then retracted (0.26, 0.27 m) are about the retract itself: v = -0.45 for 2.03 s ≈ 0.31-0.35 m on the model at today's speed scale (the reverse speed was **never measured**). t2_2, with no retract, was within 0.04 m. Probable, not proven, because the axes of the tape answers are unknown.
- **The offset depends on the arrival mode, not on the battery.** Board arrivals: 0.26 / 0.27 / < 0.04 m at 11.4-11.6 V. Dead-reckoning arrivals: 0.39 / 0.80 / 1.14 m at 11.28-11.36 V. The voltage and the arrival mode go together in this session, so it is not proven that the voltage played no part.

## 6. Run timing and phases (all runs)
| run | V start | vantage s | spin pulses / drive s (drives) | first sighting s | sightings/s | prompt → verified s | ESP answers/s | in view | loop end s (log) | ENDED print s |
|---|---|---|---|---|---|---|---|---|---|---|
| rehearsal_class_1/2 (no robot) | - | 13.84 / 13.85 | 0 / 13.8 (1) | | | 0.11 / 1.45 | 3.79 / 5.02 | 62/62, 84/89 | 15.95 / 17.33 | |
| dry_negative_1 (old rule 3 s/10/70 %) | 11.80 | 14.36 | 1 / 13.9 | | | never in 45.6 s | 1.54 | 3/93 | 60.0 | |
| dry_positive_1 (old rule) | 11.80 | 14.34 | 1 / 13.9 | | | 8.42 | 2.38 | 60/60 | 24.8 | |
| sup1 | 11.69 | 14.35 | 1 / 13.9 | | | - | 4.27 | 63/63 | 14.35 | 16.8 |
| sup2 | 11.70 | 8.31 | 1 / 7.7 | | | 2.03 | 3.13 | 40/40 | 12.37 | 14.7 |
| dry_fix_1 | 12.16 | 9.32 | 3 / 7.7 | | | 0.95 | 3.47 | 44/44 | 12.30 | 14.6 |
| dbg_1 | 11.62 | - | 34 / 14.0 (29) | | | - | 3.43 | 70/70 | 20.0 | 22.3 |
| sup3 | 11.62 | 9.31 | 3 / 7.7 | | | 1.52 | 1.59 | 21/21 | 12.83 | 15.1 |
| dbg2_1 | 12.08 | 9.32 | 3 / 7.7 | | | 1.56 | 3.22 | 40/40 | 12.03 | 14.3 |
| sup4 | 11.70 | 11.53 | 6 / 8.65 (4) | 0.51 | 11.5 | - (not aimed) | 1.57 | 0/29 | 18.1 | 20.4 |
| sup5 | 11.65 | 10.82 | 4 / 8.34 (2) | 1.10 | 14.9 | - (not aimed) | 3.65 | 0/59 | 15.8 | 18.1 |
| sup6 | 11.58 | 10.75 | 4 / 8.54 (2) | 0.44 | 15.4 | 0.94 | 2.97 | 42/42 | 13.7 | 16.0 |
| t2_1 | 11.44 | 13.63 | 9 / 8.98 (5) | 1.11 | 10.1 | 2.10 | 3.41 | 62/62 | 17.8 | 20.1 |
| t2_2 | 11.40 | 11.72 | 5 / 8.89 (3) | 0.39 | 13.5 | - (not aimed) | 3.58 | 0/57 | 15.5 | 17.9 |
| t2_3 | 11.36 | 10.55 | 5 / 8.15 (3) | 0.41 | 4.9 | 1.63 | 3.56 | 52/52 | 14.2 | 16.5 |
| t2_4 | 11.31 | 12.28 | 8 / 8.72 (6) | 0.46 | 3.9 | 1.21 | 4.27 | 68/68 | 15.5 | 18.0 |
| t2_5 | 11.28 | 16.85 | 11 / 11.15 (6) | 1.46 | 4.4 | none in 3.28 | 2.29 | 47/47 | 20.1 | 22.9 |

- Robot video: 18.2-20.1 frames/s received, no repeated frames (all frames unique by md5).
- Battery change within a run: ≤ 0.02 V, except sup2 (-0.16 V) and sup1 (+0.04 V).
- The dry runs read 12.08-12.16 V between motor runs at 11.6 V: **probably on the charger** (DQK at 10:56: "partly charged"), not proven.
- Part A at the door (`data/handshake/class_door/results.json`):
  - Primary rule (half the frames): 7/10 accepts, 9/10 rejects.
  - 3 consecutive frames: 10/10 accepts, 3/10 rejects.
  - Windowed rule replayed on all frames: 7/10 accepts, 6/10 rejects (finding 11).
- Cafe rehearsal 2026-10-28 (`../../handshake/README.md`): 9/10 accepts, 10/10 rejects.

## 7. Obstacles / furniture
Geometry (`calib/camera.json`, H = 0.100 m). Principal row 239.1, fy 306.2. Every row below is in the rectified image at column 272.

| | pose file, pitch 2.15° | marker pitch 6.21° |
|---|---|---|
| horizon row | 227.1 | - |
| expected floor-contact row at 1.2 m / 2.4 m | 252.6 / 239.8 | **230.8 / 218.1** |
| chair box bottom (YOLO, median of 12) | 231 → above 5 m = "no_ground_intersection_or_out_of_range" | **231 → 1.194 m (tape 1.20)** |
| reflection estimator contact (glossy mode) | row 221 in 12 / 12 frames | row 221 → 1.96 m (wrong by +0.76 m) |
| sensitivity | 0.045 m/px and 0.21 m/deg at 1.2 m; 0.175 m/px and 0.71 m/deg at 2.4 m | 0.046 m/px at 1.2 m; 0.174 m/px at 2.4 m |

The reflection estimator only searches above the box bottom (`sentry/perception/contact.py`: from bottom - min(24, h/2) to bottom - 2). So on this floor it can only move the contact up, which makes the distance longer.

**Simple rules that would give a usable distance here:**
1. Box bottom on a glossy floor too, with the **live pitch from an ArUco page** (it was correct to 0.006 m at 1.2 m). Expect about ±0.05 m per pixel at 1.2 m and ±0.17 m per pixel at 2.4 m.
2. Known chair width: the box is 115 px wide at 1.2 m, which gives 0.446 m by the pinhole model. Then d = fx × 0.446 / w_px. This is **calibrated on one frame of one chair and not validated**.

At 2.4 m nothing was detected, so neither rule applies. The probe frames (2) have no detection, and the big table was not tested.

## 8. Unexplained items
**(a) 0 marker fixes (sup3, dry_fix_1).** Code at each run, from the session transcript (`~/.claude/projects/.../68b819fd-....jsonl`):
- MarkerFix was written at 10:48:23 with max_range 2.5 m and median 3. The get_fix wiring came at 10:48:41.
- dry_fix_1 ran at 10:48:55 with `--motion-session`: **0 fixes**.
- A live check at 10:50:43 measured board 0 at 1.95-2.0 m, and `measure()` returned fixes in 8 of 9 frames.
- dbg_1 (10:51:13, same arguments but no `--motion-session`, instrumented): `measure()` called 400 times, all non-None; 72 blends.
- 10:52:50: the range was cut to 1.5 m and median 5; committed as 46fbc08 at 10:54.
- sup3 (10:56) and dbg2_1 (10:59, `--motion-session`) both had 0 fixes. dbg2_1 is explained by the range (board 0 at 1.95-2.0 m).

Proven:
- `--motion-session` does not stop fixes in `control_loop` (replay: 18 fixes against 23).
- Pulses were present in sup3 and dry_fix_1 (3 pulses of 0.20-0.22 s).
- MarkerFix gives fixes on real approach frames of the same path (sup6 119, t2_2 64).

Not found: why dry_fix_1 (2.5 m limit, board 0 visible at 1.99 m) and sup3 got none. The frames were not saved and the summary does not count `measure()` calls. The candidates are a board not detected in those runs (sup3: DQK said the path was blocked by the table) or a frames thread that stopped silently. Neither is proven.

sup1/sup2: one continuous spin. Pulses are only on with `--anchors` or `--servo-marker`, by design.

**(b) t2_5 handshake.** The loop ran 3.28 s in WAIT_CAMERA. The flag was 1 on only 1 tick, the one before the window reset. `WindowedHandshake` counts only answers newer than the reset and needs ≥ 6 of them with ≥ 70 % in view, and `fresh_flag` needs the newest answer to be ≤ 1.0 s old. Every answer of the run was in view (47/47), so the rule failed because fewer than 6 answers arrived after the prompt, or because they were stale at every tick. That would mean the answer rate was ≤ 1.8/s in those 3.28 s; the run average was 2.29/s. Which of the two, and why, is not recorded: per-answer times are not logged. Whether the R1 release was deliberate is not recorded.

**(c) Early motion_check stops.** class_1: one attempt at 10:34 ended "incomplete" with no latch line in the output kept, then attempts stopped at 0.4 s and 2.7 s. class_2: stops at 1.6 s and 0.3 s. In each case `hold()` returns only when the `ESTOP` latch file exists (polled every 0.3 s over SSH). `jetson/estop.py` writes it on "R1 released", "button N pressed", "gamepad lost" or a motor-driver reset failure, with a time stamp in `/home/jetbot/sentry/estop.log` on the robot. **Cause not found.** Reading that log is the first step of the next session.

**(d) Time-to-vantage spread.** See finding 10. t2_1 needed 9 pulses / 5 drives; t2_5 needed 11 pulses / 6 drives plus about 2.2 s more driving (the blind DR leg).

**(e) Why board 2 was lost in t2_3/t2_4/t2_5.** In the second half of the approach, board 2 was detected in 14-28 % of frames against 78-100 % in sup5-t2_2. Median sharpness (Laplacian variance) was 64-183 against 62-162 and mean grey level 117.7-122.4 against 116.3-122.3: no difference. The last sighting bearings were -0.12 / -0.32 / -0.21 rad, with the steering at its limit (w = -0.12 to -0.14). After that, no marker of id 1 was found in any frame. **Not found**; occlusion or a turn away are both possible. Checking needs a look at the frames after t = 6.9 / 7.9 / 10.8 s (local frames, faces possible).

## 9. Simulator input
`floor_model_1030.json` contains:
- wheel law with m0(V), 11.28-11.70 V
- spin rate 2.395 rad/s at w = 0.45, lag 0.017 s
- drift: sim value 0.45 rad/m, measured 0.38 steady and 0.57 from rest
- video latency for the sim: 0.12 s (measured ≤ 0.153)
- stop overshoot 0.043 m
- camera pitch 6.0-6.2 deg

Plug-in (`tools/floor_model.py`, test `tests/test_floor_model.py`):
```python
from tools.floor_model import load, wheel_model, FloorSim
fm = load(); sim = FloorSim(fm, battery_v=11.4)   # SimRobot API: on_packet(), step(now, dt); camera_pose(now) = the pose the video shows
model = wheel_model(fm, 11.4)                     # a sentry.nav.wheel_model.WheelModel for dead reckoning
```
Not modelled: the spread between runs (sd values are in the JSON), the reverse speed, other floors, below 11.2 V.

## 12. Surprises, and what could not be extracted
**Contradicts what the team believed:**
1. "Speed ratio falls with the battery, 1.03 → 0.65": the method is wrong. The real fall is 3.9 % between 11.6 and 11.4 V.
2. "Video lags about 1 s": the measured bound is ≤ 0.153 s.
3. "Right turns are 0.79 of left": the right pulses match the default model to within 6 %, and left is not measured well enough to compare.
4. "Chair box excludes the legs": the pitch file was wrong by about 4 deg.
5. "t2_5 waited 6 s": it waited 3.28 s.
6. "sup3 had no pulses": it had 3.
7. "Big misses are low-battery runs": they are the runs that lost the board and drove blind.
8. The motion_check rest-pose results (spin_right 0.83, forward_2 1.59) are marker-yaw and marker-position noise; the board's bearing and range from the same frames agree with the model to within 0-9 %.

**Could not be extracted:**
- the video latency alone (no capture times saved)
- the motor start lag apart from the latency
- left against right turn (2 left pulses)
- k(V) against m0(V) (one command)
- voltage against time-in-session
- the reverse speed (no board in view while retracting)
- the cause of the 0 fixes in sup3 / dry_fix_1 (no frames, no counters)
- the cause of the e-stop latches (log on the robot)
- why board 2 was lost (needs a look at the frames)
- the T2 "furniture within 1 m" item (not measured)
- obstacle recall (two placements of one chair)
- tape offsets in the start frame (axes not recorded)
