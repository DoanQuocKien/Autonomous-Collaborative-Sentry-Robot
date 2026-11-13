# Experiment B (2026-11-10/11): a model for obstacles on a glossy floor, trained on ORG, judged on saved classroom data

**Question.** The configured detector (YOLOv8n, furniture classes, glossy-floor reflection logic) gives no usable distance on the classroom's glossy tile (chair at 1.2 / 1.8 / 2.4 m: no distance in 36 of 36 frames on 2026-11-09, `reflection_unresolved`). Can a model trained on reflective-floor data do better, judged on data it never saw?

**Data.** ORG (Xue et al., IJCV 2023, [IndoorObstacleDiscovery-RG](https://github.com/XuefengBUPT/IndoorObstacleDiscovery-RG)): robot-view images of small objects on reflective floors, pixel labels (0 background, 1 ground, >= 2 obstacle category). 1,711 labelled train images (8 scenes) and 1,709 test images (7 other buildings), 38 / 43 object categories, median object 126 x 51 px at 1920 x 1080. No licence stated: local only (`data/ORG`, gitignored), used for evaluation and a small fine-tune, cited, not redistributed.
**Model.** SegFormer-B0 (`data/models/segformer-b0-ade`, ADE20K pre-trained) with a 3-class head. 15 epochs, batch 6, 512 x 512 crops of 960 x 540 images (70 % centred on an obstacle), AdamW 6e-5 one-cycle, class weights 1 / 1 / 8, fp16, seed 0; 997 s, peak 2.43 GB, loss 0.67 -> 0.0236 (`results/train_log.json`). Weights `segformer_org.pt` sha256 `a703e4290a83e688a3619e96a613aad07ae09159fdbeb83a954581ae335267e9` (local, 15 MB, not committed). Libraries: torch 2.9.1+cu128, transformers 4.57.1, ultralytics 8.4.172.
**Code.** `tools/org_seg.py` (cache, train, eval) and `tools/org_seg_judge.py` (the ruler below), branch `DoanQuocKien/w06-experiment-b`; `scripts/` here holds the diagnostic scripts.

## 1. Unseen ORG scenes (`results/eval_org_ft.json`, 1,709 images, 960 x 540)
| | |
|---|---|
| IoU background / ground / obstacle, mIoU | 0.973 / **0.953** / 0.452, 0.792 |
| obstacle pixels: precision / recall | 0.474 / 0.905; ground pixels called obstacle 1.3 % |
| objects found (>= 30 % covered) | **1,920 of 2,207 (87 %)** |
| floor-contact row error of the found objects | median **2.0 px**, 90th percentile 5.5 px |
| false obstacle components | 3,190 (**1.87 per image**, components >= 30 px) |

## 2. The ruler: D1 glossy-tile sets of 2026-10-15 with tape distances (never used for training or tuning)
`data/D1_obstacles_1015`: 24 objects at 0.32-1.98 m (tape, lens-referenced) and lateral offsets, pose `calib/camera_pose_classroom_1015.json`, frames rectified; an object is FOUND in a frame when a prediction lies within 0.5 m forward and 0.4 m lateral of its tape position (`results/judge_*.json`; every other second frame).
| | configured detector | fine-tune, obstacle class | fine-tune, free-space boundary |
|---|---|---|---|
| objects found in at least half the frames (of 24) | 1 | 8 | 6 |
| median distance error of those | 0.127 m (n = 1) | **0.041 m** | 0.091 m |
| within +/- 0.15 m (of those found) | 1 | 6 | 4 |
| chairs found (of 10) | 0 | 0 | 3 (errors 0.14-0.31 m) |
| objects within 1.2 m of the lens found (of 14) | 0 | 7 | 6 |
| objects within 1.2 m found by either fine-tune output | 0 | **10 of 14** | (union) |
| objects beyond 1.2 m found (of 10) | 1 (jacket, 1.39 m) | 1 (power strip, 1.57 m) | 0 |
Per object, near range: sandals 0.40 m, laptop sleeve 1.0 m, plastic cup 0.51 m, mouse 0.85 m, bottle 0.47 m, keychains 0.54 m found at 100 % (errors 0.00-0.05 m, one +0.29 m for the cup on the obstacle route), chairs at 0.32, 0.70 and 1.06 m via free space; missed: bag 0.70 m, book 0.95 m, chairs at 1.01 and 1.19 m (16-20 %). **Beyond about 1.4 m almost nothing is found** (laptop 1.98 m, phone 1.8 m, charger 1.8 m, three chairs at 1.77-1.9 m: 0-7 %). "Either output" is a rule chosen after seeing both results.
`empty_1` ('nothing placed'): the free-space output has a segment in all 57 frames, but the frame shows a real chair at the left edge about 1.2 m away, so this set is NOT an empty-floor control and no false-stop rate is claimed from it (the configured detector: 0 of 57 frames).

## 3. An independent check on a different day: the metal-frame chair of 2026-11-09 (36 frames, pose `1109_4`)
- **Obstacle class:** the chair's skid is found at the 1.2 m mark in **12 of 12** frames (contact 1.26 m forward, range 1.26-1.31 m; the true distance from the lens is unknown to about 0.2 m because the tape was taken from the robot front), in only 4 of 12 frames at 1.8 m (and at a wrong 2.49 m), and in 0 of 12 at 2.4 m.
- **Free-space output: fails on glare.** It reports a boundary 0.2-0.3 m in front of the robot in 24 of 24 frames at the 1.2 m and 2.4 m marks, where the chair is more than 1.4 m away: a specular highlight of the ceiling lights on the tile is labelled background and reads as a wall (`scripts/overlay1109.py`; the overlay showed a purple patch inside the floor). A stop built on it would stop in front of nothing.

## Verdict
- ORG fine-tuning makes the ground mask reflection-robust (the chairs' mirror images are ground; ground IoU 0.95 on other buildings) and finds small floor objects with a 2 px contact error on ORG.
- On our glossy tile the **obstacle-class output finds objects within about 1.2 m that the configured detector misses entirely** (10 of 14 against 0 of 14, small-object errors about 0.05 m), which is the range of the 0.5-0.6 m repulsion thresholds.
- It is **not ready to replace the configured detector**: no coverage beyond about 1.4 m, the free-space output gives glare false positives, the metal chair works only at 1.2 m, 24 objects from one session and one day is a small ruler, no empty-floor false-stop control exists yet, and nothing here is a D1 or T1 acceptance. The decision belongs to HNHL (perception owner), by PR, with his D1/D5 evaluation.
- Next, in this order: (1) a real empty-floor control (and a table control) on the glossy tile with nothing but the floor in view; (2) glare handling (a patch of non-ground enclosed by ground is not an obstacle) and a range check beyond 1.4 m, possibly at higher input resolution; (3) fine-tune on our own D5 (floor-level objects, glossy classroom) and judge on D1; (4) a live check on the robot at the tile marks.
