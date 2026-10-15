# Classroom session Thu 2026-10-15, 08:00-12:00: plan and commands

Run everything from the repo root with the `sentry` interpreter. Robot battery above 12 V at the start (charge at 11.8 V or below). The robot's `calib/motion.json` was measured on a smooth floor at v = 1.0 only; the rugged floor on 2026-10-14/15 gave about 0.8 of the speeds and a strong left veer, so today's job is to find out how much of that was the floor (`reports/DoanQuocKien/week-02/rugged_floor/README.md`).

## Bring
Marker board (ArUco `DICT_4X4_50` id 0, black square 0.150 m, page standing on the floor so the square's lower edge is 0.132 m up) on a stand, tape measure, masking tape (2 crosses, strips), a protractor, the obstacles for `assets/d1/obstacles_template.csv`, gamepad, charger.

## Rules for every drive
- **Clear 1 m on both sides of the path.** (2026-10-15: an open-loop run veered 1 m sideways into a bean bag.)
- E-stop armed (hold Start 1.5 s); any other button disarms it. **Hold R1 fully down from the beeps until the two short beeps**; the robot only moves while R1 is held. A hand stays ready to release it.
- Never touch the robot between a run's three beeps and its two short beeps.
- `python -m tools.jetbot_status <ip>` between groups; stop below 10.5 V.

## Timeline
| Time | What |
| :-- | :-- |
| 08:00 | Setup: `python -m tools.preflight --marker-m 0.15 --bottom-h 0.132 --camera-h 0.100` (fix every FAIL), board upright at the far end (1.4-2.6 m from the robot's start), mount locked (tape + pencil mark) |
| 08:15 | Pose: 3 strips at 0.5 / 1.0 / 1.5 m from the plumb spot under the lens: `python tools/measure_camera_pose.py --marks 0.5 1.0 1.5 --h-tape 0.100 --tag classroom_1015`; then the marker check `python -m tools.estimate_camera_tilt --marker-m 0.15 --bottom-h 0.132 --id 0` (camera roll: PR #38) |
| 08:30 | Speed (marker as the ruler, no tape): `python -m tools.speed_trial 0.7 4 --label classroom` first (the same as the rugged floor), then 0.5, 0.6, 0.85 and `1.0 3` (3 s); two runs each. Prints net displacement / wheel seconds = average speed, the marker bearing at start and at rest, the wheel seconds and the battery. A run with under 0.5 wheel seconds is unusable: repeat |
| 08:55 | **Duration test (separates start-up lag from steady speed):** `python -m tools.speed_trial 0.7 2 --label dur2` and `0.7 6 --label dur6`, three runs each (6 s needs 1.4 m of path; start the board 2.4 m away). If the distance grows in proportion to the wheel seconds the speed is lower; if a constant amount is missing from every run it is a start-up lag. On the rugged floor the 4 s averages were 0.8x the glossy line but the steady speed from the marker fits was 0.9-1.08x: probably a lag of 0.5-1 s, not yet shown |
| 09:10 | Turns (tape + protractor): tape strip along the robot's centreline before the run, `python -m tools.motion_trial trial turn 0 1.0 0.5`, read the turn angle (left +), `python -m tools.motion_trial record reports/DoanQuocKien/week-02/classroom_turn_w10.csv 0 0 <turn_deg>`. Five runs; then `trial turn 0 0.5 1.5` into `classroom_turn_w05.csv`. Aim for under one full turn |
| 09:35 | Heading test (floor vs wheels): the same `python -m tools.speed_trial 0.6 4 --label head_centre` from the centre line, then `--label head_left` and `--label head_right` from 0.4 m to each side, all pointing at the board; two runs each. Compare the marker bearing at rest (left in every case = wheels or start-up, changes with the spot = floor) |
| 09:50 | Break; battery (charge if 11.8 V or below) |
| 10:00 | Obstacle sets: `docs/D1 Classroom Checklist.md` section 2 (setups 2-4, one matte-floor setup, 20 obstacles, forward distance to the nearest cm, floor type in the notes) |
| 11:30 | Strip check again, `python -m tools.preflight`, back up `data/D1*` (faces: never in git or chat), return checklist in `docs/JetBot Notes.md` |
| 11:50 | Buffer |

## Straight tape runs (only if the marker is out of view)
`python -m tools.motion_trial trial straight 0.7 0 4`, string between the start and far crosses, `python -m tools.motion_trial record <csv> <forward_m> <lateral_m> 0` (lateral: left +).

## After the session
Fit and profile (`calibrate_motion fit --csv ...` with the affine speed model), the per-floor numbers into `reports/DoanQuocKien/week-02.md` and the hours; copy `data/speed_runs/` next to the log.

## Demo-room check (before the presentation, about 20 minutes; added 2026-10-15)
The demo room has a different floor and texture, so one room's data does not show that the method transfers. The same steps there are the generalisation evidence (a pure test, no tuning):
1. `python -m tools.preflight --marker-m 0.15 --bottom-h 0.132` (battery 11.8 V or more; the live tilt must agree with the stored pose within 1.5 deg, else three strips).
2. Marker pages up (rigid vertical surface, ids 0-5, 0.05-0.25 m high); start check: `python -m tools.speed_trial 0.7 4 --label demo_room` once and one turn `python -m tools.turn_trial 0.5 0.4 --label demo_room`; compare with `sentry/nav/wheel_model.py` (speed within 15 %, turn rate within 15 %) and note the heading at rest.
3. Three empty-floor clips and one obstacle set (chairs, tape truth, one session pose) with `python -m tools.record_clip`; run the obstacle pipeline untouched and report distance error, `reflection_unresolved` count, false alarms on the empty clips.
4. Report the numbers as they are (glossy or matte, which floor), next to the tile results of 2026-10-15.
