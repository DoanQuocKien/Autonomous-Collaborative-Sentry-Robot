# Link-cut safety trials, home, 2026-11-08 (DQK) - laptop path only

`python -m tools.link_cut_test --label home_1 --trials 5` (robot at DQK's home, wooden floor, battery 11.84 V at the start). The robot spins in place (v = 0, w = 0.45); after 2 s the laptop stops sending UDP packets WITHOUT a stop packet (the app 'closed'); the robot's own 0.3 s watchdog must stop it. The e-stop was armed; R1 was held at each trial's start. **Correction (HNHL review, 2026-11-09):** `trials.csv` records `r1_still_held = 0` for trial 4 (the poll after the trial found R1 not held), so R1 was NOT shown to be held for every trial and the release time is unknown; trial 4's cause (watchdog or R1 release) is unconfirmed and the five trials are not equally conditioned. The stop is read from the video (consecutive-frame difference, threshold between the still noise 0.9 and the spin level 12-16), so each number is an UPPER BOUND on the motor stop latency: it includes the video delay (bounded < 0.16 s on 2026-10-30, not re-measured today) and the frame period (about 0.05 s).

| trial | stop seen after the last packet |
|---|---|
| 1 | 0.524 s |
| 2 | 0.516 s |
| 3 | 0.503 s |
| 4 | 0.521 s |
| 5 | 0.481 s |

Plan limit: motors stop <= 350 ms after link loss. **Not demonstrated**: the upper bounds are 0.48-0.52 s. They do not prove a violation (the video delay is inside them), but the 0.3 s watchdog plus the deceleration leaves little room under 0.35 s. A direct measurement needs the stop time on the robot (a log of the wheel command going to zero) or a clock-synchronised capture time. Not done: the R1-release stop (separate trial). This is laptop-path evidence, not the 'Edge safety' pass (no on-robot layer exists). Numbers only; no video saved.

**Status of these numbers (2026-11-11):** video proxies of the stop (picture stillness), not a measured mechanical or motor stop; the < 0.16 s video-latency bound dates from 2026-10-30 and was not re-measured; the plan limit of 0.35 s stays UNVERIFIED. The old tool had four weaknesses (no guaranteed sender cleanup, the cutoff was the last attempted send even if it failed, no check that the picture moved before the stop, wheels on the floor against the wheels-off rule); `tools/link_cut_test.py` now has guaranteed cleanup, a confirmed-send cutoff taken atomically, per-trial validity (R1 held at the cut included), an explicit `--wheels-on-ground-ack` exception, and fault-injection tests. These five old rows are kept as they were recorded and must be repeated with the new tool before any citation beyond 'observed 0.48-0.52 s on the old protocol'.
