## 8. Measured limits to state in the report (DQK, 2026-11-09)

**Monocular floor ranging with a 0.100 m lens is weak beyond about 1.5 m.** A floor point at distance d is H/d below the horizon, one pixel is about 0.19 deg (f about 306 px), so the range error per pixel is about d^2 x 0.0033 / H:

| lens height H | per pixel at 1.2 m | at 1.8 m | at 2.4 m |
|---|---|---|---|
| 0.10 m (the kit, now) | 0.05 m | 0.11 m | 0.19 m |
| 0.20 m | 0.02 m | 0.05 m | 0.10 m |
| 0.30 m | 0.02 m | 0.04 m | 0.06 m |

Measured (home wooden floor 2026-11-06 to 11-08, and the CLASSROOM glossy tile floor with 0.6 m tiles on 2026-11-09 (DQK corrected the label on 11-09: the tile trials, the motion test, the 1.8 m static check and `self_pose` `1109_*` were in the classroom), one person; `reports/DoanQuocKien/week-05/home_1107/`): the detector box bottom sits 3-7 px below the visible feet and varies between sessions and with the stance, which is 0.4 m at 1.7 m; with the 3.5 px offset a still person on the 1.8 m tile read 1.71 m (-0.09 m); driving did not change the view at rest (box bottom within 1.2 px after forward-and-back bursts). In the live runs the pursuit runner read about 1.3 m when the tape and the box height said about 1.7 m, so it stopped early (the standoff dead band takes the short reading for 'arrived'). The pursuit and hold results are therefore first supervised live trials with these limits, not acceptance numbers. The camera mount also moves with handling (pitch -4.26 to -0.64 to -4.61 deg over two days, cause per DQK: mount and movement): `self_pose` before every run.

**Not done, proposals (design changes, none planned before the mid-term):**
1. **A higher camera mount** (0.2-0.3 m) improves the range resolution 2-3 times, and keeps heads in the frame. It would change the viewpoint of D1, D2 and D5 (re-record, re-validate the obstacle layer and the floor-level classes) and is a hardware change on school property.
2. **More upward tilt** (about 5 deg more, about 10 deg up) keeps the head of a person in the frame down to about 1.4 m and keeps the floor visible from about 0.2 m; it does not improve the foot-row resolution.
3. **A better model:** a person segmentation mask for the floor contact (less box-margin noise), or a metric monocular depth model on the laptop (independent of the camera height; unvalidated here, would need the tape-mark protocol on the 1.2, 1.8 and 2.4 m tiles and a fisheye undistortion first). A better detector alone does not remove the pixel-resolution limit above.
4. **Not adopted:** a per-person height constant (conflicts with following arbitrary intruders); ankle keypoints (the ankle is about level with a 0.100 m lens, the floor intersection is meaningless).
