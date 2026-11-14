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

## Runs 3-4: gamepad dongle pulled while R1 held (REAL motor service, wheels off the ground)

`unplug_1114.py` sent v=0.5 (0.15 per wheel at the service's cap 0.3) to port 5556; the running `sentry-control` service (old `robot_udp.py`, 2.0 s heartbeat; the unplug path is `estop.py`'s) drove the motors. Run 3 (40 s): the dongle was not pulled (no USB disconnect in `dmesg`), so it shows nothing about the unplug; the wheels stopped when the sender ended and R1 release cut in 7 ms.

Run 4 (60 s):

| Event | Time |
|---|---|
| ARMED / GO (Start, then R1) | 08:12:04.145 / 08:12:07.934; motors +0.15 +0.15 at 16:12:07.984 |
| Dongle pulled with R1 held | the button logger saw R1 up (the input layer releases held keys on disconnect) then ENODEV |
| `estop.py`: gamepad gone | 08:12:13.416 |
| `estop.py`: STOPPED (gamepad lost), its own motor cut | 08:12:13.464, cut took 6 ms (48 ms after detection) |
| `robot_udp`: ENGAGED, motors 0 | 16:12:13.475 / 16:12:13.513 (97 ms after detection) |
| Dongle plugged back | found / gone / found (re-enumeration, as at boot); stayed stopped until armed again (ARMED 08:12:24.9 and 08:12:31.4, GO 08:12:37.9) |

Result: pulling the dongle with R1 held stops the motors (pass). The time from the physical pull to the kernel removing the device is not measured.

## Run 5: gamepad switched off while R1 held, dongle plugged in (REAL motor service, wheels off the ground)

Same script, 60 s. The operator (DQK) switched the pad off twice with R1 held and switched it on again holding R1 (operator's account; the logs cannot tell a switch-off from a release).

| Event | Time |
|---|---|
| ARMED / GO | 08:14:32.723 / 08:14:38.404; motors +0.15 +0.15 |
| Pad switched off (1) | dongle reported R1 up 08:14:48; `estop.py` STOPPED (R1 released) 08:14:48.076, cut 6 ms; `robot_udp` motors 0 at 16:14:48.103 |
| Pad on, R1 held | GO 08:14:56.769 without re-arming (R1 release is a soft stop by design) |
| Pad switched off (2) | STOPPED 08:15:15.477, cut 6 ms; motors 0 at 16:15:15.526 |
| End | GO 08:15:20.199; sender ended (motors 0 at 16:15:29.399); R1 released 08:15:33.381; latch set afterwards |

Result: this pad's dongle reports every button released when the pad switches off, so a dead pad with R1 held stops the motors like a released R1 (pass for switch-off). Switching the pad back on with R1 held resumes without re-arming. Not tested: batteries pulled and the pad walking out of range (both expected to look like the switch-off on this dongle, not shown). Battery after the session: 11.98 V. Clocks: `estop.log` (host) is 8 h behind the container log (time zone). Robot test files removed afterwards. The `sentry-control` service still runs the old `robot_udp.py` until #119 is merged and deployed.

Files: `run_output.txt` (laptop output with both robot logs), `hb_age_1114.log` (per-second maximum), `dryrun_1114.py`, `hb_age_1114.py`.
