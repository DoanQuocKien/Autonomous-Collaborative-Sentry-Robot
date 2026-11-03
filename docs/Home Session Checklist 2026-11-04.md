# Home session, Wed 2026-11-04 (not the classroom)

Rule: **the robot is on an unknown floor and room.** Everything measured here is labelled with the room and floor (matte or glossy, tile or carpet) and is NOT classroom evidence. The classroom list is `docs/Classroom Tasks Week 6.md`. Graded items first, optional ones last; do the maths afterwards, not during the session.

Words: **Pass** = the stated criterion met as measured. **Record** = typed into the run's summary or the session README at the time. A logged pose is not a result: ask what the tape says.

## 0. Before leaving the desk (laptop, 30 min)
1. Update a clean checkout with `git switch main` then `git pull --ff-only` (keep any local work on its own branch first; controllers, hold detector and tracker are merged). Use the project interpreter: `python tools/check_env.py`; `python -m pytest -m "not gpu and not hil" -q`. Run GPU checks separately with prepared local weights; missing assets/HIL skips are not hardware passes.
2. Charge the robot to full. `python -m tools.jetbot_status <ip>`: start graded runs only at >= 11.4 V; stop below 10.5 V.
3. Network: robot, ESP32 and laptop on the same Wi-Fi. The robot only knows the profile `DoanQuocKien` (hotspot). Robot tools use `--ip auto` for the JetBot; `deploy_live --esp-ip auto` or `handshake_test --ip auto` finds the ESP32 (`find_esp32`). Check `ping`, one real JetBot video frame and one ESP32 frame (one stream client at a time). `python -m tools.check_net` is a synthetic localhost smoke test, not a test of the robot/Wi-Fi path.
4. Floor clear (2 x 4 m free), tape measure, 150 mm ArUco boards, a place to stand with the gamepad. E-stop: hold Start 1.5 s to arm, hold R1 to move. Never `--no-estop`. Motor tests only with the area clear.
5. Say the floor and room in the first line of the session README (`reports/DoanQuocKien/week-05/home_1104/README.md`).

## 1. Required at home (in this order)
| # | task | how | pass / record |
|---|---|---|---|
| 1 | Camera pitch for this floor | `python -m tools.self_pose --page-bottom-h 0.0` (page standing on the floor 1-2 m ahead) | >= 15 frames, spread < 0.4 deg. Record the pitch. Lens height stays 0.100 m. Re-run after any handling. |
| 2 | Full-battery speed and turn (clean calibration) | `python -m tools.motion_check --label home_turns_1 --anchors <csv of today's boards> --spin-s 0.2 --repeats 6 --drive-s 0.6 --rest 1.5 --quad --min-battery 11.4`. For speed, repeat the full command with fresh labels `home_speed055_1` / `home_speed075_1`, `--v 0.55` / `--v 0.75`, `--drive-s 1.5 --repeats 2` and the same anchors/battery gate | Record battery start/end per file. Target >= 10 left and >= 10 right pulses with a board in view before and after. A refused fit is a result: write why. Keep the withdrawn provisional file unusable. Do not copy home gains into the classroom model (floor-specific), and never reuse a label to overwrite a raw run. |
| 3 | Pursuit PD step responses (tune the gains) | A person (or a board on a cart) 2 m ahead steps to 1.2 m or moves sideways; run the pursuit controller (`sentry/nav/controllers.py`) logging distance and bbox-centre error against time | Targets: steady distance 1.2 +/- 0.2 m; bbox centre within +/- 10 % of frame width for 80 % of the time. Keep the logs (numbers only). The commands must stay legal (>= 0.4 per wheel after mixing). |
| 4 | D3 recording (plan D3: JetBot following one or two people) | `python -m tools.record` while following a supervised target: walking, stopping, occlusions, crossing paths; consenting team members or volunteers only | Frames stay local (`data/`, never committed). Tracking: >=60 s two-person scenes, reviewed per-frame body boxes/IDs/visibility, capture timestamps and empty frames; ID switches <=1/min. Re-ID: separate reviewed gallery/query and held-out split, >=5 identities for rank-1 >=85%; fewer identities are a pilot, not a pass. |
| 5 | Second D5 batch, priority MATTE floor | `python -m tools.record` floor-level set (legs and feet, wires straight and curled, shoes, sandals, backpacks, bags, furniture, empty floor 20 %), 0.3-1.5 m, 50+ per class; reserve one whole session before model selection | Label floor, room, session and distances. Matte supplies the missing floor control. A different glossy room/session can still provide independent-session evidence, but does not supply a matte-floor comparison. The first 50/class is a batch target, not the full plan's >=150/class or T1 acceptance. |
| 6 | Link-unplugged safety | On the laptop-controlled path, robot driving slowly with R1 held: turn Wi-Fi off or close the app; separately release R1. On-robot-layer trials require that layer to exist first | Motors stop <=350 ms after packet stream ends or R1 is released. Record 5 measured stops and the control path; the historical 305-315 ms is robot_udp dry-run log timing, not measured mechanical braking. Until Stage A exists, this is laptop-path safety evidence, not a complete 'Edge safety' pass. |
| 7 | End of session | `python -m tools.jetbot_status <ip>`; shut down cleanly (`sudo shutdown -h now`); charge | Record the final voltage. Update the return checklist in `docs/JetBot Notes.md` if anything was attached or installed. |

