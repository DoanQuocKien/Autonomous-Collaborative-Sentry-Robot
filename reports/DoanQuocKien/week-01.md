# Week 01 – DoanQuocKien (2026-10-05 to 2026-10-11)

*Written Saturday 2026-10-10, updated that evening. Items marked **TODO** are not done yet; the Sunday session results still need adding.*

## Done
- Robot bring-up and link: JetBot reachable from the laptop over the Windows hotspot (2.4 GHz, because the ESP32 needs it); Wi-Fi power save on the Realtek RTL8822CE fixed permanently (`/etc/modprobe.d/8822ce-sentry.conf`), antenna fitted. The remaining checks are in `robot_checks.md` and `robot_remote_checks.txt` – PR #1 and PR #2 (both merged; PR #2 approved and merged by HNHL on 2026-10-10)
- `jetson/camera_pub.py` (GStreamer camera -> JPEG q60 -> ZeroMQ), `jetson/robot_udp.py` (v/w mixing, 300 ms watchdog, clock echo), shared `common/protocol.py` and `common/mixing.py` – PR #1, PR #2
- Safety: gamepad dead-man switch and e-stop (`jetson/estop.py`), verified on the robot with wheels off the ground, including with `robot_udp.py` frozen – PR #2
- Tools: `tools/jetbot_status.py` (battery, Wi-Fi, containers), `tools/fetch_models.py` (re-ID and face weights, safe loading), `tools/gpu_pipeline_check.py`, `tools/make_markers.py`, `tools/esp_serial.py`, `tools/esp_tile_rx.py`, `tools/fetch_esp_jpeg.py` – PR #2
- Environment: conda env `sentry` (Python 3.12, torch 2.9.1+cu128, onnxruntime-gpu 1.23.2), install paths for GPU laptop / CPU laptop / Jetson in `docs/Setup.md` – PR #1, PR #2
- Hardware decisions and shopping lists (`docs/Hardware.md`), printable calibration targets (`assets/print/`), plan updates (map-based coverage search, hold-and-recenter instead of orbiting, ArUco localization, USB speaker + offline TTS) – PR #2
- **MJPEG relay and fake ESP32 (2026-10-10):** `tools/esp_mjpeg_relay.py` serves the tile stream as `http://127.0.0.1:81/stream` so KR's `record.py` / `replay.py` work with the GC2145 boards (D1 recording needs it); `tools/esp_tile_sim.py` simulates the board; found and fixed a flaw where the full-refresh after `REFR` was discarded because the JPEG header had not arrived yet; the missing record-then-replay round-trip test for the ESP32 view added (`tests/test_record_replay_esp32.py`); change-detector improvements (thin edges, faster quiet refresh) – PR #2
- **D1 checkerboard set (2026-10-10):** 58 photos (all detected, every cell of a 4x4 image grid has 58+ corners) taken with the new guided tool `tools/capture_checkerboard.py`, which shows the least-covered area and saves only photos that reach it; `tools/find_jetbot.py` finds the JetBot after every hotspot restart (`jetbot_ip = "auto"`); `.env` (hotspot password) added to `.gitignore` – PR #6. Trial `cv2.fisheye` calibration on the 640x480 stream: RMS 1.39 px on all 58, 0.95 px after dropping 5 early outliers (`cb_010`-`cb_014`), `fx` about 310 px, centre (286, 239), stable across odd/even half-splits (the real `tools/calibrate_fisheye.py` is Week 2). Photos are in `data/D1/checkerboard/` (not in git)
- **Review:** approved HNHL's PR #5 (network telemetry, 121 tests pass on a clean checkout, merges cleanly with main); noted one interaction with `jetbot_ip = "auto"` to fix after both merge
- **ESP32-CAM (unplanned):** both camera modules turned out to be GC2145 (no hardware JPEG), so the planned HTTP MJPEG stream is impossible. Built a 640x480 stream in software (raw Bayer capture trick, sensor timing registers, changed-tile UDP stream), laptop receiver `sentry/espcam.py` with white balance, 5 tests, PlatformIO project for KR's CameraWebServer sketch, `docs/ESP32-CAM.md`, plan risks 12-13 – PR #2

