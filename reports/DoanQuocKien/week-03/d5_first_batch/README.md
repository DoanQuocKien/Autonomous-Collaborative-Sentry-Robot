# D5 first batch (DQK, 2026-10-24, glossy floor, one room)

Floor-level objects from the robot's own camera (lens 0.10 m), recorded with `python -m tools.record_d5 <class> --floor glossy --dist <m> --n <N>`. The images stay in `data/D5/` (not in git; people are in some frames), listed in `data/D5/manifest.csv` (class, file, floor, tape distance, session, time).

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