## 2. Optional at home (only if 1-7 are done)
- Phase 2 rehearsal with the ESP32 at any door: face -> re-ID -> queue on live frames (KR and HNHL present); not the demo shot.
- F21 refresh: `jetson/edge_bench.py` with a person in view, a 15-minute battery run with the voltage log (a charger is available at home).
- Reverse speed (the retract): three retracts in front of a board, speed from the range slope.
- Video shots that do not need the classroom: 2 (boot, arm, R1 stop), 3 (live stream with FPS/latency), 7 (pursuit, hold). Phone on a tripod; consenting people only; battery before every take.
- MPU6050 diagnosis (robot on, nothing else running): `i2cdetect -y -r 1` expects 0x68; report what appears. No wiring changes without noting them in the return checklist.

## 3. Laptop-only work (no robot; any time before 11-09)
Cross-check `reports/DoanQuocKien/week-04/classroom_1030/analysis/next_session_1109.md` part A against current main. A1 (board-loss stop/search) is merged. PR #90 also made replay write `analysis_summary.json` and added a 1 s MarkerFix median age guard; PR #93 already replaced controller `assert legal(...)` with safe stop/log and removed the duplicate F15 script. Remaining work:
- A2 DONE (2026-11-03, this branch): `deploy_live --servo-margin` (default 0.044 m) stops the motors that much BEFORE the stop range (the robot coasts 0.043 m; the earlier wording "range <= stop - v x 0.2 s" had the sign wrong).
- A3 DONE: `--answers FILE.json`, or the questions at the end when a terminal is attached (now with named axes x forward / y left and the furniture distance), or afterwards `python -m tools.tape_answers <run folder> --offset-x .. --offset-y ..`; with neither, the run prints a loud WARNING.
- A4 DONE: `handshake.csv`, `frames.csv` (seq, t_cap) in the run folder; `marker_fix_calls` and `marker_fix_results` in summary.json.
- A5 DONE: `servo_motion` (summary key, print, function, test) removed.
- A6 PARTLY DONE: `rest_pose` now takes the heading from the board BEARING (direction to the known anchor minus the bearing) instead of the board's noisy orientation; UNVALIDATED: replaying `class_2` gives the same ratios as before (spin_left 0.894 and 1.134, still 6 of 15 segments measurable, fit refused), so either the bearing path did not engage or it changes nothing; the unit test passes with synthetic data only. Find out at home before trusting it. Original text: `motion_check`: investigate turns from board bearings and drives from range. Replay preservation is already fixed; keep raw summary unchanged and save new analyses separately.
- A7 acquire a new marker-measured fit and an independent CHECK run for this floor. Keep `calib/motion_session_1030_provisional.json` withdrawn (`usable=false`); do not replace withdrawn gains with hand-picked numbers. Any `floor_model` candidate is exploratory until validated against new measurements.
- A8 DONE: the loop prints "PLACE THE ESP32 and keep HOLDING R1 until the 2 beeps (at least 10 s)" at WAIT_CAMERA and "STANDBY: release R1 now".
- A9 DONE: `deploy_live --min-battery` defaults to 11.4 V (graded runs).
- Also: verify the existing MarkerFix age guard clears motion-contaminated rests; DQK's report sections (deployment, calibration, 5.x) from the Week 1-4 evidence. Controller/F15 changes already merged are not new session work.

## 4. Not at home (see the classroom document)
Deployment T2 runs and Part C (the door, boards and sweet spot are the classroom's), entrance and handshake results, the obstacle detector on the glossy floor, the demo shot of Phase 1 at the door, the video latency CDF on the hotspot network.
