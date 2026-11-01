# Data catalogue (2026-10-30 session and the earlier motion data)

`catalogue.csv` is the full list, written by `python -m tools.analyse_classroom_1030`: 132 rows with path, run, what, bytes, files, rows/frames, time span and sha256.

**storage** column:
- "local only": only in `data/` or `calib/`, which are git-ignored or untracked.
- "local only; identical copy committed: <path>": the same bytes are committed under `../`.
- "committed": the file itself is tracked.

**privacy** column: every frame folder is robot or ESP32 video and may show people. Frames stay local and must never be copied. No frame or crop is in the repository.

| group | entries | contents | time span | storage |
|---|---|---|---|---|
| `data/deploy/<run>/summary.json, log.csv` | 18 runs: rehearsal_class_1/2, dry_negative_1, dry_positive_1, sup1-sup6, dry_fix_1, dbg_1, dbg2_1, t2_1-t2_5 | log.csv: 30 Hz, 356-1760 rows | 12.0-60.0 s | sup1-sup6, t2_x, dry_negative/positive: committed copy. rehearsal_class_1/2, dry_fix_1, dbg_1, dbg2_1: local only |
| `data/deploy/<run>/servo.csv` | sup4, sup5, sup6, t2_1-t2_5 | board id 1 sightings: 48-224 rows | 6.5-13.9 s | committed copy |
| `data/deploy/<run>/frames/` | sup5, sup6, t2_1-t2_5 | 2 237 JPEG frames, 46 MB, 18-20 fps | 14.1-20.2 s each | local only, privacy |
| `data/motion_check/class_1, class_2` | commands.csv (684 / 1604 rows), segments.json, summary.json | 6 / 15 segments | 23.3 / 54.7 s of commands | committed copy |
| `data/motion_check/*/frames/` | 404 + 547 frames, 20.5 MB, about 10 fps | | 214 / 185 s | local only, privacy |
| `data/furniture/chair_1.2m, chair_2.4m, probe` | result.json + 12 / 12 / 2 frames | | | chair results: committed copy. probe and frames: local only |
| `data/handshake/class_door` | results.json, results_run1_primary.json, trials.json, eval_rerun.log; ref (6), sweep (222), trials (20 folders, 1 047 frames) | Part A at the classroom door | | local only, privacy |
| `data/handshake/cafe_arch/results.json` | cafe rehearsal 2026-10-28 | | | local only (summary committed as `../../handshake/cafe_arch_results.json`) |
| `data/entrance/class_door` | entrance.json + 1 robot frame | robot-eye door reference | | local only, privacy |
| `data/explore/class_dry_1` | summary.json, log.csv (124 rows), grid.npz | explore_live dry run, 2026-10-30 09:48: robot still, pose file `rugged_1018` (the wrong floor), 124 / 124 frames with an unresolved obstacle, ended "no_frame". **Not analysed further: it does not move the robot.** | 32 s | local only |
| `data/speed_runs/*.csv` | 12 files, 84-452 rows | Week 2 glossy drives 2026-10-15 (= `reports/DoanQuocKien/week-02/classroom_1015/speed_runs`) | 7-23 s | local; copies committed under week-02 |
| `data/turn_runs/*.csv` | 4 files | Week 2 turns | | local |
| `data/dr_path/*` | 6 runs: commands.csv, summary.json, 47-87 frames each | Week 3 dead reckoning (2026-10-18/19/24) | 7-15 s | local; t2_1024 summaries committed under week-03 |
| `data/anchors_class_1030*.csv`, `data/dr_anchors_*.csv` | 5 files | board positions. **1030b: board 3 (id 2) at (0, 1.5) is an assumption** | | 1030 files: committed copy |
| `calib/*.json` | motion.json, camera.json, motion_session_1030_provisional.json (hand-made), 11 camera_pose files | | | mixed, see csv |
| `reports/DoanQuocKien/week-02/motion_runs.csv, motion_v07_rugged_tape.csv` | tape runs | | | committed |

SHA-256 of the key raw files, first 16 hex characters (full values in the csv):

| file | sha256 |
|---|---|
| deploy/sup6_1/log.csv / servo.csv | 2e5b40586a514753 / d3ef4f08d1359225 |
| deploy/t2_1/log.csv / servo.csv | c4abe3a400ffb08a / cc9d7e30ef63e972 |
| deploy/t2_2/log.csv / servo.csv | 8fbbd59422e8fc76 / a0a3662195aa2d31 |
| deploy/t2_3/log.csv / servo.csv | cb6f4e1d8d8b5cd8 / 52eb2d9627fcd093 |
| deploy/t2_4/log.csv / servo.csv | b87a21177fde61fa / e759bdef9d25cb0d |
| deploy/t2_5/log.csv / servo.csv | b8a8efb38e48bf26 / 26c31d619e6a5968 |
| deploy/sup3_1/log.csv / dry_fix_1/log.csv / dbg_1/log.csv | 07191db7571ed58b / 87738012f7638fd7 / 7fed8b1e31f582cf |
| motion_check/class_1/commands.csv / class_2/commands.csv | ce1ba1f2f5d59f61 / 301cd905d04bf74f |
| furniture/chair_1.2m/result.json / chair_2.4m | 89c7c9dd10113072 / c47fd6925b623535 |
| handshake/class_door/results.json | 3fc9dd2ed0287a74 |
| calib/camera_pose_self_1030_2.json / motion_session_1030_provisional.json | 48ef1692b21a550e / e748a5c3432e21d7 |

Not catalogued and **not examined** (no robot-motion content for this analysis): `data/D1*`, `D2`, `D5*`, `follow/` (Week 2 follow runs), `parity/`, `check_env/`, `insightface/`, `jetbot_card_files_2026-10-16/`, `models/`, `ultralytics/`, the two `for_HNHL_obstacles_*.zip`, `marker_range_test.csv` (summarised in the Week 2 README), `jetbot_host_key`, and the partition table.

The time span of the handshake trial folders is per trial (5-8 s); the csv shows only the longest.