## Tests run
| Tier | Command | Result | Evidence |
| :-- | :-- | :-- | :-- |
| T0 | `pytest -m "not gpu and not hil"` | 72 passed | week-01/pytest.log |
| T2 | Video uplink, real camera, 60 s, laptop hotspot 2.4 GHz | 20.0 fps, 0 of 1200 frames missing, one-way latency p50 13 / p95 53 ms | week-01/link_test_2026-10-04.txt (section N) |
| T2 | Control link: ping and UDP 1.5 / 6 Mbit/s | 0 % loss | week-01/link_test_2026-10-04.txt |
| T2 | Watchdog, 5 cycles (`robot_udp --dry-run` on the robot) | stop 305-315 ms after the last packet | week-01/link_test_2026-10-04.txt (section O) |
| T2 (wheels off) | Dead-man / e-stop, including a frozen `robot_udp.py` | pass; motor cut works independently of the program | week-01/estop_test_2026-10-06.txt, estop_deadman_2026-10-06.txt |
| T1 (gpu) | `tools/gpu_pipeline_check.py` | 3-model pipeline 37 FPS, about 300 MB VRAM; InsightFace about 7 ms, OSNet 11-13 ms | week-01/gpu_baseline_2026-10-06.txt |
| T1 (gpu) | `tools.gpu_baseline --check-face` (HNHL's tool) on the target RTX 4050 6 GB | pass: YOLOv8n 110.6 FPS, YOLOv8s 106.3 FPS (batch 1, FP32, 640), peak allocated 33 / 79 MiB; onnxruntime-gpu 1.23.2, torch CUDA OK | week-01/gpu/gpu_baseline_rtx4050.json, .log |
| T1 (trial) | Fisheye calibration on 58 checkerboard photos, 640x480 | RMS 1.39 px (0.95 px after dropping 5 outliers); target < 1.0 px in Week 2 | week-01/d1/ (this session; photos in data/D1/checkerboard/) |
| T2 | ESP32-CAM stream, 68 s walk-through test | 14.4 FPS average, large motion 13.8 FPS; full-load worst case 9-10 FPS | week-01/esp32_gc2145_jpeg_2026-10-09.txt (sections 18-21) |

## Acceptance criteria status (Implementation Plan §4.3)
- Video uplink: >= 20 FPS **pass** (20.0); capture-to-laptop p95 < 50 ms **fail, marginal** (53 ms, includes JPEG encode, clock-synced via echo; not yet re-measured glass-to-laptop) – TODO re-measure
- Control link: loss < 1 % **pass** (0 %); watchdog stop <= 350 ms **pass** (305-315 ms)
- GPU budget: pipeline >= 15 FPS **pass** (37), peak VRAM <= 5.5 GB **pass** (about 300 MB)
- ESP32-CAM VGA 15 FPS (§3 interface row): **partial**, 14.4 FPS average with a custom UDP stream and a fixed camera (the HTTP MJPEG interface cannot work with the GC2145 modules); needs the team's approval or an OV2640 module
- Not due this week: fisheye calibration, obstacle distance, entrance, localization, face/re-ID accuracy

## Blockers / risks
- **ESP32-CAM sensor (plan risk 12):** GC2145 has no JPEG; workaround works only for a fixed camera and needs the interface change approved by KR and HNHL (PR #2 comment). Fallback: buy an OV2640 module.
- **Second ESP32-CAM board (risk 13):** loses its Wi-Fi uplink whenever the camera runs; cause unknown (not power, memory, encoder, channel width, clock, protocol). The first board works. KR's board is untested.
- **Latency target missed by 3 ms (53 vs 50 ms)** on the JetBot video path; to re-measure with the final setup.
- **No floor driving yet:** the e-stop is verified wheels-off only; first floor test with the e-stop armed is still to do (battery check first, >= 11.1 V).
- **Campus Wi-Fi is bad** (10 KB/s on some days) and slows downloads; the laptop hotspot only works when the laptop's own Wi-Fi shares its channel or is off.
- **Unflashed firmware changes (2026-10-10):** the new change detector, faster quiet refresh and header-on-REFR compile and are tested in Python/simulation, but the board was unreachable; flash `esp32/tile_stream` and re-measure before D1 (TODO).
- **Merge coordination:** HNHL opened PR #5 and it merges cleanly with main; KR's PR #3 has no tests for record / replay / sim_robot (round-trip test added in PR #2). `record.py` on main still has the `CONFLATE` crash (`!_more`); PR #5 removes it. After PR #5 and #6 merge, `ZMQReceiver`, `synchronize`, `UDPSender` and `tools/log_latency.py` must call `find_jetbot.resolve()` because the config now says `auto`. No reviews or weekly log from KR yet.
- The weak hotspot password (8 characters) should be changed; update the robot's saved profile first while it is connected.

## Next week
- Sunday: merge PR #5 (HNHL, approved) and PR #6, freeze the §3 interfaces (ESP32 row: needs KR's answer), record the rest of **D1** (room sweeps, doorway views, 20 tape-measured obstacles, ESP32 door view; **the 58 checkerboard photos are done**). Needs a tape measure. The camera publisher on the robot does not survive a reboot (restart it, or add a systemd service).
- Week 2 (DQK): `tools/calibrate_fisheye.py` (target < 1.0 px) and `tools/calibrate_motion.py`; T1 reprojection error, T2 motion repeatability (5 runs each of straight 1 m and 90° turn).
- Decide the camera: keep the GC2145 tile stream or order an OV2640; update the plan accordingly.
- First floor driving with the e-stop armed, in daylight at low speed.
- Flash the updated `esp32/tile_stream`, run `tools/esp_mjpeg_relay.py` + `tools/record.py D1` against the real board before the D1 recording.
- Re-measure video latency (target p95 < 50 ms), optionally install `estop.py` as a systemd service.

## Hours
- About 18 h of logged working sessions (estimated from chat timestamps, gaps over 20 min removed; 16-23 h depending on the cutoff):
  - Oct 3-4 (before the week): about 8 h – plan, repo, environment, first robot link
  - Oct 5-6: about 3 h – robot checks, e-stop, link tests
  - Oct 9-10: about 6.5 h – ESP32-CAM debugging and the 640x480 stream, docs, PR work
- Not counted: hands-on robot handling, charging, shopping, travel.
