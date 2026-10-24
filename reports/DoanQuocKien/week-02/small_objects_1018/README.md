# Small objects and wires: first baseline (2026-10-18, rugged matte floor)

Evidence for the required row "Small objects and wires" (Implementation Plan section 4.3, risk 30). One session, one floor, one distance (1.0 m), five items; **a first look, not the acceptance measurement**.

## Setup
- JetBot at 10.41.212.160, camera lens height **0.100 m (fixed)**, floor: rugged, patterned carpet (matte), battery 12.2-12.5 V, video 20 FPS.
- Camera pose of the day: `camera_pose_rugged_1018.json`: H 0.100 m (fixed), pitch **1.04 deg down** from the 1.0 and 2.0 m strips (they agree within 0.05 deg); the 0.5 m strip lands 3 cm off (3 px) and is in the residuals, not in the fit (rms 2.1 cm). The tool's own free fit (H 0.0957 m, pitch 0.89 deg) is kept in the file under `free_fit`. The first attempt (0.5 m strip 5 cm off) is not used. The tilt is not constant between sessions (tiltable mount), so this pose is for this session only.
- One item at a time on the centre line, its front floor edge on the 1.0 m strip (distance from the point under the lens). Capture: 20 frames from the live stream (`capture_frames.py`), the detector run on each frame (no motor commands).
- People were partly in view at the frame edges in some captures.

## Results

| Item | Stock YOLOv8n (furniture classes) | Semantic floor (PR #46) | Open vocabulary (YOLO-World, PR #46) |
| :-- | :-- | :-- | :-- |
| Small low table | 0 / 20 (people only) | not found (1 stray 5 x 7 px speck) | found in 3 / 3 saved frames, conf 0.50-0.54, 0.86-0.87 m (-13 to -14 %) |
| Backpack | 2 / 20 (as "suitcase" 0.30; otherwise truck, train, parking meter); 0.927 m (-7.3 %) | not found (hits only on a person's foot) | found in 2 / 3 saved frames, conf 0.54-0.60, 0.89-0.90 m (-10 to -11 %) |
| Box | 0 / 20 (1 hit rejected, `bottom_truncated`) | not found | found, conf 0.21, median 0.861 m (-13.9 %); the 25 distance hits over 20 frames include other objects |
| Black wire | not run | not run | **0 / 20**: the wire across the centre line (a thin dark line, 1-2 px) is never boxed; the one "cable" hit (conf 0.10) is another cable at the left edge, 0.65 m |

## What it shows
- The stock detector and the semantic floor do not see ordinary objects from 0.10 m on this floor, not only wires. Only the open-vocabulary backend does, and only for objects that are in its prompt list.
- The open-vocabulary distances are 10-14 % short, all on the same side. The boxes extend about 4 px below the object's contact row, which suggests a bias in the box bottom, not noise. The target is median <= 10 %.
- Wires stay unsolved with every backend we have. That is the honest status for risk 30; mitigations in the plan: speed cap, keep-clear rule on demo day, a floor-anomaly check (HNHL).

## Caveats
- Single floor, single distance, 20 frames per item; the table and backpack counts for the open-vocabulary backend come from 3 saved frames each, not a live 20-frame capture. The box count is not clean (other objects in the room also produce hits).
- The prompt list had to be extended with "box", "backpack", "low table" and "wire" (`config.toml` was changed locally for the test and reverted). The repo list does not contain them.
- The open-vocabulary backend ran at 8-11 FPS in HNHL's measurement, under the 20 FPS target.
- Not done: white wire, footwear (no shoes on hand), the other items (cup, phone, mouse, laptop case, jacket, charger), 0.5 and 1.5 m, the glossy floor.

## Files
- `obstacles_stock_yolo.csv`, `obstacles_open_vocabulary.csv`: per item, frames, frames with any detection (anything, not only the item), frames with a distance, median distance.
- `capture_frames.py`: the capture and detector script (needs the repo on `PYTHONPATH`).
- `camera_pose_rugged_1018.json/.jpg`: the pose and its annotated photo.
- The frames themselves stay under `data/D1_small_objects_1018/` (gitignored); to be handed to HNHL privately.
