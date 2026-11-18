# Tower keep-out, pursuit with tower avoidance, dorm motion check (Wed 2026-11-18, dorm, flooring like the classroom)

One run per condition; the dorm floor veers the robot left by 40-70 deg over about 1.3 m on 3 of the 4 early runs (grout lines between tiles). Battery 11.5-12.3 V. Camera pose `camera_pose_self_1118_1.json` (pitch -6.9 deg, spread 0.04 deg).
Tower: 4 faces, ArUco DICT_4X4_50 ids 10-13, 50 mm prints, tower 5 x 8 cm. Range test of the markers: `../tower_marker_range_1118/`.

| Run | Strategy | Result |
| :-- | :-- | :-- |
| `avoid_e` (tape start 1.3 m) | timed manoeuvre: turn 90 deg away, 0.8 m sideways, turn back, clear (open loop) | passed, ended 1.37 m from the tower, 1.2 m off the line (target 0.8), heading 30 deg left of the start; 10.6 s of wheels |
| `steer_a` (tape start 1.3 m) | closed loop on the marker bearing (`TowerSteer`) | triggered at 0.887 m, bearing -7.6 deg; closest about 0.4 m by tape, never touched; ended beside the tower 0.86 m away, heading 54 deg left; 5.95 s of wheels |
| pursuit `d` (obstacle detector off) | pursuit + `TowerSteer` | 36.7 s, 3 tower avoids, 0 aborted; ended when the person was lost for 5 s (no search in that tool version) |
| pursuit `e` (obstacle detector off, `--search`) | pursuit + `TowerSteer` + spin-and-find | 120 s, 13 triggers, 12 avoids completed, one active at the time limit, 0 abort events; tracked 67.2 %, distance in band 9.2 %, centred 40 %. Four logged SEARCH episodes lasted about 0.05-2.1 s. Repeated pursue / avoid near the tower (6 times in the last 45 s). |

Runs `tower_pursuit_b` and `_c` (obstacle detector on, `--floor unknown` / `glossy`) never drove forward: two far chairs (3 m, box bottom at image rows 283-289, just below the horizon of the pitched-up camera) counted as near by the 0.55 image-height rule. Not a tower result; the detector was switched off for `d` and `e` (obstacle avoidance still open).

Motion check (`motion_check_dorm_2.txt`, anchors `anchors_dorm_1118.csv`: boards at 1.6 m ahead and 1.64 m at 45 deg left and right): FAIL against the Week 2 gains; 4 of 6 segments measurable, turn ratios 0.57 / 0.68, forward ratios 0.56 / 0.87, drift +0.17 / +0.83 rad/m (limit 0.05); the fit was refused (forward ratios scatter 0.56-0.87 > 0.15). The segments are short (0.4 s spins, 0.4 m drives), so the ratios are noisy. Not a graded item.

Files: `*_avoid_2.csv` per-frame logs (t, seen, id, range, bearing, side px, command, phase); `pursuit_e_log.csv` / `*_summary.json` from `tools.pursue_live`; `tower_runs_summary.csv` all trial rows (the approach run without a tower and the early `avoid_a..d` rows included). Start pictures show a person and are not committed.

HNHL review added command expiry, startup battery/video-IP checks and a critical-obstacle check on the trigger frame after these runs. CPU regressions cover the changes. The committed runs record the earlier tool version. The three HOLD rows in pursuit `e` span about 0.14 s of logged state, with no timed stand-still protocol.
