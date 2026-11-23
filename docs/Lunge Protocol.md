# Padded Lunge Protocol (D4), draft of 2026-11-23

Status: DRAFT written by DQK (team leader). Values marked **(to confirm)** are proposals to settle on Thursday 2026-11-26 before recording. Spec/plan references: `docs/Implementation Plan.md` section 4.2 (D4) and the strike-detection acceptance row (recall >= 90 %, <= 1 false trigger / 5 min of walking, <= 150 ms frame to command).

## 1. Purpose
D4 is the dataset to tune and test the lunge detector (`dA/A > 0.40` within 100 ms, or fast ankle rise) and the evasion trigger. It has two parts: 20+ padded lunges (positives) and 10 min of normal activity (negatives, for the false-trigger rate). **Nobody is ever struck.**

## 2. Safety rules (stop the session if any is broken)
1. Soft prop only: pillow, rolled towel or pool noodle on a cardboard tube or stick, at most 1 m long. No hard object at the moving end. The thruster holds the far end.
2. Thruster stops at the tape line **0.8 m from the robot** at the closest. Never touch the robot, never aim at the camera lens, never aim at a person.
3. Robot motors are **disabled** (no packets, or wheels off the ground) for all D4 recording. Evasion trials with the robot moving are a separate step (section 7) with R1 held and the e-stop armed.
4. Clear floor of 1.5 m behind and beside the robot. No cables or chairs in the lunge lane.
5. One person at a time in the lane. Everyone else is outside the 3 m marks.
6. Anyone says "stop" and everything stops. Battery 11.1 V or more (`python -m tools.jetbot_status <ip>`).

## 3. Roles (to confirm)
| Role | Who | Job |
| :-- | :-- | :-- |
| Thruster | HNHL, then KR | performs the lunges and the walking |
| Labeller | KR | presses the key at each onset with `tools/label_events.py` (must exist before the session) |
| Operator | DQK | runs `python -m tools.record D4`, robot and battery, phone side-view video, calls "stop" |

## 4. Set-up
- Robot standing still in the lane, camera facing the thruster, laptop recording with `python -m tools.record D4 --no-esp32` (JetBot frames plus both clocks).
- Floor tape on the 0.6 m tiles at **3.0, 2.4, 1.8, 1.2 m** from the robot, plus a stop line at **0.8 m**. Mark the lane centre; add a second lane 0.6 m to the left and right for off-axis lunges.
- Phone on a tripod to the side at 240 fps if available (also used for the reaction-time measurement); record a clap or a held-up clock at the start so phone and laptop clocks can be aligned.
- Lighting: classroom lights as normal; do one set with the window brighter if time allows.

## 5. Positives: 24 lunges (minimum 20 valid)
A lunge is a fast commit toward the robot: one step forward plus the prop thrust, starting from standing still. Onset = the first visible movement toward the robot.

| Set | Start distance | Style | Reps |
| :-- | :-- | :-- | :-- |
| A | 2.4 m | step + thrust, fast | 4 |
| B | 1.8 m | step + thrust, fast | 4 |
| C | 1.8 m | thrust only (arm and prop, feet stay), fast | 4 |
| D | 2.4 m | step + thrust, medium (about walking pace) | 4 |
| E | 1.8 m, left or right lane | step + thrust, fast | 4 |
| F | 3.0 m | step + thrust, fast | 4 |

Between lunges: step back to the start tape, stand still 3 s (this gives the detector a clean baseline). Say "ready" before each lunge so the labeller expects it. Repeat any lunge where the thruster stumbled or stopped early and mark it invalid.

Geometry notes (computed from `calib/camera.json`, lens at 0.10 m): the vertical half field of view is 38 degrees, so a 1.7 m person is only fully in view beyond about 2.1 m; closer than that the head is cut off and the box area grows less than the real body. Sets A to F start at or beyond 1.8 m on purpose, and the closing speed the 0.40 threshold implies (whole box scaling, no crop) is about 1.2 m/s from 0.8 m, 1.9 m/s from 1.2 m and 2.8 m/s from 1.8 m. A normal walk is 1.2 to 1.4 m/s, so close walking toward the robot is the hardest negative: it is recorded below.

## 6. Negatives: 10 minutes of normal activity (plus 2 min hard negatives)
Continuous recording, thruster not holding the prop unless stated.
1. 3 min walking across the view and back at normal pace, at 1.8 to 3.0 m.
2. 2 min walking **toward** the robot at normal pace and stopping at the 1.2 m tape, repeated (the main false-trigger risk).
3. 2 min standing, arm waving, bending to pick something from the floor, sitting down and standing up.
4. 3 min two people walking and crossing paths, one passing behind the other.
5. Hard negatives (2 min): fast walking or a quick step toward the robot with no thrust, holding the prop still, handing the prop to another person.

## 7. After recording
- Labels: `tools/label_events.py` writes onset timestamps; refine against the phone video if the key press lags (human delay is about 0.2 to 0.3 s, so keep the raw press time and the refined time as two columns).
- Evidence and data: recordings stay in `data/D4/` (gitignored); counts, label file and the detector metrics go to `reports/<handle>/week-NN/`.
- Detector check (offline): recall on the 24 positives, false triggers per minute on the negatives, latency from frame time to command (acceptance row above).
- Evasion with the robot moving (separate session, wheels off first): `python -m tools.pursue_live --evade`, key `e` injects a STRIKE; then a few real padded lunges at low cap. Only with R1 held, e-stop armed, never `--no-estop`. Measure the reaction time with the 240 fps phone.

## 8. Open items (to confirm Thursday)
- Thruster speeds are defined by feel (fast, medium); if time allows, time one lunge on the phone video and record the closing speed in the evidence.
- 24 positives assume about 30 min; the negatives take about 12 min. Plan D3 (re-ID, three people) for the second half of the 08:00 to 12:00 slot.
- Consent: every person recorded must agree (privacy rules, section 4.2); recordings are not shared outside the team.
