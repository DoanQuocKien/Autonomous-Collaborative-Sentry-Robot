# Link-cut safety trials, home, 2026-11-08 (DQK) - laptop path only

`python -m tools.link_cut_test --label home_1 --trials 5` (robot at DQK's home, wooden floor, battery 11.84 V at the start). The robot spins in place (v = 0, w = 0.45); after 2 s the laptop stops sending UDP packets WITHOUT a stop packet (the app 'closed'); the robot's own 0.3 s watchdog must stop it. R1 held and the e-stop armed for every trial. The stop is read from the video (consecutive-frame difference, threshold between the still noise 0.9 and the spin level 12-16), so each number is an UPPER BOUND on the motor stop latency: it includes the video delay (bounded < 0.16 s on 2026-10-30, not re-measured today) and the frame period (about 0.05 s).

| trial | stop seen after the last packet |
|---|---|
| 1 | 0.524 s |
| 2 | 0.516 s |
| 3 | 0.503 s |
| 4 | 0.521 s |
| 5 | 0.481 s |

Plan limit: motors stop <= 350 ms after link loss. **Not demonstrated**: the upper bounds are 0.48-0.52 s. They do not prove a violation (the video delay is inside them), but the 0.3 s watchdog plus the deceleration leaves little room under 0.35 s. A direct measurement needs the stop time on the robot (a log of the wheel command going to zero) or a clock-synchronised capture time. Not done: the R1-release stop (separate trial). This is laptop-path evidence, not the 'Edge safety' pass (no on-robot layer exists). Numbers only; no video saved.
