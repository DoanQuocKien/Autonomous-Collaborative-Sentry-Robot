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

## Decision 2026-10-30 (DQK, the team lead): accepted as a pass for the plan's handshake row
The measured numbers above are unchanged (7 of 10 accepts, 9 of 10 rejects; the target of 10 and 10 is NOT met by the measurement). **Revisit this decision, and use the traceback below, if any later run of the deployment fails at the handshake or the report is questioned.**

### Notes for the traceback (what to check first if the handshake misbehaves later)
1. **Both error types happened, so neither side of the threshold is safe.** A false reject (accept trials t01, t13, t19: 49 %, 25 %, 32 % of frames, inliers 14-26 against the threshold 27) and a false accept (reject trial t18: 68 % of frames, median 40 inliers, the glazed partition beside the door). The XFeat threshold 27 comes from the calibration sweep (222 frames, 111 used); a different sweep gives a different threshold. In the cafe rehearsal it was also 27.
2. **The glazed partition next to the door looks like the door's glass panels.** If a real run verifies with the camera aimed at the partition, that is this effect. Mitigation to try: include frames of the partition in the calibration sweep (they were not in it: the sweep avoided "the door and its frame"), or add a second reference frame of the partition as a negative.
3. **Distance and angle sensitivity.** The reference is from about 2 m, level to about 10-15 degrees of roll. Views from under about 1.5 m or at a sharp angle (t19) gave 14-26 inliers. The spec window is 1.5-3.0 m: keep the ESP32 at 1.5 m or more when placing it, and re-take the reference from the position the camera will really have.
3b. **Stream stalls.** Three accept trials had 8, 27 and 37 frames of about 60 (the ESP32 stream, Wi-Fi). With few frames a trial is decided by very few results (t07 had 5 scored frames and passed). Check the frame rate first when results look odd: `python jetson/mjpeg_probe.py http://<esp>:81/stream`.
4. **The decision rule matters.** Here: at least half of the scored frames (the rule fixed before the run). The state machine uses 3 consecutive in-view frames (`EntranceFilter`); the secondary evaluation in this folder reports that too, labelled as chosen after the primary result.
5. **Operator effects** in this run: late arrival at the door in some segments (t01, t13), the laptop corner in the picture in some frames (t19), no second run. A rerun with the operator rules of the README above is the cleanest way to separate the detector from the operator.
6. Files: `data/handshake/class_door/` (local, git-ignored: ref, sweep, 20 trial folders, `results.json`), the committed per-trial numbers `class_door_results.json`. Tool and tests: `tools/handshake_test.py`, `tests/test_handshake_test.py` (PR #80).
