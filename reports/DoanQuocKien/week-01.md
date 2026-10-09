# Week 01 – DoanQuocKien (2026-10-05 to 2026-10-11)

*Written Saturday 2026-10-10. Items marked **TODO** are not done yet; the Sunday session results still need adding.*

## Done
- Robot bring-up and link: JetBot reachable from the laptop over the Windows hotspot (2.4 GHz, because the ESP32 needs it); Wi-Fi power save on the Realtek RTL8822CE fixed permanently (`/etc/modprobe.d/8822ce-sentry.conf`), antenna fitted. The remaining checks are in `robot_checks.md` and `robot_remote_checks.txt` – PR #1 (merged), PR #2 (open)
- `jetson/camera_pub.py` (GStreamer camera -> JPEG q60 -> ZeroMQ), `jetson/robot_udp.py` (v/w mixing, 300 ms watchdog, clock echo), shared `common/protocol.py` and `common/mixing.py` – PR #1, PR #2
- Safety: gamepad dead-man switch and e-stop (`jetson/estop.py`), verified on the robot with wheels off the ground, including with `robot_udp.py` frozen – PR #2
- Tools: `tools/jetbot_status.py` (battery, Wi-Fi, containers), `tools/fetch_models.py` (re-ID and face weights, safe loading), `tools/gpu_pipeline_check.py`, `tools/make_markers.py`, `tools/esp_serial.py`, `tools/esp_tile_rx.py`, `tools/fetch_esp_jpeg.py` – PR #2
- Environment: conda env `sentry` (Python 3.12, torch 2.9.1+cu128, onnxruntime-gpu 1.23.2), install paths for GPU laptop / CPU laptop / Jetson in `docs/Setup.md` – PR #1, PR #2
- Hardware decisions and shopping lists (`docs/Hardware.md`), printable calibration targets (`assets/print/`), plan updates (map-based coverage search, hold-and-recenter instead of orbiting, ArUco localization, USB speaker + offline TTS) – PR #2
- **ESP32-CAM (unplanned):** both camera modules turned out to be GC2145 (no hardware JPEG), so the planned HTTP MJPEG stream is impossible. Built a 640x480 stream in software (raw Bayer capture trick, sensor timing registers, changed-tile UDP stream), laptop receiver `sentry/espcam.py` with white balance, 5 tests, PlatformIO project for KR's CameraWebServer sketch, `docs/ESP32-CAM.md`, plan risks 12-13 – PR #2

## Tests run
| Tier | Command | Result | Evidence |
| :-- | :-- | :-- | :-- |
| T0 | `pytest -m "not gpu and not hil"` | 64 passed | week-01/pytest.log |
| T2 | Video uplink, real camera, 60 s, laptop hotspot 2.4 GHz | 20.0 fps, 0 of 1200 frames missing, one-way latency p50 13 / p95 53 ms | week-01/link_test_2026-10-04.txt (section N) |
| T2 | Control link: ping and UDP 1.5 / 6 Mbit/s | 0 % loss | week-01/link_test_2026-10-04.txt |
| T2 | Watchdog, 5 cycles (`robot_udp --dry-run` on the robot) | stop 305-315 ms after the last packet | week-01/link_test_2026-10-04.txt (section O) |
| T2 (wheels off) | Dead-man / e-stop, including a frozen `robot_udp.py` | pass; motor cut works independently of the program | week-01/estop_test_2026-10-06.txt, estop_deadman_2026-10-06.txt |
| T1 (gpu) | `tools/gpu_pipeline_check.py` | 3-model pipeline 37 FPS, about 300 MB VRAM; InsightFace about 7 ms, OSNet 11-13 ms | week-01/gpu_baseline_2026-10-06.txt |
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
- **Merge coordination:** HNHL's branch has no PR yet and will conflict in `.gitignore`, the plan and `requirements-base.txt`; KR's PR #3 has no tests for record / replay / sim_robot.
- The weak hotspot password (8 characters) should be changed; update the robot's saved profile first while it is connected.

## Next week
- Sunday: merge PRs, freeze the §3 interfaces (ESP32 row), record **D1** (room sweeps, doorway views, 20 tape-measured obstacles, 30+ checkerboard photos, ESP32 door view). Needs the printed checkerboard on a flat board and a tape measure.
- Week 2 (DQK): `tools/calibrate_fisheye.py` (target < 1.0 px) and `tools/calibrate_motion.py`; T1 reprojection error, T2 motion repeatability (5 runs each of straight 1 m and 90° turn).
- Decide the camera: keep the GC2145 tile stream or order an OV2640; update the plan accordingly.
- First floor driving with the e-stop armed, in daylight at low speed.
- Re-measure video latency (target p95 < 50 ms), optionally install `estop.py` as a systemd service.

## Hours
- About 18 h of logged working sessions (estimated from chat timestamps, gaps over 20 min removed; 16-23 h depending on the cutoff):
  - Oct 3-4 (before the week): about 8 h – plan, repo, environment, first robot link
  - Oct 5-6: about 3 h – robot checks, e-stop, link tests
  - Oct 9-10: about 6.5 h – ESP32-CAM debugging and the 640x480 stream, docs, PR work
- Not counted: hands-on robot handling, charging, shopping, travel.
