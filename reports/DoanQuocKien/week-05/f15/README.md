# F15 from the real runs (2026-11-02)

`F15_dead_reckoning.png`, made by `python -m tools.plot_f15_dead_reckoning`. Replaces the simulated F15 of PR #93 (`tools/plot_f15_localization.py`), whose curves came from invented drift and correction factors, not from any run.

- **A, B:** the two 3 m runs of 2026-10-24 (`reports/DoanQuocKien/week-03/t2_dead_reckoning/`): tape end pose against the estimator's end pose (replay, speed scale 1.0). Run 1 open loop: 186 cm without, 158 cm with markers (the boards left the view). Run 2 closed loop: 98 cm without, 14.5 cm with markers (the limit is 15 cm; 15.5-17.3 cm at the other speed scales; one run, depends on the hand-surveyed board position). Two runs, not the 5 of the plan.
- **C:** the 2026-10-30 deployment runs, tape offset from the sweet spot (`tape_offsets_1030.json`, copied from the classroom README): 26 and 27 cm when board 2 was followed to the end, 39, 80 and 114 cm when it was lost and the last 0.8-1.0 m ran on dead reckoning, 82 cm for dead reckoning only. Different protocol from A and B (stop position, not a 3 m straight run).
- Only end points exist (per-frame poses were not saved), so no trajectory is drawn between them.
