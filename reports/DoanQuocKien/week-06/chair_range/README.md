# Chair box width as a range fallback on the glossy floor (DQK, 2026-11-13)

For HNHL (perception owner). Proposal and data, not a detector change.

**Problem (known since 15/10, experiment B on 9/11):** on the glossy classroom tile the chair's floor contact is `reflection_unresolved`, so the obstacle detector gives no distance (today: chair detected at conf 0.95, no ground distance; `explore_live` refuses to start).

**Idea:** range from the chair's box size instead of its floor contact (the same idea gave <= 0.05 m for the door).

**Data:** `../classroom_1111_pm/data/chair_range_frames_1113_blurred.zip` (6 taped distances 0.6-2.4 m, 12 frames each, a person in the background blurred out; `README.txt` inside) and `../classroom_1111_pm/data/chair_width_range_1113.json` (numbers). Recorder: `tools/record_chair_ranges.py` (robot standing still, no commands).

**Result (YOLOv8s, class 56, nearest chair = lowest floor contact):**
- one chair, front-on, left third of the picture: box width 138 / 112 / 94 / 77 / 61 px at 0.9 / 1.2 / 1.5 / 1.8 / 2.4 m; fit distance = 160.3 / width - 0.24, leave-one-out max error 0.05 m (height: 0.11 m); at 0.6 m the chair back leaves the picture (height unusable).
- the 9 tape-measured chairs of 15/10 (`data/D1_obstacles_1015`, rows matched by order of floor contact): errors -0.16 to +0.28 m, 7 of 9 within +/-0.16 m, median absolute error 0.12 m; the worst two are the 0.32 m and 1.90 m ends.

**Limits:** one chair type and day for the fit; a wider or rotated chair reads nearer or farther; the largest-box rule picks the background chairs (use the lowest floor contact); not wired into any detector; 0.6 m and closer needs the width, not the height.

**Asked of HNHL:** whether this is worth evaluating on D1/D5 with more chair types and angles as a fallback when the contact is unresolved; the decision on the detector is yours.

**Why it matters for `sentry/nav/explore.py`:** its rule for an unresolved obstacle ('near when the box bottom is below 55 % of the image height') cannot separate near from far with this camera: the chair's box bottom was 336 / 322 / 318 / 312 / 309 / 304 px at 0.6 / 0.9 / 1.2 / 1.5 / 1.8 / 2.4 m (264 px is the threshold), so every unresolved chair in view blocks. The box width (above) does separate them; a width threshold of about 112 px (about 1.2 m) would be the data-supported replacement. Not implemented (safety logic, no robot test).
