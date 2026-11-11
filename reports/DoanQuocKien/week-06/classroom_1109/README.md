# Classroom, Mon 2026-11-09 (DQK, alone, glossy tile floor with 0.6 m tiles, no ESP32-CAM on hand)

Place: the CLASSROOM (label corrected by DQK on 11-09: everything dated 2026-11-09 was recorded here, not at home). Floor: glossy tile, tiles exactly 0.6 x 0.6 m. One person (DQK). Battery 12.03 V at the first run, 11.73 V later (gate 11.4 V). The graded T2 runs, Part C, the handshake and Phase 2 were NOT done (no ESP32-CAM on hand; the official session is pushed to next week).

## Done today
| item | result | where |
|---|---|---|
| `self_pose` x4 | pitch -4.61, -4.34, -4.61, -4.70 deg (spread 0.05-0.14 deg, 45 frames each, 0 rejected); stable within 0.4 deg all day | `pose/` |
| Pursuit runner trials (tile steps 3 / 2 / 1 tiles) | `tile_1_1`, `tile_2_1`, `tile_3_1`, dry-run `p2_dry_1`; first live runs, no acceptance; in `tile_3_1` all 80 rows between 3.4 and 7.4 s have v = 0 and w = 0 (no creeping, PURSUE mode with the standoff dead band) and HOLD was entered at 7.405 s (HOLD rows: 21 in two short episodes, 7.4-8.06 s and 43.8-44.2 s; numeric source `pursuit/tile_3_1/log.csv`); true hold about 1.7 m while the runner read 1.3 m | `reports/DoanQuocKien/week-05/home_1107/` (on PR #99; the folder name says home, its section 7 says classroom) |
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

## Experiment A (metric depth model), 2026-11-10 evening: FAILS zero-shot
Model: Depth Anything V2 Metric Indoor Small (Hypersim fine-tune), run on the rectified fisheye image (f 306 px, 93 deg wide), depth read at the middle of the person box (0.35-0.65 of its height), converted to forward distance with the camera pitch. Saved frames only (`data/pursuit/...`, local), tape distances lens to feet by DQK.
- Pass 1 (native view): about 2.1x too far for a person at 1.77-1.80 m (3.7-3.8 m). Thin metal chair: unusable (see-through frame, unstable). Not a person effect: the factor was the same in two sessions.
- Pass 2 (hold-out; `experiment_A_depth_zoom_holdout.json`): ratio model / tape, native view 2.10 and 2.07 (1.8 m sets), **2.52 on the held-out 1.25 m set**; with a virtual zoom of 1.7 the ratios are 1.10, 1.20 and **1.48**. A zoom chosen on the 1.8 m sets (x1.8, 1.79 m for 1.80 m) does not transfer: at 1.25 m the model is about 0.6 m too far. The error is not one scale factor: the output is compressed with distance (it behaves like an added offset of about 1.7 m in the near range).
- Verdict: pass rule (every tile within +/- 0.15 m) NOT met. A fine-tune on metric ground truth from this camera would be needed (the saved data has only 1.25 and about 1.8 m; the 2.4 m and 1.2 m marks were not saved as frames). Not a quick fix; left as a proposal.

### Experiment A, rounds 3-5 (2026-11-10 night): four more models and a floor-plane anchor, all fail
Round 3, metric models zero-shot on the same saved person sets (ratio = model forward / tape; native view | 1.4x zoom; `experiment_A_models_trial.json`):
| model | 1.80 m | 1.77 m | 1.25 m (hold-out) |
|---|---|---|---|
| DA-V2 Metric Indoor Base | 2.58 \| 1.98 | 2.64 \| 2.20 | 3.15 \| 2.57 |
| DA-V2 Metric Indoor Large | 2.50 \| 1.99 | 2.38 \| 1.93 | 2.80 \| 2.17 |
| Depth Pro | 1.87 \| 1.66 | 1.65 \| 1.42 | 2.02 \| 1.70 |
| ZoeDepth NYU | 1.91 \| 1.50 | 1.82 \| 1.51 | 2.32 \| 2.07 |
All read too far and worse at the near range (the output is compressed). Shared cause (hypothesis, not tested): these models learned depth from eye-level cameras (about 1-1.6 m) and use the vertical image position as a cue, which breaks with a lens 0.10 m above the floor.
Round 4-5, floor-plane scale anchor (relative Depth Anything V2 Small, known H = 0.100 m and the pitch from `self_pose`, robust fit of the model output to the geometric floor depth per frame, no per-person constant; `experiment_A_floor_anchor_trial.json`): floor strip 0.4-3.0 m: ratios 7.6 (blown up), 0.97, 1.60; strip 0.3-1.2 m: 2.76, 0.89, 1.57; strip 0.3-1.6 m: 3.02, 0.86, 1.55. **Two sets at the same 1.8 m give ratios of about 3.0 and 0.9**, so the error depends on the scene (glossy floor reflections leave only 40-70 % of the floor pixels on a straight line), not on the distance: no constant can calibrate it.
Verdict: no off-the-shelf monocular metric depth approach meets +/- 0.15 m at 1.2-2.4 m with this camera on this floor. Remaining options (not done): fine-tune a depth or contact-point model on the target viewpoint (ORG dataset downloading, 7.1 GB), and the plan's higher mount. The foot-contact route (experiment B) with a reflection-robust segmentation is the better use of the dataset.

### Experiment A, round 6 (2026-11-10 night): range from body-part sizes with population priors (a lead, not a result)
Idea: no depth model, no floor, no per-person constant: `Z = f x prior size / pixel size` from pose keypoints (YOLOv8n-pose, `yolov8n-pose.pt` in the repo root) in the rectified image (f 306 px), forward distance via the pitch. Priors (adult means): shoulder width 0.38 m, shoulder-to-hip trunk 0.50 m, ear-to-ear 0.155 m. Saved person sets with tape (`experiment_A_anthro_range.json`), ratio = range / tape, median of 20 frames:
| set | tape | shoulder | **trunk** | head | all cues |
|---|---|---|---|---|---|
| `home_4_1` | 1.25 m | 1.45 | **1.13** | 2.63 | 1.36 |
| `home_6_1` | 1.77 m | 1.32 | **0.99** | 0.99 | 1.15 |
| `box_1p8_1` | 1.80 m | 1.62 | **1.09** | 1.08 | 1.19 |
The trunk cue is within 1-13 % (about +/- 0.1 m at 1.8 m) at all three, the first approach near the +/- 0.15 m target. The shoulder cue is 30-60 % too far for this person (the shoulder keypoints sit inside the 0.38 m prior) and the ear cue is unreliable at 1.25 m; averaging all cues is worse than the trunk alone. **Caveats:** one person (DQK), three sets, and 'trunk only' was chosen after seeing these three sets, so this is a lead; the population spread of the trunk length (about +/- 6 % in the literature, not measured here) adds to it; posture (leaning, turned body) changes the pixel length; no person frame at 2.4 m or 1.2 m exists in the saved data (an earlier 2.4 m row in my notes was invalid: the frame file was missing and the model ran on a stock sample image, retracted). Validation needs person frames at 1.2, 1.8, 2.4 m from at least two other people.

### Experiment A, round 7 (2026-11-10 night): temporal trunk-length range
Fixed before running: trunk prior 0.50 m, all four keypoints above 0.8 confidence, causal median over the last 10 valid frames (0.5 s at 20 fps), score = fraction of frames within +/- 0.15 m of the tape, on every stationary frame of the three sets (`experiment_A_anthro_temporal.json`).
| set | gated frames | raw: median error, within +/- 0.15 m, sd | smoothed |
|---|---|---|---|
| 1.25 m (`home_4_1`) | 171 / 171 | +0.16 m, 39 %, 0.03 | +0.15 m, 29 %, 0.01 |
| 1.77 m (`home_6_1`) | 455 / 455 | -0.02 m, 100 %, 0.03 | -0.02 m, 100 %, 0.02 |
| 1.80 m (`box_1p8_1`) | 122 / 122 | +0.16 m, 34 %, 0.02 | +0.16 m, 32 %, 0.01 |
Frame-to-frame noise is small (sd 0.01-0.03 m; the floor-row range moved by 0.4 m between sessions). The error is a per-set bias (+0.16, -0.02, +0.16 m; the two 1.8 m sets differ by 0.18 m), probably the stance (a lean or a turn changes the trunk's pixel length); smoothing cannot remove it. Verdict: the experiment's pass rule (within +/- 0.15 m per frame, every tile) is NOT met (29-39 % in two sets); against the plan's pursuit tolerance (1.2 +/- 0.2 m) all three sets stay within 0.16 m. One person, three sets, no frame at 1.2 m or 2.4 m, no other person: a promising lead that needs the validation recording (1.2, 1.8, 2.4 m, at least two other people) before it can replace or back up the foot-row range. A possible integration (not done): the pose model also gives person boxes, so the runner could use one pose pass for boxes and keypoints and take the standoff dead-band range from the trunk cue when the keypoints are confident, falling back to the foot row otherwise.

### Experiment A, round 8 (2026-11-10 night, pre-registered): other body cues and fusion with the foot row
Fixed before running (`experiment_A_anthro_fusion.json`): priors from the Drillis and Contini proportions with stature 1.70 m (trunk 0.49, hip-knee 0.42, knee-ankle 0.42, shoulder-ankle 1.32 m), gates 0.8 (trunk keypoints) and 0.6 (leg keypoints), causal median of 10, fusion = 50/50 mean of the body-cue median and the foot-row range (box bottom of the pose box, offset 3.5 px, pose `1109_4`). Bias in metres against the tape (smoothed median), sets 1.25 / 1.77 / 1.80 m:
| cue | 1.25 | 1.77 | 1.80 | mean abs bias | sets within +/- 0.15 m |
|---|---|---|---|---|---|
| foot row | +0.16 | -0.34 | +0.11 | 0.20 | 1 of 3 |
| **trunk** | **+0.13** | **-0.05** | **+0.12** | **0.10** | **3 of 3** |
| hip-knee | +0.35 | +0.34 | +0.48 | 0.39 | 0 of 3 |
| knee-ankle | +0.49 | +0.43 | +0.60 | 0.50 | 0 of 3 |
| shoulder-ankle | +0.28 | +0.19 | +0.35 | 0.27 | 0 of 3 |
| body median | +0.32 | +0.27 | +0.41 | 0.33 | 0 of 3 |
| fusion with the foot row | +0.23 | -0.04 | +0.26 | 0.18 | 1 of 3 |
Findings: (1) the leg-based cues read 0.2-0.6 m too far with the same sign at all three distances (the leg segments look shorter from a 0.10 m lens than the proportion tables say; cause not established: foreshortening or the pose model's leg points); (2) fusing with the foot row is worse than the trunk alone, because the foot-row bias swings between sets (-0.34 to +0.16 m); a heavier trunk weight would be tuning on the same three sets and was not done; (3) the trunk prior here is 0.49 m (round 7 used 0.50 m): the literature value, set before the run, but it lowers the bias from +0.16 to +0.13 m; the sensitivity is about 0.04 m of range per 0.01 m of prior at 1.8 m; (4) all body segments scale with the person's stature, so fusing them reduces keypoint noise but not the population spread. Conclusion: keep the trunk cue alone (with the foot-row fallback already in `--range-source trunk`); more rounds on these three sets would only fit them. Needed: frames at 1.2, 1.8, 2.4 m from several people.
