# Week 04 - DoanQuocKien (2026-10-26 to 2026-11-01)

*Started 2026-10-28 from the Monday session notes; hours not recorded yet. Updated through Wed 2026-10-28. The Mon 2026-10-26 session was solo (the teammates were busy), so everything that needs a second person is open.*

## Done
- **Speaker dropped (team decision, 2026-10-26):** audio prompts and the alert sound play on the laptop; CLAUDE.md, spec, plan, report plan, hardware, setup and JetBot notes updated (PR #70). Not done: `sentry/app/audio.py` (laptop playback) and removing the unused Jetson `play`/`aplay` path.
- **ESP32-CAM debugging (most of Mon):** the board on hand carries an **OV2640** (`SENSOR PID=0x0026`), not a GC2145. The GC2145 tile firmware on it gave 1.6 FPS and wrong colours; `esp32/sentry_cam` (HTTP MJPEG) is the right firmware. Camera alone (Wi-Fi off, new `esp32/experiments/ov2640_rate`): VGA 25.2 FPS, QVGA 50. Over Wi-Fi the 20 MHz camera clock interfered with the radio (1.1 FPS); at 10 MHz it streams about 10-11 FPS at VGA. Laptop InsightFace found a face in 65 of 65 frames (one person, one position; not a detection rate). Details in `docs/ESP32-CAM.md` (PRs #71, #72, #73).
- **Firmware defects found by reading the code and fixed:** a failed camera probe ended `setup()` before Wi-Fi started (board looked as if it could not join the hotspot; it now reboots until the camera is found), no Wi-Fi supervision in `loop()`, sensor power-cycle before init, three small chunks per frame plus Nagle (one header chunk and `TCP_NODELAY`), per-frame verbose logging. Not separated: which of these raised the frame rate. Not tested: the reboot-on-camera-fail path and the Wi-Fi watchdog (could not trigger them).
- **Periodic full refresh in the tile receiver** (PR #71, for GC2145 boards): grey holes at 1-2 FPS.
- **`edge_bench.py --door-live` / `--door-url`** (PRs #69, #73): the door pipeline on the live ESP32 stream (tile stream or OV2640 MJPEG, Jetson reader `jetson/mjpeg_latest.py`, one pytest against a fake stream).
- **G1 live-ESP32 bench: NOT done.** A 25 s smoke test held 19.68 FPS (no face in the ESP32 view). The 15-minute run was killed at about 10 minutes (urgent interruption): no result. Partial tegrastats and battery logs and a README are in `week-04/edge_deploy/` (battery 12.19 V start, 11.92 V min).

## What went wrong (for the record)
- About a day went into the ESP32. Some of my early explanations (hotspot, power source, sensor settings, lighting) were guesses that the data later contradicted; the real causes were the wrong firmware for the sensor and defects in the firmware code. Lesson: read the code and measure before attributing a fault to the environment.
- The hotspot dropped twice during the session; the robot and ESP32 vanished each time.

## Open / next
- G1: rerun the 900 s live-ESP32 bench with a person in view of both cameras (solo), then the parity row (HNHL's parity set).
- Two-person session this week: T2 deployment sequence (5 runs), KR's live handshake test, the teammates' D2 entries. My own 10 D2 entries can be recorded alone.
- Decide the ESP32 interface (tile stream vs OV2640 MJPEG, one client at a time): needs all three to approve.
- `sentry/app/audio.py`, deployment behaviour against the simulator, small-object targets and the IMU decision (solo).
