# Classroom session 2026-11-14 (all three members, 2 hours): task list, decisions, schedule

Written 2026-11-13 night by DQK from `docs/Implementation Plan.md` (section 4.3 rows, "Carried over" list), `docs/Classroom Session Deployment Checklist.md` (its own durations: setup 15 min, Part A 15 min, Part B 45 min, Part C 30 min) and the evidence README `reports/DoanQuocKien/week-06/classroom_1111_pm/README.md`. Constraints: **120 minutes**, three people, one robot, **one ESP32 stream client at a time** (impostor test, handshake and deployment cannot overlap), figures frozen Mon 2026-11-16, internal draft Wed 11-18, report Mon 11-23.

## 1. Every open item that needs the team, the door or the room

| # | Item | Status now | What it unlocks in the report | Cost (min) | Decision |
| :-- | :-- | :-- | :-- | :-: | :-- |
| 1 | **F3 photo** (JetBot, gamepad, ESP32 tower at the door, all three in one place) | missing, no substitute | a mandatory figure of the Mid-Term Report Plan | 5 | **DO (must)** |
| 2 | **Impostor scores for the door camera**: HNHL and KR enrol with `tools.enroll_guided`, then each stands at the taped 1.8 / 2.4 / 3.0 m marks (looking at the lens and away); DQK too; every frame is scored against all three enrolments | one person only (DQK, 100 % of straight frames >= 0.45); no FAR; 0.45 not validated | the only way to state a TAR/FAR for the door camera (plan row D2: TAR >= 95 % at FAR <= 1 %) | 15 recording + 3 each enrolment (in parallel with setup) | **DO (must)** |
| 3 | **T2 deployment: the 5th counted run and a rerun with the board-loss fix** (4 of 5 counted on 10-30; `deploy_live`, handshake verified, STANDBY, 0 collisions, tape 1.5-3.0 m) | 4 of 5; the other runs lost the board | plan row 'Sweet-spot selection' 5/5 | 35 (layout 5, rehearsal + dry run 10, two supervised runs about 7 each, buffer) | **DO (must)** |
| 4 | **ESP32 handshake**: `ref` with the tower placed at its real spot (needed by item 3), then the negative check (aimed away must not verify) | two 10/10 + 10/10 passes already (11-09, 11-11); 7/10 and 9/10 on 10-30 | confirms the plan row on the final tower placement | 3 for `ref`; the full 20 trials (Part A, about 15) | **ref: DO; full retest: DO IF TIME (decision gate at minute 50)** |
| 5 | **Demo-video shots** (entrance found, sweet spot, prompt, camera placed, verified, standby) | none from the final system | the 2-4 min video (cut by Wed 11-18) | 0 extra: film during items 2-4 | **DO (KR films)** |
| 6 | Part C: Phase 1 chain, `deploy_live --door` with the declared room | never run on the robot | plan row 'Phase 1 end to end' | 30 + 15 measuring the room | **DROP**: needs the room declared by tape (box, walls, door) and the table problem makes the 3 x 3 m box tight; report as "in progress with its plan" |
| 7 | Phase 2 live at the door (ESP32 -> face -> re-ID -> queue) | **no live tool exists** (`tools/replay_phase2.py` replays recorded frames only) | plan row 'Phase 2 live' | would need building first | **DROP** (cannot be run tomorrow whatever the time) |
| 8 | Pursuit PD / standoff-hold protocols, Phase 2 -> 3 chain on the robot | first supervised runs only (F17); no step response, no hold timing | plan rows 'Pursuit PD', 'Standoff hold', 'Full loop' | 25-40 each, needs a walking person and floor | **DROP**: report the first runs as "in progress" (what the figure freeze allows) |
| 9 | Optional solo robot follow-ups (forward steady speeds, trim A/B, alignment test, the swerve test) | open, none required | statistics only | 5-10 each | **DROP** (not session time) |
| 10 | Obstacle avoidance on the glossy floor | blocked: no distance for chairs (`reflection_unresolved`); only the chair-width proposal (PR #110) | nothing to run | - | **DROP** |

Not session time (asynchronous, do before Mon 11-16): HNHL reviews #108, #109, #110; KR addresses the changes requested on #101; DQK logs the Week 6 hours.

## 2. Time budget (120 min) and decision

Must items (1, 2, 3, ref of 4) cost **5 + 15 + 35 + 3 = 58 min**; setup 15 and wrap-up 12 bring it to **85 min**, leaving **35 min** of buffer. Past sessions overran (the 10-30 session spent all its time on Phase 1), so the buffer is kept thick. Decision: **everything marked DO fits; the standalone handshake retest (about 15 min) fits only if the gate at minute 50 is met; items 6-10 do not fit and are dropped with a stated reason.**

| Minutes | Block | Who | Output |
| :-- | :-- | :-- | :-- |
| 0-15 | **Setup**: charge check (>= 12.2 V), hotspot (2.4 GHz, battery saver off), `jetbot_status`, ESP32 tower at the door 1.8 m from it (taped marks at 1.8 / 2.4 / 3.0 m), `self_pose` (the mount moved 16 deg during the dorm session), e-stop armed | DQK robot + `self_pose`; HNHL and KR tower, marks, **enrol with `enroll_guided` in parallel** | all checks in the notes |
| 15-18 | Handshake `ref` with the tower in place (`tools.handshake_test ref --name class_door_1114`) | KR holds, DQK runs | reference for item 3 |
| 18-33 | **Impostor scores** (recording 3 people x 6 clips; ESP32 stream used by this block only) | HNHL runs and scores, KR/DQK stand | one JSON per subject, all frames local |
| 33-68 | **T2**: layout (cleared floor, board, tape coordinates), laptop rehearsal (`--no-robot`) including the negative check, dry run, two supervised runs with R1 | DQK operator (R1), HNHL laptop, KR films | `data/deploy/t2_*` summaries + answers captured at run time |
| 68-78 | **F3 photo** and the remaining shots | KR | photo, clips |
| 78-90 | Wrap-up: copy evidence to `reports/<handle>/week-07/`, shut down (5 W, `shutdown -h now`, ESP32 off), note what is open | all | commits Sunday |
| 90-120 | **Buffer** (re-run of a failed T2 run, or Part A) | | |

**Decision gate at minute 33** (after the impostor block): if it ended on time, insert the standalone handshake trials (Part A, 15 min) before T2 and start T2 at minute 48; this uses 15 min of the buffer and pushes the later blocks back by the same amount. If it ran late, skip Part A: the T2 runs include a handshake verification each, and the rehearsal includes the negative check.

## 3. Go / no-go checks at minute 0

- Battery < 11.4 V: no graded robot runs (charge first; plan rule), run items 2 and 1 only.
- ESP32 stream below 5 fps at the door: fix the link (phone closer, channel) before items 2 and 4; do not record impostor clips below 5 fps.
- Camera pitch: take `self_pose` first; every tool that converts image rows to floor distance needs the new pose file.
- Whitelist: `data/whitelist/DQK.npz` exists on DQK's laptop only; HNHL's and KR's enrolments are made in the session on their own laptops and copied (`.npz`, embeddings only) to the scoring laptop.

## 4. Prerequisites, tonight

- **HNHL and KR:** run `python -m tools.check_env`, then `python -m tools.enroll_guided --help` and a first dry enrolment with their webcam (needs OpenCV with GUI, insightface, a webcam); KR has no CUDA: `--device cpu` is the default and enough. Do **not** commit the `.npz` (git-ignored under `data/`).
- **DQK:** charge the robot to >= 12.2 V; put the impostor recorder/scorer in the repo (`tools/door_recognition_seq.py`, from the scratch script used on 13/11) with a test; message to HNHL and KR.
- **Everyone:** consent for face frames to be recorded and kept local (the recorded frames stay under `data/`, never committed; only the numbers go to the report).

## 5. How the report states what was dropped

Items 6-10: "in progress, with the plan and the blocker" (Phase 1 chain: needs the declared room; Phase 2 live: no live tool, replay only; pursuit/hold: first supervised runs only; obstacle distance: unresolved on the glossy floor, chair-width fallback proposed). This follows the plan's own rule: what does not work by the freeze is reported as in progress, not rushed.
