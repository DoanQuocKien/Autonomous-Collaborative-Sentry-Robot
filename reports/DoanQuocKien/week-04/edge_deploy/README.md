# G1 live ESP32 frames, edge bench (DQK)

## Full run, 2026-10-28 (cafe): `live_esp32_*`
`jetson/edge_bench.py --mode stageC --door-thread --door-url http://10.195.93.9:81/stream --seconds 900` on the robot, wheels still, on battery. One person in view of the robot's camera (about 2.6 m) and a second person at the ESP32 (OV2640, firmware of PR #72/#73, 10 MHz camera clock, JPEG quality 12), cafe, bystanders possible (1.93 people per frame on average).

| Quantity | Result | Target (plan 4.3) | |
| :-- | :-- | :-- | :-- |
| Frames / FPS | 17,999 in 900.1 s = **20.00 FPS** (2 skipped by newest-only) | >= 20 FPS | met |
| Capture-to-result | mean 46.6, p50 42.2, **p95 69.7 ms** | p95 <= 100 ms | met |
| RAM (tegrastats, 907 samples) | 2.10 GB mean, **2.11 GB max** of 3.87 | < 3.0 GB | met |
| GPU temperature | 32.2 C mean, **33.0 C max** | < 80 C | met |
| Battery (INA219) | 12.34 V start, **11.83 V min**, 11.92 V end (18 samples) | >= 11.1 V | met |
| Board power (5 V rail) | 5.50 W mean, 6.90 W max | - | - |
| Door pipeline | 4,499 runs = 5.0 Hz, mean 46.5 ms (p95 73.9; SCRFD 15.3, MobileFaceNet 20.1 per face), 1.13 faces per run | - | - |
| ESP32 frames delivered to the Jetson | 2,121 in 900 s = **2.36 fps** (0 reconnects) | - | weak: most door runs reused a frame |

What this does not show: the parity row (HNHL's parity set); faces per door run include whoever stood at the ESP32 (no identity check); the 2.36 fps came from the firmware's TCP window and a busy radio, since improved to about 9 fps (`docs/ESP32-CAM.md`, PR #77) but not re-benched. Files: `live_esp32_bench.json` (bench JSON), `live_esp32_bench.out`, `live_esp32_tegra.log` (1 Hz), `live_esp32_batt.log` (raw INA219 word per minute; volts = byte-swapped word >> 3 x 4 mV).

## First attempt, 2026-10-26 (partial, not a result)
`edge_bench.py --mode stageC --door-thread --door-url http://10.195.93.9:81/stream --seconds 900` was started on the robot and **killed after about 10 of 15 minutes** (urgent interruption). The bench writes its JSON only at the end, so there is no FPS or latency result. G1's live-ESP32 half stays open.

What was kept: `partial_run_tegra.log` (tegrastats, 1 Hz, 611 lines) and `partial_run_batt.log` (unix time and the raw INA219 word once a minute; volts = byte-swapped word >> 3 x 4 mV): 12.19 V at the start, 11.92 V minimum, 11.97 V at the last sample (12 samples).

A 25 s smoke test before it (same command, no face in the ESP32 view): 19.68 FPS, 6 frames skipped, 1.0 people per frame, 0 faces per door run (the ESP32 pointed at a door), ESP32 frames reached the Jetson at 3.75 fps.
