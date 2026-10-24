# T2 dead reckoning over 3 m with ArUco correction (DQK, 2026-10-24, glossy tile, battery 11.3 V)

Layout (x forward along the string from the start cross, y left): board A (id 0) straight ahead, boards B (id 1) and C (id 2) on the right at y = -0.7 m and x = 1.5 and 2.5 m, facing the string; marker centres 0.207 m above the floor. Tape-measured end position (forward, left, heading) from the start cross.

| Run | Drive | True end | No correction | With correction (59 marker updates in run 2) |
| :-- | :-- | :-- | :-- | :-- |
| 1, `t2_1024_1` | open loop, v = 0.7 for 10.6 s, no steering | 1.66 m, 1.30 m left, 60 deg left | 186 cm | 158 cm (5 updates, then all boards left the view: the robot faced 60 deg to the left) |
| 2, `t2_1024_2_follow` | **closed loop**: PI steering on the bearing of board A (`dr_path --follow 0 --stop-m 0.8`), stopped itself 0.79 m from A | 2.95 m, 0.05 m left, 0 deg | 98 cm | **14.5 cm** at speed scale 1.0 (15.5 / 16.5 / 17.3 cm at scale 0.9 / 0.8 / 0.72) |

Target (Implementation Plan 4.3): <= 15 cm with correction, <= 40 cm without.

## Reading the result
- **With correction: 14.5 cm, met by 0.5 cm at the nominal scale, not at the other scales tried.** One run only. It depends on the surveyed board position: board A was first entered as 3.8 m, then corrected to 3.6 m after a re-measurement; with 3.8 m the same run gives 4-7 cm (`anchors_A38.csv`), with 3.6 m 14.5-17 cm. The truth is the tape: the marker distance reported at the end (0.79 m) was 14 cm longer than the tape-based 0.65 m, so a hand-measured layout limits the result to about this size.
- **Without correction: 98 cm, target not met, and cannot be met with steering on.** Without an IMU the estimator integrates the commanded turn: the controller steered right by about 0.016 w to cancel the left veer, so the integrated heading ends at -52 deg while the real robot ended straight. An IMU (MPU6050, tbd) would remove this. Open loop (run 1) the no-correction error was 186 cm because the robot curved 60 deg left, which the commands do not show.
- The open-loop drive curves hard and unpredictably on this floor and battery (50-60 deg left over about 2 m, also on 2026-10-18), so a straight command cannot be corrected afterwards: the boards leave the view.

Run 2 also stopped with the steering integral at -0.0143 (the learned trim, about 10 deg/m).

## Files
`commands.csv` (time, v, w as sent), `summary.json` (replay at four speed scales, with and without correction), anchors CSVs. The camera frames (81) are not committed (people may be in them).
