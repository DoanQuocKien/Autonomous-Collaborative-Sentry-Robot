# E-stop heartbeat 1.0 s: robot dry run (2026-11-14)

Checks that `HEARTBEAT_MAX_AGE_S = 1.0` in `jetson/robot_udp.py` (PR #119, was 2.0 s) never stops a normal held R1.

Setup: battery 12.22 V before, 12.20 V after. The branch's `robot_udp.py` ran in the `jetbot_jupyter` container as a separate copy with `--dry-run` on ports 5701/5702 (the motor service on 5556 got no packets; no motor was driven). The laptop sent v=0.5, w=0 at 30 Hz for 90 s (`dryrun_1114.py`). `hb_age_1114.py` read `ESTOP_ALIVE` every 10 ms in the container. The host `estop.py` (`sentry-estop` service) was unchanged; `estop.py` and `common/` on the robot matched the branch.

| Check | Result |
|---|---|
| Heartbeat age, 8489 samples over 89 s | max 0.548 s, p99 0.501 s, p50 0.254 s; 0 samples over 0.6 s; 0 read errors |
| Margin to the 1.0 s limit | 0.45 s |
| Armed + R1 held (16:01:16 to the end of the sender, 16:01:43) | e-stop released once, no ENGAGED in between; motors +0.15 +0.15 |
| Speed cap default | 0.5 x 0.3 = 0.15: the new default cap 0.3 applied (the old default 0.5 would give 0.25) |
| Sender stopped | motors 0.00 at 16:01:44.005 (0.3 s watchdog) |
| Packets | 2577 received, 0 malformed, 0 stale |

## Run 2: R1 release (45 s, same setup plus a second gamepad reader `js_log_1114.py` on the host)

| Event (button log on the host, estop.log, dry-run log) | Time |
|---|---|
| Start (button 11) down / up | 08:06:34 / 08:06:39; ARMED 08:06:35.527 |
| R1 (button 7) down | 08:06:42; GO 08:06:42.692; dry run released 16:06:42.701, motors +0.15 +0.15 |
| R1 up after about 11 s | 08:06:53; estop.py STOPPED 08:06:53.486 (its own motor cut 5 ms) |
| Dry run | ENGAGED 16:06:53.503 (17 ms after the estop.py stop), motors 0.00 at 16:06:53.521 (35 ms) |
| Heartbeat, 4240 samples | max 0.542 s, p99 0.501 s, 0 over 0.6 s |

Between 08:03:40 and 08:03:56 (an aborted attempt, no button log yet) the pad armed three times without a GO: something other than R1 cancelled each arm (any other button, Start included, hard-stops). Run 2 with the button log shows a clean Start -> R1 sequence, so no pad fault is suspected.

Not covered: the dongle-unplug test with R1 held is still open. Clocks: `estop.log` (host) is 8 h behind the container log (time zone). Robot test files removed afterwards. The `sentry-control` service still runs the old `robot_udp.py` until #119 is merged and deployed.

Files: `run_output.txt` (laptop output with both robot logs), `hb_age_1114.log` (per-second maximum), `dryrun_1114.py`, `hb_age_1114.py`.
