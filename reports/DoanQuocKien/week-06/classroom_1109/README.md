# Classroom, Mon 2026-11-09 (DQK, alone, glossy tile floor with 0.6 m tiles, no ESP32-CAM on hand)

Place: the CLASSROOM (label corrected by DQK on 11-09: everything dated 2026-11-09 was recorded here, not at home). Floor: glossy tile, tiles exactly 0.6 x 0.6 m. One person (DQK). Battery 12.03 V at the first run, 11.73 V later (gate 11.4 V). The graded T2 runs, Part C, the handshake and Phase 2 were NOT done (no ESP32-CAM on hand; the official session is pushed to next week).

## Done today
| item | result | where |
|---|---|---|
| `self_pose` x4 | pitch -4.61, -4.34, -4.61, -4.70 deg (spread 0.05-0.14 deg, 45 frames each, 0 rejected); stable within 0.4 deg all day | `pose/` |
| Pursuit runner trials (tile steps 3 / 2 / 1 tiles) | `tile_1_1`, `tile_2_1`, `tile_3_1`, dry-run `p2_dry_1`; first live runs, no acceptance; the standoff dead band stopped the creeping (21 HOLD frames, 3.5 to 7.2 s in `tile_3_1`); true hold about 1.7 m while the runner read 1.3 m | `reports/DoanQuocKien/week-05/home_1107/` (on PR #99; the folder name says home, its section 7 says classroom) |
| Motion effect on the range | box bottom row 285.2 still, 284.1 after three forward-and-back bursts, 283.9 (sd 0.9) while moving: driving does not change the view (-1.2 px, 0.1 m) | same README, section 7 text |
| Still range at the 1.8 m tile, offset 3.5 px | 1.71 m (0.09 m short) | scratch run, summarised in the plan limits |
| **Obstacle retest on the glossy floor, metal-frame cantilever chair, 12 frames each** (`furniture_check`, YOLOv8n confidence 0.25, `--floor glossy`, pose `1109_4`) | **1.2 m: 0/12 detected, 0 with a distance. 1.8 m: 4/12 detected (confidence 0.30-0.38), 0 with a distance (all `reflection_unresolved`). 2.4 m: 0/12, 0.** Tape = robot front to the nearest chair point on the floor; the front skid is about 1.46 m from the lens at the 1.2 m mark | `furniture/` |

## Finding on the chair
At 1.2 m YOLOv8n sees the chair at only 0.05-0.09 confidence; YOLOv8s sees the same chair at 0.21-0.42 with a correct box (bottom row 289 on the skid). At 1.8 m the glossy-floor logic cannot resolve the box bottom (`reflection_unresolved`): the mirror image of the legs and the skid continues the box. Session diagnostic (distance in >= 10 of 12 frames within +/- 0.15 m up to 1.5 m): NOT met, as on 10-30 (12/12 detected without a distance at 1.2 m, 0/12 at 2.4 m for the earlier chairs).

## Not done
The table (robot to be placed 1.2, 1.8 and 2.4 m from it), the end-of-session `self_pose` after moving the robot, T2, Part C, handshake, Phase 2, the classroom-floor calibration (`motion_check`), the demo shots.

## Experiment B, offline pass 1 (2026-11-09 evening, saved chair frames, 12 per distance, pose `1109_4`, `--floor glossy`; `experiment_B_offline_pass1.json`)
| candidate | 1.2 m det / with distance | 1.8 m | 2.4 m |
|---|---|---|---|
| base (YOLOv8n, 0.25) | 0 / 0 | 6 / 0 (all `reflection_unresolved`) | 0 / 0 |
| YOLOv8s | 5 / 0 (`reflection_unresolved`) | 1 / 0 | 12 / **5**, median 2.21 m |
| YOLO-World (`open_vocabulary`) | 0 / 0 | 8 / 0 | 12 / 0 (all `reflection_unresolved`) |
| SegFormer floor analyzer (`semantic_floor`) | same as base | same as base | same as base |
| YOLOv8s + SegFormer | same as YOLOv8s | | |
No candidate meets the session diagnostic (distance in >= 10/12 frames within +/- 0.15 m up to 1.5 m). The live check gave 4/12 at 1.8 m for the base; the saved JPEG frames give 6/12 (frame sampling). **The common blocker is the glossy-floor logic (`reflection_unresolved`), not only the detector confidence:** a larger detector finds the chair more often, but its distance is rejected because the mirror image of the legs cannot be separated from the box. Next (tonight): the reflection thresholds in `[obstacle]` (`reflection_min_score` 0.85, `reflection_min_peak_margin`, `reflection_peak_separation_px`, ...) on these frames, the empty-floor frames for false stops, then the live check of the best setting. The 2.4 m YOLOv8s distance (2.21 m against a tape of 2.4 m from the robot's front) is 0.4 m short at the front-to-lens offset of about 0.2 m. Offline numbers are not an acceptance.
