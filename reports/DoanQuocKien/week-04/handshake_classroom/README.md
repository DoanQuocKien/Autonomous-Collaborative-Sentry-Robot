# ESP32 placement handshake at the classroom door (DQK, 2026-10-30, solo)

Plan 4.3 row 'ESP32 handshake' (T2): target **10 of 10 correct accepts and 10 of 10 correct rejects**. Tool `tools/handshake_test.py` (ref, sweep, trials, eval), the entrance detector on the ESP32's own frames (XFeat + RANSAC, `enroll_esp32`), ESP32 OV2640 held in the hand, hotspot, classroom door (double door with glass panels, a glazed partition to its side, windows with blinds on another wall). The decision rule was fixed before the run: a trial is "in view" when at least half of its scored frames are (the first 1.5 s of each 5 s segment are not scored).

Reference: 6 frames from about 2 m (second attempt at the setup: the first test frame showed the door too close and the laptop's edge in the picture, so the laptop was moved). Calibration: 222 sweep frames (111 used) of windows, walls, ceiling and floor, the door never in view; XFeat threshold 27 inliers. 20 trials of 5 s, alternating.

| Result | |
| :-- | :-- |
| Correct accepts | **7 of 10** (target 10: **not met**) |
| Correct rejects | **9 of 10** (target 10: **not met**) |

Failures, with what the frames show (the causes are my reading of the pictures, not proven):
- **t01 accept** (49 % of frames in view, median 26 inliers against 27): starts on a plain wall and swings to the door late; mostly the transition, just under the rule.
- **t13 accept** (25 %, 14 inliers): starts on a window and reaches the door only at the end; the stream stalled (16 scored frames of about 60).
- **t19 accept** (32 %, 19 inliers): the door is very close and at an angle (a different scale and view from the 2 m reference); a dark object, probably the laptop corner, in the right edge of the frames.
- **t18 reject** (68 % in view, median 40 inliers): the camera swept windows, the ceiling and the glass partition beside the door, whose glass panels resemble the door's: a false accept.
- Stream stalls in three accept trials (t07: 8 frames, t11: 27, t13: 37 of about 60): the ESP32 side, not the detector; t07 and t11 still passed with few scored frames (5 and 7).

Limits: one door, one session, hand-held camera (about 10-15 degrees of roll in the reference), trials started late by the operator in some segments, no re-run. The cafe rehearsal of 2026-10-28 was 9 of 10 and 10 of 10 (PR #80). The state machine's own rule (`EntranceFilter`: 3 consecutive in-view frames) is a different rule from the majority rule used here and was not scored. Frames stay local (`data/handshake/class_door`, git-ignored).
