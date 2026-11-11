# Provenance of the experiment A scripts (2026-11-09 to 11-10)

Run with `PYTHONPATH=.` from the repository root, laptop conda env `sentry` (Python 3.12): ultralytics 8.4.172, transformers 4.57.1, torch 2.9.1+cu128, GPU RTX 4050 6 GB. The scripts use absolute
paths of DQK's machine (`D:\CS532\...`, a scratch folder for outputs); adapt `R` and `S` at the top. Frames are local (people in them, `data/` is gitignored); the numbers are in the JSON files one folder up.

| script | what it did | output |
|---|---|---|
| `depth_eval.py` | round 1-2: Depth Anything V2 Metric Indoor Small on the saved person sets, native view and virtual zoom | `experiment_A_depth_pass1_body_zoom2.json` |
| `depth_zoom.py` | round 2: zoom calibrated on the 1.8 m sets, validated on the 1.25 m set | `experiment_A_depth_zoom_holdout.json` |
| `depth_models.py` | round 3: Metric Indoor Base and Large, Depth Pro, ZoeDepth | `experiment_A_models_trial.json` |
| `depth_floor_anchor.py` | round 4-5: relative depth anchored to the floor plane | `experiment_A_floor_anchor_trial.json` |
| `anthro_range.py`, `anthro_temporal.py`, `anthro_posture.py`, `anthro_fusion.py` | rounds 6-8: body-part size ranging (trunk prior 0.50 m in rounds 6-7, 0.49 m in round 8), temporal median, posture features, leg cues and fusion | `experiment_A_anthro_*.json` |

Not preserved: the scripts of the first offline detector pass (`glossy_eval.py`, `chair_dets.py`) and of the ankle and box-height checks (`ankle_check.py`, `ankle_dist.py`, `height_marks.py`, `floor_marks.py`); their results are in the README of this folder and can be rerun by rewriting them.

## Weights and models
- `yolov8s.pt` (person/chair boxes): `data/models/yolov8s.pt`, sha256 `1f47a78bf100391c2a140b7ac73a1caae18c32779be7d310658112f7ac9aa78a`
- `yolov8n-pose.pt` (keypoints): repository root, sha256 `c6fa93dd1ee4a2c18c900a45c1d864a1c6f7aba75d84f91648a30b7fb641d212`
- Hugging Face model ids (downloaded 2026-11-10, revision = the one served that day, not pinned): `depth-anything/Depth-Anything-V2-Metric-Indoor-Small-hf`, `...-Base-hf`, `...-Large-hf`, `depth-anything/Depth-Anything-V2-Small-hf` (relative), `apple/DepthPro-hf`, `Intel/zoedepth-nyu`
- Camera: `calib/camera.json` (fisheye) and the pose file named in each script (`calib/camera_pose_self_1109_4.json`, copies in `../pose/`); the saved person sets are `data/pursuit/{home_4_1,home_6_1,box_1p8_1}/frames` with the tape distances 1.25, 1.77, 1.80 m (DQK, lens to feet).
- Priors: trunk 0.50 m (rounds 6-7) and 0.49 m (round 8, Drillis and Contini, stature 1.70 m): reported separately, as HNHL asked.
