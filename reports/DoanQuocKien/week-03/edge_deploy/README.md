# Edge latency and load with a person in view (DQK, 2026-10-24)

`jetson/edge_bench.py --mode stageC --door-thread --seconds 900` on the robot (school JetBot, Jetson Nano, MAXN), live camera stream (20 fps), wheels still, on battery. A person sat 2.6 m in front of the camera (two more people at a desk behind): pose on every frame, detector every 3rd, OSNet x0.25 every 15th, door pipeline (SCRFD, align, MobileFaceNet, 2 faces) in its own thread at 5 Hz on a **still image** (not live ESP32 frames).

| Quantity | Result | Target (plan 4.3, 'Edge latency and load') |
| :-- | :-- | :-- |
| Frames / FPS | 17,974 in 900 s = **19.97 FPS** (23 skipped by newest-only) | >= 20 FPS: 0.03 below, camera is 20 fps; not strictly met |
| Capture-to-result | mean 51.0, p50 49.4, **p95 78.1 ms** | p95 <= 100 ms: met |
| People per frame (pose) | 1.36 on average | person in view: yes |
| Door pipeline | 4,500 runs = 5.0 Hz, 75.5 ms mean (p95 97.6), 2.0 faces per run | - |
| RAM (tegrastats) | 2.10 GB mean, **2.13 GB max** of 3.96 | < 3.0 GB: met |
| GPU temperature | 38.4 C mean, **40 C max** | < 80 C: met |
| Board power (5 V rail) | 5.73 W mean, 7.04 W max | - |
| Battery (INA219, under load) | 11.89 V at the start, **11.48 V minimum**, 11.56 V at the end (12.05 V at rest before the run) | stays >= 11.1 V: met |

**What this does not show:** the door pipeline ran on a still image, so the 'live ESP32 frames' half of gate G1 is open (it needs the tile receiver for the robot in PR #55, and `edge_bench.py` reading live frames); the parity row needs HNHL's parity set.

Files: `person_bench.out` (the bench JSON), `person_tegra.log` (tegrastats at 1 Hz), `person_batt.log` (unix time and the raw INA219 bus-voltage word once a minute; volts = byte-swapped word >> 3 x 4 mV).
