# T2 deployment runs, 2026-11-14 (classroom, JetBot + ESP32-CAM)

Setup: robot servos on ArUco board 0 (`--servo-stop 1.33`), robot starts about 3.3 m from the board (bearing about -10 deg), ESP32 tower at the door, handshake references `class_door_1114` (7 refs). No obstacle stop (R1 only). Battery 11.7 V. Frames stay local (data/deploy/).

| Run | Result | Time to stop point | Handshake (in view / frames, last inliers) | STANDBY | Door (tape, robot) | Wall | LoS | Collisions |
|---|---|---|---|---|---|---|---|---|
| t2_1114_8 | pass | 14.8 s | 109/109, 409 | 18 s | 2.94 m | 0.30 m | clear | 0 |
| t2_1114_9 | pass | 23.5 s | 163/163, 378 | 26.6 s | 2.94 m | 0.45 m | clear | 0 |

Board 0 after the run (tape, ahead/right): run 8 1.48/0.45 m (1.55 m), run 9 1.54/0.46 m (1.61 m); target 1.33 m. Tower to door: 2.45 m (run 8 placement). The ending positions differ by about 6 cm; the door ends at 2.94 m instead of the planned 2.5 m, inside 1.5-3.0 m but near the far edge.

Not counted: t2_1114_5 and _6 (R1 released 4-5 s after the stop), _7 (start 3.54 m from the board: marker found in 1 of 43 frames in the first 10 s, approach timed out at 1.70 m from the board). First launch attempts were also lost to a tower aimed at the ceiling (handshake 0/44 in view) and a launcher waiting on a password prompt; no motion command was sent in the latter. A start beyond about 3.4 m from board 0 is not reliable.

Counted T2 runs: 6 (4 on 10-30 + runs 8 and 9). Tape offset from the sweet spot was not measured in the start frame.

## Door-camera recognition, three people (plan row D2)

Tool: `tools/door_recognition_seq.py` (record + score), test `tests/test_door_recognition_seq.py`. Enrolments: `tools.enroll_guided`, 5 poses each (DQK, HNHL, KR), webcam of the laptop. Recording through the ESP32 door camera (12.5 fps) at taped 1.8 / 2.4 / 3.0 m from the lens, per mark: 8 s looking at the lens, 8 s turned away to the right, 8 s turned away to the left. Every frame is scored against all three enrolments (max cosine over the enrolment vectors, largest face), threshold 0.45. Frames stay local (`data/door_recog/door_1114/`); `scores_*.json` hold numbers only.

| Subject | TAR 1.8 m | TAR 2.4 m | TAR 3.0 m | TAR all | Straight frames |
|---|---|---|---|---|---|
| DQK | 0.891 | 0.900 | 1.000 | 0.930 | 300 |
| HNHL | 0.980 | 1.000 | 0.970 | 0.983 | 299 |
| KR | 0.860 | 0.952 | 0.874 | 0.892 | 278 |
| pooled | | | | **0.936** (821/877) | 877 |

FAR: 0 of 1754 impostor scores reached 0.45; the highest impostor score is 0.323. A face was detected in every straight frame, so the misses are scores below 0.45 (not lost faces). Plan row D2 (TAR >= 95 % at FAR <= 1 %): FAR met, pooled TAR 93.6 % is below the target (only HNHL reaches it alone). The misses do not follow the distance (DQK is worst at 1.8 and 2.4 m, KR at 1.8 and 3.0 m); the cause is not established (enrolment quality is a suspect, not shown). With three people the threshold 0.45 is not validated and not changed.

Quality notes: a first DQK recording was discarded because the poses ran one cue ahead at 3.0 m (head turned during the "lens" clip); the scorer now reports, per mark, how many "straight" frames are frontal and how many "away" frames are turned (|yaw ratio| <= 0.25 / >= 0.30). HNHL's away clips are turned less than that cutoff (94/203, 29/191, 100/199 frames); the away frames are reported apart and do not enter TAR/FAR. Per-frame scores are not stored in the JSON.

## Status at the end of the session (2026-11-14)

Done: T2 runs 8 and 9 (counted runs: 6 in total, plan row met); handshake references and sweep for `class_door_1114`; impostor scores with three people; robot at 5 W and shut down (battery 11.66 V before shutdown).
Left: F3 photo (devices only, no people needed) and the demo shots (need the robot on); re-score with per-frame values and possibly re-enrol KR/DQK with more varied poses (Monday); impostor scores of a person who is not enrolled and not in the team (more than 3 subjects); Phase 2 live (owner HNHL, issue #114); reviews and the items listed in the session plan.
