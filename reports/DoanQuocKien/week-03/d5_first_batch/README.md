# D5 first batch (DQK, 2026-10-24, glossy floor, one room)

Floor-level objects from the robot's own camera (lens 0.10 m), recorded with `python -m tools.record_d5 <class> --floor glossy --dist <m> --n <N>`. The masked images are committed in `data/D5/` (team decision 2026-10-24; `.gitignore` re-includes that folder, the underscore folders stay out), listed in `data/D5/manifest.csv` (class, file, floor, tape distance, session, time).

| Class | Frames | Positions |
| :-- | :-- | :-- |
| footwear (`shoe`: shoes and slippers) | 49 | 0.5 / 0.8 / 1.0 m, upright, sideways, tipped over |
| backpack | 49 | 0.5 / 0.8 / 1.0 m, standing, turned, lying |
| bag (tote, duffel) | 50 | 0.5 / 0.8 / 1.0 m, flat, stretched, standing on a string (the string is faintly visible) |
| wire_black | 50 | 0.3 / 0.5 / 0.7 / 1.0 m, across, curled, diagonal |
| wire_white | 49 | same; the white wire is nearly invisible on the white glossy floor at 0.7-1.0 m (hard case, expect low recall) |
| leg | 50 | 0.5 / 0.8 / 1.2 m, standing, striding, sitting with feet toward the camera |
| furniture: chair 20, table 15, plant 15 | 50 | 0.5 / 0.8 / 1.2 m (the table and plants cannot move: the robot moved) |
| empty floor | 50 | six views (room, windows, corridor, blank wall) |

**Not yet:** a matte floor, a second room, a second lighting (the held-out T1 session), and 150 per class. Counts are recording counts: frames within a batch are near-duplicates, so deduplicate by similarity before training.

## Labelling rules
- Label **every** visible leg, plant, table, chair, backpack, bag and shoe, including the ones far in the background (the recorder's legs at the desk, the big plant at the left of many frames). An unlabelled object teaches the detector that it is background.
- Wires: label the whole visible length, including the plug and adapter.
- `empty` frames are negatives for the object being recorded, but the background items above still get their labels.

## Faces
`python -m tools.mask_faces` fills the head of every detected person with grey (originals stay in `data/D5_unmasked/`, local only). The masked frames and the 44 unmasked ones (a person seated facing away, only the back of the head) were checked by eye. Dropped for a head turned toward the camera: shoe 018, backpack 037, wire_white 010 (`data/D5/_excluded/`). Frames excluded for other reasons (person walking by, wrong distance label, sitting pose with a face) are in the same folder.

## Tool notes
- `record_d5` numbers files from the highest index + 1; the first version reused numbers after frames were moved and overwrote 3 empty frames (re-recorded).

## Auto-labels (first pass, to correct by hand)
`python -m tools.autolabel_d5` (YOLO-World `yolov8s-worldv2`, 8 classes in `data/D5/classes.txt`) wrote YOLO-format proposals to `data/D5/labels/<folder>/<frame>.txt` (boxes with confidence >= 0.2; not committed, HNHL's hand-corrected labels in PR #63 use the same paths, rerun the tool to regenerate) and every box with its confidence to `data/D5/autolabel.csv` (threshold 0.05). They are proposals, not ground truth.

| Folder | Own class found in the frame (conf >= 0.2) | Notes |
| :-- | :-- | :-- |
| chair | 20 of 20 | good boxes; chairs in the background are found too |
| plant | 15 of 15 | good boxes (0.9); the big plant in the background of most frames is found everywhere |
| shoe | 39 of 49 (44 at 0.1, 48 at 0.05) | good boxes |
| backpack | 22 of 49 (29 at 0.05) | box is right but the label is often `chair` or `bag`: fix the class |
| bag | 2 of 50 (26 at 0.05) | box found but labelled `backpack`: fix the class |
| leg | **0 of 50** (33 at 0.05) | standing legs and bare feet are not found: draw the boxes by hand |
| wire_black, wire_white | **0 of 99** | as in the 2026-10-18 baseline, thin wires are never found: draw by hand (or segmentation, risk 30) |
| table | **0 of 15** | the table seen from below is not found (a small table in the background is): draw by hand |

Suggested route: hand-label about 20 frames per class, fine-tune YOLOv8n on them, re-label the rest with that model, correct again. The empty-floor frames hold plants (40), tables (29) and chairs (34) at >= 0.1: those are real background objects that keep their boxes (labelling rule), not false alarms.
