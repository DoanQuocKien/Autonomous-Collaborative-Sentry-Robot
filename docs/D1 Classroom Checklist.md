# D1 classroom session (Mon 2026-10-12): checklist

Lessons from the cafe session (2026-10-11): `reports/DoanQuocKien/week-01.md`, `data/D1/README_cafe_glass.txt`. Run everything from the repo root with the `sentry` interpreter.

## Bring
- Robot charged to about 12.4 V (>= 11.1 V OK, < 10.5 V stop), gamepad, tape measure (3 m+), masking tape, phone (reference photo), laptop + charger.
- The 150 mm ArUco prints (`assets/print/aruco_4x4_50_ids0-5_150mm.pdf`, 100 % scale, matte), mounted flat (foam board or a book) so they do not curl. Measure one and set `aruco_marker_m` in `config.toml`.
- ESP32 board + power bank (the OV2640 camera if it arrived; the board has no camera otherwise).
- A drive or cloud folder for the backup of `data/D1/` (about 1.3 GB per session, contains faces: never in git or chat groups).

## Set up (15 min)
1. Hotspot on (2.4 GHz), phone battery saver OFF, phone close to the work area. Laptop on that hotspot.
2. `python -m tools.jetbot_status` (battery). Start `estop.py` (arm key: Start held 1.5 s) and `camera_pub.py`, either by hand or with the systemd units (PR #12, untested: install and test them first, 5 min).
3. `python -m tools.find_jetbot` finds the robot; `config.toml` has `jetbot_ip = "auto"`.

## 1. Doorway set (about 20 min, per door)
1. Phone photo of the door (front-on, about 2 m, whole door and frame, no people): `data/D1/<door>_iref.jpg`.
2. Terminal A: `python -m tools.record D1 --no-esp32` (or without the flag when an ESP32 stream is available). Terminal B: `python -m tools.d1_label --door <door> --iref <door>_iref.jpg`.
3. Per position: place the robot, step away (the fisheye sees sideways), type `<distance_m> <angle_deg> <y|n> [notes]` + Enter, wait 5 s, **empty Enter** (ends the row), then move the robot.
4. Positives at 1, 2, 3, 4 m and angles 0, +-30 (+-45 if there is room), **both sides**. Distances by tape (+-5 cm), angles estimated (+-10 deg). Negatives: random views with the door out of sight (beyond +-90 deg of the optical axis), `0 0 n ...`. Note "person in view" when someone is in the frame.
5. `python -m tools.d1_manifest --door <door>`; check the counts. Row notes containing `exclude` are dropped, `moving` keeps all frames.

## 2. Obstacle distances (about 25 min)
20 obstacles at tape-measured distances 0.3-2.0 m **to the nearest cm** (this metric needs it: median error <= 10 %), in the room that is mapped. One CSV row each (`assets/d1/obstacles_template.csv`), robot still, a photo of each setup if possible.

## 3. Room sweeps (about 10 min)
Slow drive around the room with the e-stop armed (`tools.send_cmd --v 1.0`, hold R1), `tools.record D1_sweep`.

## 4. Motion + markers dataset (new, about 20 min): for KR's localization
1. Stick 2-3 ArUco markers on the wall at robot-camera height (about 10-20 cm), tape-measure their positions from a room origin: `assets/d1/marker_positions_template.csv`.
2. Mark start lines on the floor. Paths: straight 3 m, a square (about 1 m sides), a 90 deg turn in place; a few repeats of each, markers in view part of the time.
3. `python -m tools.record D1_motion --no-esp32`; for each run command with `send_cmd --v 1.0 --seconds <t>` (hold R1), then measure the end pose with the tape (`assets/d1/motion_markers_template.csv`). The same runs give DQK's motion calibration (5 x straight 1 m, 5 x 90 deg turn, Week 2) on the classroom floor.

## Wrap up
- `tools.jetbot_status` again; charge the robot. Remove nothing from the robot yet (the return checklist is in `docs/JetBot Notes.md`).
- Backup `data/D1*`, then share only the labelled frames of each manifest with KR and HNHL, privately.
- Update `reports/DoanQuocKien/week-02.md` (what was recorded, what failed).
