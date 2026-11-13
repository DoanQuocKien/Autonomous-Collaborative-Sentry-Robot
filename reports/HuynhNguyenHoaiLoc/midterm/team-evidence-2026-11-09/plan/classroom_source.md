# Tasks that need the classroom, to finish in Week 6 (Nov 9-15)

> **Session moved (2026-11-08, DQK): the classroom session of Mon Nov 9 is pushed to NEXT WEEK (date to be fixed).** Everything below that needs the room waits for it; the figure freeze (Mon Nov 16), the internal draft (Wed Nov 18) and the report due date (Mon Nov 23) did not move, so all graded classroom runs, F7 and F17 land in one session close to the freeze. Use this week for the home and laptop items listed under 'Before the session' and for the rehearsals.

> **Camera repaired (2026-11-05):** the robot's camera socket was resoldered and the video stream works again (about 18.6 fps). Re-run `tools.self_pose` before any run that counts (the mount may have moved). Details in the plan's Week 5 status and `docs/JetBot Notes.md`.

Sessions: **Mon Nov 9** (G2 day; the Week 5 session) and **Mon Nov 16** (pick-up; figures frozen). Everything here depends on the classroom's door, floor, boards or network. Home work is in `docs/Home Session Checklist 2026-11-04.md`. Rule of the day: graded runs first with the answers captured at run time; measurements for the maths second; the maths at home. Detailed run protocol and commands: `reports/DoanQuocKien/week-04/classroom_1030/analysis/next_session_1109.md` (part B).

## Before the session (home, no robot)
Remaining tool work in section 3 of the home checklist (check what is already merged), the robot charged to >=11.4 V, `self_pose` re-run on arrival, the 10-30 e-stop log read (`ssh jetbot@<ip> tail -n 300 /home/jetbot/sentry/estop.log`: it explains the three early motion_check stops). Home gains are not a classroom calibration; obtain/validate today's floor-specific model before any graded run that relies on it, with the R1 operator and a cleared area.