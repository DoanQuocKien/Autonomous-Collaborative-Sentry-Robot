# ESP32 placement handshake, cafe rehearsal (DQK, 2026-10-28)

Plan 4.3 row 'ESP32 handshake' (T2): the entrance detector (`sentry/perception/entrance.py`, XFeat + RANSAC, policy `auto`, `enroll_esp32`) on the ESP32's OWN frames must say "door in view" when the camera faces the door and "not in view" when it is turned away; target **10 of 10 correct accepts and 10 of 10 correct rejects**. Run with `tools/handshake_test.py` (ref, sweep, trials, eval). **This is a rehearsal in a crowded cafe, not the plan's test: the plan's door is the classroom door** (to be repeated there).

Setup: the ESP32 (OV2640, MJPEG, firmware of PRs #72-#77) held in the hand on its USB cable. "Door" = the arched opening with the red posters and the fan. Reference: 5 frames, about 2 m. Calibration: 168 frames of a 25 s sweep of the room with the door not in view (XFeat threshold 27 inliers, the default minimum; the sweep never needed a higher one). Trials: 20 segments of 5 s, alternating accept (face the door from about 1.5-3 m, position and angle varied) and reject (turn away), the first 1.5 s of each not scored; a trial is "in view" when at least half of its scored frames are (the rule was fixed before the run).

| Result | |
| :-- | :-- |
| Correct accepts | **9 of 10** (target 10 of 10: not met) |
| Correct rejects | **10 of 10** (met) |
| Reject trials | 0 to 14 % of frames in view, median inliers 12 to 15 against the threshold 27: a wide margin |
| Accept trials | median inliers 22 to 174 (100 % of frames in view down to 43 %) |

The missed accept is trial 11 (43 % of frames in view, median 22 inliers against 27). Its frames show the arch from farther than the 1.5-3 m of the protocol (the arch and posters are small in the picture), people walking through the doorway in front of it (a backpack covers the arch in several frames), and the camera rotated. So the cause is the test conditions, but the trial counts as run. Also present in every frame: the laptop screen in the left edge of the view (the reference had none), which did not stop the other nine accepts.

Limits: one door, one session, cafe light, bystanders crossing the door area, a hand-held camera; the decision is by majority of frames (the state machine's own `EntranceFilter` needs 3 consecutive in-view frames, a different rule that was not scored). Frames stay local (`data/handshake/`, git-ignored; they show bystanders). Per-trial numbers: `cafe_arch_results.json`.

**Decision 2026-10-28 (DQK, the team lead): accepted as a pass for this rehearsal** (cause of the miss: a farther view and bystanders crossing the door). The measured numbers above are unchanged; the real test is still the classroom door.
