# Week 03 - DoanQuocKien (2026-10-19 to 2026-10-25)

*Illness Mon-Fri 2026-10-19..23 (no work); everything below was done on Sat 2026-10-24. Updated that evening.*

## Done
- **D5 first batch** (the Week 3 item, added to my list on 2026-10-24 because the first batch to HNHL was late): 397 frames on a glossy floor, one room: footwear 49, backpack 49, bag 50, black wire 50, white wire 49, legs 50, furniture 50 (chair 20, table 15, plant 15), empty floor 50. Recorder `tools/record_d5.py`, face masking `tools/mask_faces.py` (heads painted over, borderline frames dropped, checked by eye), labelling rules (label every visible leg, plant, table, chair, bag, shoe, even far in the background) in `reports/DoanQuocKien/week-03/d5_first_batch/README.md`. Committed to the private repo (team decision, PR #59; the plan's privacy line says so). Not yet: matte floor, second room, second lighting, 150 per class.
- **Edge latency and load with a person in view** (G1, first half; PR #60, `week-03/edge_deploy/`): 15 min on battery, Stage B mix plus the door pipeline in its own thread (on a still image): p95 capture-to-result **78.1 ms** (target <= 100), RAM max **2.13 GB** (< 3.0), GPU **40 C** max (< 80), battery 11.89 -> **11.48 V** under load (>= 11.1), 1.36 people per frame, **19.97 FPS** (target 20: 0.03 short, 23 of 17,974 frames skipped by the newest-only reader; not strictly met).
- **Marker correction and T2 dead reckoning over 3 m** (PR #56, `week-03/t2_dead_reckoning/`): the heading sign bug in `update_with_markers` is fixed with a regression test (found in a real run on 2026-10-18). `tools.dr_path --follow ID` steers by a marker's bearing while it drives. Open loop (no steering): the robot curved 60 deg left, boards left the view, **158 cm** with correction. Closed loop: **14.5 cm** with correction (target <= 15 cm; 15.5-17.3 cm at other speed scales; one run, depends on the surveyed board position: 4-7 cm if board A is at 3.8 m instead of 3.6 m), **98 cm** without (target <= 40 cm, not met: no IMU, the estimator integrates the steering commands).
- **Papers** 12-14 in the Mid-Term Report Plan (YOLO-World, SegFormer, Borenstein and Feng), read.
- **D2 without outside volunteers:** leave-one-out among the three members (PR #57), with the limit stated.
- Reviewed KR's PR #55: 410 tests pass, 1 fails (event timestamps ignored once the clock is non-zero); KR informed.
- Week 2 leftovers closed: PR #54 merged, the Week 2 log (PR #58).
- **HNHL's PR #63** reviewed (442 tests pass, the metrics match their JSON), fixed with PR #66 (the unusable `d5.yaml` removed; **138 background leg boxes in 137 frames** with `tools/label_background_legs.py`) and merged. First-pass YOLO-World labels (`tools/autolabel_d5.py`: chair, plant and shoe found well; legs, wires and tables not found) were replaced by HNHL's hand-corrected ones (PR #65).
- **Plan:** the weekly session is now the Monday of the following week, in the classroom (PR #64; Week 3's is Mon Oct 26); six PRs merged (#56-#61) and the plan checked after the merge; paper numbering fixed (PR #67).

## Not done (Week 3, DQK)
- Edge bench with **live ESP32 frames** (G1, second half): KR's robot tile receiver (PR #55) is merged (2026-10-25); the bench still needs a small `edge_bench.py` change, the ESP32 and a charged robot (classroom, Mon Oct 26).
- USB speaker playback on the Jetson (needs #55 and the speaker).
- Deployment behaviour and the T2 deployment sequence (5 runs): needs a door and the classroom.
- D2 ESP32 entries (needs a door and the ESP32).
- T2 motion repeatability with the estimator in the loop: the closed-loop run above is one run; 2-4 more are needed after charging (battery was 11.3 V).
- MPU6050: not decided (a gyro would remove the no-correction error above).

## Notes
- The robot's open-loop straight drive curves 50-60 deg over about 2 m on this floor at 11.3-11.5 V (also on 2026-10-18 at 12 V): closed-loop steering is needed for any straight path; the steering integral settled at -0.0143 (about 10 deg/m).
- Marker range gate 1.5 m (`max_marker_distance_m`): far boards are rejected; a longer gate made the open-loop estimate worse (heading from oblique, distant markers).

## Hours
- From the chat timestamps (same rule as week 2: a gap of up to 30 minutes between messages counts as work), counted on Sun 2026-10-25 at 09:16 (UTC+7): Mon 2026-10-19 2.2 h (the Sunday-session spill-over, until about 12:50), Sat 2026-10-24 **2.6 h**, Sun 2026-10-25 **0.4 h** so far; **5.2 h** for the week. Chat time only; the 15-minute bench run and the robot waits are inside it, the long gaps while the PRs were reviewed and merged are not; offline work (reading the papers, moving boards and furniture) is not counted.
