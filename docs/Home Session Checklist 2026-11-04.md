# Home session, Wed 2026-11-04 (not the classroom)

Rule: **the robot is on an unknown floor and room.** Everything measured here is labelled with the room and floor (matte or glossy, tile or carpet) and is NOT classroom evidence. The classroom list is `docs/Classroom Tasks Week 6.md`. Graded items first, optional ones last; do the maths afterwards, not during the session.

Words: **Pass** = the stated criterion met as measured. **Record** = typed into the run's summary or the session README at the time. A logged pose is not a result: ask what the tape says.

## 0. Before leaving the desk (laptop, 30 min)
1. `git pull` main (the controllers, hold detector and tracker are in); `python tools/check_env.py`; `pytest -q` (expect about 600 passed).
2. Charge the robot to full. `python -m tools.jetbot_status <ip>`: start graded runs only at >= 11.4 V; stop below 10.5 V.
3. Network: robot, ESP32 and laptop on the same Wi-Fi. The robot only knows the profile `DoanQuocKien` (hotspot); `--ip auto` finds the ESP32 (`find_esp32`). If home Wi-Fi is not the hotspot, use the phone hotspot and check `ping`, `tools.check_net`, one video frame.
4. Floor clear (2 x 4 m free), tape measure, 150 mm ArUco boards, a place to stand with the gamepad. E-stop: hold Start 1.5 s to arm, hold R1 to move. Never `--no-estop`. Motor tests only with the area clear.
5. Say the floor and room in the first line of the session README (`reports/DoanQuocKien/week-05/home_1104/README.md`).

## 1. Required at home (in this order)
| # | task | how | pass / record |
|---|---|---|---|
| 1 | Camera pitch for this floor | `python -m tools.self_pose --page-bottom-h 0.0` (page standing on the floor 1-2 m ahead) | >= 15 frames, spread < 0.4 deg. Record the pitch. Lens height stays 0.100 m. Re-run after any handling. |
| 2 | Full-battery speed and turn (clean calibration) | `python -m tools.motion_check --label home_1 --anchors <csv of today's boards> --spin-s 0.2 --repeats 6 --drive-s 0.6 --rest 1.5 --quad`, then `--v 0.55 --drive-s 1.5 --repeats 2` and `--v 0.75` | Record battery start/end per file. Target >= 10 left and >= 10 right pulses with a board in view before and after. A refused fit is a result: write why. Do not copy these numbers into the classroom model (floor-specific). |
| 3 | Pursuit PD step responses (tune the gains) | A person (or a board on a cart) 2 m ahead steps to 1.2 m or moves sideways; run the pursuit controller (`sentry/nav/controllers.py`) logging distance and bbox-centre error against time | Targets: steady distance 1.2 +/- 0.2 m; bbox centre within +/- 10 % of frame width for 80 % of the time. Keep the logs (numbers only). The commands must stay legal (>= 0.4 per wheel after mixing). |
| 4 | D3 recording (plan D3: JetBot following one or two people) | `tools/record.py` while pursuing: walking, stopping, occlusions, crossing paths; team members only, consent given | Frames stay local (`data/`, never committed). HNHL needs reviewed body boxes for the re-ID gallery: record at least 5 identities if possible (3 members + volunteers with consent), or say the limit. |
| 5 | Second D5 batch, only if the home floor is MATTE | `tools/record.py` floor-level set (legs and feet, wires straight and curled, shoes, sandals, backpacks, bags, furniture, empty floor 20 %), 0.3-1.5 m, 50+ per class; set one whole session aside for HNHL's held-out test | Label the floor and room. Skip if the floor is glossy again (same condition as D5). |
| 6 | Link-unplugged safety (plan row 'Edge safety') | With the robot driving slowly, R1 held: turn Wi-Fi off or close the app. Then release R1 once | Motors stop <= 350 ms after the packet stream ends or R1 is released (watchdog 305-315 ms measured). Record 5 stops. |
| 7 | End of session | `python -m tools.jetbot_status <ip>`; shut down cleanly (`sudo shutdown -h now`); charge | Record the final voltage. Update the return checklist in `docs/JetBot Notes.md` if anything was attached or installed. |

## 2. Optional at home (only if 1-7 are done)
- Phase 2 rehearsal with the ESP32 at any door: face -> re-ID -> queue on live frames (KR and HNHL present); not the demo shot.
- F21 refresh: `jetson/edge_bench.py` with a person in view, a 15-minute battery run with the voltage log (a charger is available at home).
- Reverse speed (the retract): three retracts in front of a board, speed from the range slope.
- Video shots that do not need the classroom: 2 (boot, arm, R1 stop), 3 (live stream with FPS/latency), 7 (pursuit, hold). Phone on a tripod; consenting people only; battery before every take.
- MPU6050 diagnosis (robot on, nothing else running): `i2cdetect -y -r 1` expects 0x68; report what appears. No wiring changes without noting them in the return checklist.

## 3. Laptop-only work (no robot; any time before 11-09)
The tool changes of `reports/DoanQuocKien/week-04/classroom_1030/analysis/next_session_1109.md` part A. A1 (board lost: stop and search, never dead reckoning) is DONE and merged; the rest is open:
- A2 stop margin: arrive when range <= stop - v x 0.20 s.
- A3 grading answers as flags or a JSON (`--answers`), offsets in named axes, "furniture within 1 m: measured distance".
- A4 log every handshake answer (t, in_view, inliers) and every frame's `seq`/`t_cap`; count MarkerFix calls and non-None results.
- A5 remove the invalid `servo_motion` turn ratios from the summary.
- A6 `motion_check`: turns from board bearings, drives from range; `--replay-only` must not overwrite the raw summary.
- A7 fix the hand-made provisional motion file (right scale 1.0, scale about 1.05) or build the model from `tools/floor_model.py`.
- A8 operator prompt "hold R1 until 2 beeps, at least 10 s; STANDBY: release R1".
- A9 battery gate 11.4 V for graded runs.
- Also: MarkerFix median with a time limit (clear it when the robot moves); replace the `assert legal(...)` in the controllers by "return stop and log" (leftover of PR #93); one F15 script instead of two; DQK's report sections (deployment, calibration, 5.x) from the Week 1-4 evidence.

## 4. Not at home (see the classroom document)
Deployment T2 runs and Part C (the door, boards and sweet spot are the classroom's), entrance and handshake results, the obstacle detector on the glossy floor, the demo shot of Phase 1 at the door, the video latency CDF on the hotspot network.
