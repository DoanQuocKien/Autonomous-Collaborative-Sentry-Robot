# Tasks that need the classroom, to finish in Week 6 (Nov 9-15)

Sessions: **Mon Nov 9** (G2 day; the Week 5 session) and **Mon Nov 16** (pick-up; figures frozen). Everything here depends on the classroom's door, floor, boards or network. Home work is in `docs/Home Session Checklist 2026-11-04.md`. Rule of the day: graded runs first with the answers captured at run time; measurements for the maths second; the maths at home. Detailed run protocol and commands: `reports/DoanQuocKien/week-04/classroom_1030/analysis/next_session_1109.md` (part B).

## Before the session (home, no robot)
Part A of the home checklist (A2-A9 tool changes; A1 is done), the robot charged to >= 11.4 V, `self_pose` re-run on arrival, the 10-30 e-stop log read (`ssh jetbot@<ip> tail -n 300 /home/jetbot/sentry/estop.log`: it explains the three early motion_check stops).

## A. Graded (do first)
| # | task | pass | status now |
|---|---|---|---|
| 1 | **T2 deployment sequence, 5 runs counted** (plan 4.3: stop 1.5-3.0 m from the door, clear line of sight, wall or furniture within 1 m measured, handshake verified, STANDBY, 0 collisions) | 5 of 5 | 4 of 5 counted on 10-30 by DQK's decision (furniture within 1.5 m, not 1 m); the 5th and a rerun with the board-loss fix are open |
| 2 | **Part C: Phase 1 chain with the declared room** (`deploy_live --door`: scan, find the entrance, choose the sweet spot, deploy) | the same run criteria | never run on the robot |
| 3 | **T2 pursuit PD and standoff hold, first trials** (plan rows 'Pursuit PD', 'Standoff hold') with the gains tuned at home | distance 1.2 +/- 0.2 m; bbox centre within +/- 10 % for 80 % of the time; hold 2.0-3.0 s after the target stops, re-centred within 1.5 s, no orbiting | no robot trial yet (simulation only) |
| 4 | **ESP32 handshake at the classroom door** with the live rule (5 s window, 6 answers, 70 %), including a deliberate "aimed at the glazed partition" negative | verified within 3-4 s when aimed at the door; not verified when aimed at the partition | 7/10 accepts and 9/10 rejects on 10-30, accepted by DQK; the live rule not tested on the door |
| 5 | **Phase 2 live at the door** (ESP32 -> face -> re-ID -> queue) with the three members | whitelisted enter, the one not enrolled is queued; numbers as measured | not done on live frames |

## B. Obstacle layer and edge (G2, Mon Nov 9)
| # | task | note |
|---|---|---|
| 6 | Obstacle detector retest on the glossy floor with chairs and the big table at 0.8-2.4 m, with the pitch from today's `self_pose` (`tools.furniture_check --tape d`) | 10-30: chair 1.2 m detected 12/12 without a distance, 2.4 m 0/12; pass for the stop: a distance in >= 10 of 12 frames within +/- 0.15 m up to 1.5 m |
| 7 | T2 exploration with obstacle repulsion, 5 x 3 min, 0 collisions (plan 'Obstacle repulsion') | needs a detector that gives distances on this floor; D5 is from this floor |
| 8 | **G2 / Stage A (obstacle layer on the robot) is not built.** The plan's fallback is "stay on the laptop path; no further edge work before the mid-term". Decide on Nov 9 whether to drop Stage A and the 'Edge obstacle layer' row; the 'Edge safety' row (item 6 of the home list) is independent | decision, written into the plan |

## C. Calibration on the classroom floor (after the graded runs)
| # | task | note |
|---|---|---|
| 9 | Turn per 0.2 s pulse, left and right, n >= 10 each, boards at 1.5 m ahead and to the side | 10-30: 0.438 rad per pulse (sd 0.030, n = 12, mostly right pulses); the left rate rests on 2 pulses |
| 10 | Speed at v = 0.55 and 0.75 with the battery recorded at each start and end; repeat at the end of the session | 10-30: 0.224 m/s at 11.6-11.7 V, 0.216 at 11.4 V |
| 11 | Reverse speed at v = -0.45 (the retract) | unknown; explains the 0.26-0.27 m offsets only if about 0.3 m |
| 12 | Video lag with `t_cap` logging (A4) | bounded < 0.16 s on 10-30 |

## D. Report evidence that needs the room (figures frozen Mon Nov 16)
- **F7** video latency CDF and FPS on the hotspot network: `tools.log_latency` CSV with clock sync (a CDF cannot be built from quantiles; the 60 s run had p95 53 ms against the target 50 ms).
- **F17** pursuit: distance to target and bbox-centre error against time, hold events (from task 3 logs).
- **F20/F21** refresh with a person in view if the home bench is not enough.
- **Demo video shots** needing the room: 5 (entrance found, sweet spot, prompt, camera placed, verified, standby) and the Phase 2 and pursuit shots in the classroom; pick-up on Nov 16. Rules: battery check before every take, the R1 operator stated, consenting people only, replay or `sim_robot` shots captioned as such.

## E. Team items that need the classroom or the robot
- **HNHL:** a reviewed D3 body-box gallery and the held-out split (needs D3 from home and the classroom pursuit runs); re-ID rank-1 and ID switches on D3 (>= 5 identities, <= 1 switch/min); FP16 vs FP32 on the RTX 4050 for the report; screen recordings of the perception overlays during the runs.
- **KR:** PURSUE/HOLD wired to the hold detector and the controller commands, Phase 1-3 transitions replayed from logged events, then driven live in A.3; the door pictures and the ESP32 view for the video; the 3-consecutive handshake rule concern (the live rule is the windowed one).
- **All:** agree on Nov 9 which tasks slip to Nov 16 and write anything not working into the report as "in progress with its plan", not rushed.

## Order on the day (about 3 h)
0 battery, link, e-stop log; 1 `self_pose`; A.1 (5 T2 runs, graded, answers via `--answers`); A.2 Part C; A.4; A.3 and A.5 if teammates are present; B.6; C.9-12; D shots last. Charge between runs when below 11.4 V.
