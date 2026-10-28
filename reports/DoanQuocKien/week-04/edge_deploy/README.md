# Partial G1 run, live ESP32 stream (DQK, 2026-10-26): NOT a result

`edge_bench.py --mode stageC --door-thread --door-url http://10.195.93.9:81/stream --seconds 900` was started on the robot and **killed after about 10 of 15 minutes** (urgent interruption). The bench writes its JSON only at the end, so there is no FPS or latency result. G1's live-ESP32 half stays open.

What was kept: `partial_run_tegra.log` (tegrastats, 1 Hz, 611 lines) and `partial_run_batt.log` (unix time and the raw INA219 word once a minute; volts = byte-swapped word >> 3 x 4 mV): 12.19 V at the start, 11.92 V minimum, 11.97 V at the last sample (12 samples).

A 25 s smoke test before it (same command, no face in the ESP32 view): 19.68 FPS, 6 frames skipped, 1.0 people per frame, 0 faces per door run (the ESP32 pointed at a door), ESP32 frames reached the Jetson at 3.75 fps.
