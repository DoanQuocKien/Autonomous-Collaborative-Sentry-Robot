# Obstacle set, classroom, 2026-10-15 (DQK)

Data for HNHL's obstacle recognition and distance work. **A real recognition problem, see "What it shows" below.** Private D1 rules apply: the frames in this folder are only the three chair clips (no people visible, checked on contact sheets); the other clips (people at the image edge) are in a private zip that is not in git and not for chat groups.

## Capture
- JetBot, robot **still** on a floor mark, camera facing +x, 6 s per clip (about 85 frames, 14 fps), `python -m tools.record_clip`. Floor: **glossy polished tile** with visible reflections (confirmed by the operator). Room lit by ceiling tubes and windows; the image has a pink colour cast (white balance).
- Truth: tape from the point under the lens along the robot's forward axis. `tape_distance_m` = forward distance to the nearest floor point the robot would hit first, nearest cm; `lateral_offset_m` = sideways offset, **left +**. Rows 6-26 were given in metres. Rows 27-29 (`chairs_c`) were given as `106 0.16`, `119 -0.17`, `180 0` and are read as centimetres for the forward distance and metres for the sideways offset (1.06 m / +0.16, 1.19 m / -0.17, 1.80 m / 0): **confirmed by the operator**.
- Camera pose for these frames: `camera_pose_classroom_1015.json` = 3 tape strips at 0.5 / 1.0 / 1.5 m, one click each, rms 2 mm, **H 0.109 m, pitch -12.2 deg (the camera looks UP 12 deg; the mount tilts during transport and is readjusted by hand)**, roll 0 (the real roll is about +1.1 deg, see PR #38). The tilt may have drifted during the session; a marker check at the end was not done on these frames. Treat the pose as +-1 deg.

## Files
- `obstacles_2026-10-15.csv`: 24 rows (ids 6-29; ids 1-5 are the 12 October setup, sent separately). Columns as `assets/d1/obstacles_template.csv` plus `clip` and `frames_in_git`. Rows of one clip share start / end times.
- `chairs_a/`, `chairs_b/`, `chairs_c/`: every 3rd frame of each chair clip (names are the original frame numbers). Chair clips: ids 21-23, 24-26, 27-29 (`chairs_c` is tight: chairs close together).
- `set2`, `set3`, `set4` (15 mixed small objects: sandals, bag, laptop sleeve, chair, charger, cup, mouse, laptop stand, power strip, phone, bottle, keychains, book, jacket, laptop): **private zip only**.

## What it shows (current `ObstacleDetector`, glossy setting, today's pose, one mid-clip frame per clip)
- The detector finds the **chairs** with high confidence (0.80-0.95 for the near ones) but returns **no distance for any chair**: every box is `reflection_unresolved` (the symmetry estimator abstains on this tile). That is the tuning target.
- With **all 80 COCO classes enabled**, none of the small or low objects was detected in set 2-4 (bottle, laptop, bag, cup, mouse, phone, book, jacket, charger): YOLOv8n at this size and camera height does not see them. Widening `class_ids` is not the fix.
- A plain colour-threshold floor model would break on decorated floors and shadows. Two ideas that generalise: a pretrained scene segmenter with a floor class (for example SegFormer-B0 on ADE20K: floor, rug, carpet; "not floor" in the lower image = obstacle, distance from the ground-plane formula), and a geometric cue (floor points move between frames as the ground plane predicts from our own motion estimate, objects above it do not).
- A second, very different floor exists for generalisation tests (rugged hard carpet, 2026-10-14 night, marker runs in `reports/DoanQuocKien/week-02/rugged_floor/`).

## Suggested protocol
Tune any threshold on `chairs_a` + `chairs_b`, report on `chairs_c` (held out, tight layout). Report glossy and matte separately as the evaluator requires: **no matte set was recorded** (a matte-paper setup was dropped on purpose: the robot runs on glossy floors, tune for them; a small matte control is still needed for `required_floor_types`).
