# Tower marker range, driven test (dorm, 2026-11-18)

Tool: `python -m tools.tower_marker_trial reverse 0.35 --yaw <deg> --label <x>` (PR #131). The robot starts 0.35 m (tape, lens to tower) from the tower with a marker in view, drives backward at v = -0.5 (about 0.2 m/s, wheels on the floor, e-stop armed, R1 held) and stops 0.3 s after the last frame with an id 10-13 marker. The end distance is taped. Markers: 50 mm prints (edge not measured), one per tower face. Dorm floor, similar to the classroom. Battery 12.2-12.3 V.

| Tower angle (face turned away from the camera) | Marker lost at (tape) | Last marker size | Frames with the marker |
| :-- | :-- | :-- | :-- |
| 0 deg (id 10 face-on) | 1.64 m | 9 px | 100 % to about 0.6 m, 60 % at 1.3 m |
| 30 deg | 1.23 m | 11 px | 100 % to about 0.5 m, 50 % at 3 s (about 0.9 m) |
| 45 deg (worst case for four faces) | 1.07 m | 13 px | 100 % to about 0.5 m, 30 % at 3 s |

- One run per angle; not an acceptance result. The id 12 face straight on was not run.
- The PnP range is not reliable at 9-11 px (1.32 m reported against 1.64 m taped at 0 deg); use the tape column. Inside 1 m it was within 6 %.
- The first run (`tower_a_approach_1`, 1.94 m approach) is not included: the tower was not in view (the robot veered), so it says nothing about detection.
- Per-frame data: `tower_*_reverse_2.csv` (t, seen, id, range_m, bearing_deg, side_px, cmd_v); start pictures `*_start.jpg` (taken by the tool before the beeps for the 3 runs; the 0 deg picture is of the face-on setup).
