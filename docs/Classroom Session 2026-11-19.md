# Classroom session Thu 2026-11-19 (all three members): what only the classroom can do

Decision 2026-11-16 (DQK, team leader): the remaining video shots are recorded here, in the classroom, with all three members (the only day all three are free); the video cut moves to Fri 11-20 - Sat 11-21, final Sun 11-22. The report's numbers and figures stay frozen on 11-16: anything measured on 11-19 is added only if marked "added after the freeze", otherwise the item is reported as in progress. This file lists everything left that cannot be done off-session. Everything that could be done on 11-16 evening is done (see `reports/DoanQuocKien/week-07/classroom_1116/README.md`, PR #125, plan entry PR #126).

## Before anyone films (DQK, 15 min)
1. `python -m tools.jetbot_status auto`: battery >= 11.1 V (stop < 10.5 V). Decide the power mode and write it on the shot list: the 11-16 runs were in 5 W mode; `sudo nvpmodel -m 0` (MAXN) is what the benchmarks used.
2. Camera pose with `python -m tools.self_pose --page-bottom-h 0.0` (the mount moves whenever the robot is handled; -8.0 deg on 11-16).
3. ESP32 IP (`python -c "from sentry.net import discover; print(discover.find_esp32())"`; 10.169.60.9 on 11-16), tower aimed at the door, floor clear. New handshake references and sweep (`tools.handshake_test ref` / `sweep`, door NOT in the sweep) if the tower spot changed; the 11-16 references are in `data/handshake/class_door_1116` (local).
4. The robot has the audit-fix code since 11-16 (e-stop checked wheels-up); control packets are still unsigned (no control key): decide whether to create one (`docs/Setup.md`) or state "unsigned" again.

## Shots (Mid-Term Report Plan section 5; recorded on 11-16: entrance found, sweet spot, pursuit)
| # | Shot | Needs | Notes |
| :-- | :-- | :-- | :-- |
| 5 | Prompt -> camera placed -> handshake verified -> reverse to STANDBY (a real T2 run, filmed from the start) | robot, ESP32, tower, 1 operator | `deploy_live` command of the 11-16 run (`reports/.../classroom_1116/README.md`); the tower goes in front of the stop point after the robot stops; R1 held to the two beeps |
| 6 | ESP32 view: an enrolled member walks in -> whitelisted; a member NOT enrolled in that fold -> intruder -> queued | the three members, HNHL's Phase 2 live (#114, #115) | Dry run first (never run end to end on the robot); leave-one-out as in the plan D2 |
| 7 | Pursuit then hold and re-centre when the target stops | robot, one person, R1 | DQK decided on 11-16 that HOLD needs no more session time; film it only if time is left (the 11-16 run reached 32 % in band, not an acceptance run) |
| - | The intruder sequence and the full loop | all of the above | only if shots 5 and 6 are done; whatever does not work is cut or captioned, not rushed |
| 2, 3, 4, 8 | boot / R1 stop, live stream overlay, exploration with obstacle boxes, GPU and Jetson bench | - | not confirmed on file: check which of these exist before Thursday, record the rest or use the captioned replay/`sim_robot` fallback |

## Data that needs people in the room
- Re-enrolment of KR with varied poses (`tools.enroll_guided --person-id KR --out-dir data/whitelist_new`, 5 poses, max 5 embeddings per person) and an impostor-score run with someone outside the team (consent first); DQK's re-enrolment on 11-16 did not change his TAR (0.930).
- One more pursuit run for F17 only if wanted (distance, 1.2 m start, with a stand-still of 4 s for the HOLD timing).

## Not classroom, but not done yet (no rush before the freeze; record outcomes)
- Motion check: deferred to the dorm by DQK (3 boards at about 1.5 m, front, 45 deg left, 45 deg right, all facing the robot, default 2.2 m limit). Not a graded item; until then the Week 2 gains are used and named as a known limit.
- Tower avoidance in pursuit (markers on the tower faces, keep-out disc, adapter into `observe_obstacle`): needs robot tests; stated as a known limit in the report.
- Reviews: #125 and #126 (mine, need one review each from HNHL or KR), #113 (KR, blocked by the D5/D2 deletions and stale report lines; two reviews of changes requested + a follow-up comment).
- Report: chapters 3, 4 and 8 carry the 11-16 numbers (this PR); the internal draft is Wed 11-18; PR freeze Fri 11-20; tag `midterm` Sat 11-21.

## After the session
Robot return notes (`docs/JetBot Notes.md`, only the final return is a full undo): `tools.jetbot_status` at the end, 5 W mode (`sudo nvpmodel -m 1`) when idle, clean shutdown (`sudo shutdown -h now`) and charge. Evidence into `reports/<handle>/week-07/classroom_1119/` with a README of conditions and every failure.
