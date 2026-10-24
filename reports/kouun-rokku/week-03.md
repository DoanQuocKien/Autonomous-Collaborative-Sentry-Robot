# Week 03 – kouun-rokku (2026-10-19 to 2026-10-25)

*Focus: ESP32 HTTP MJPEG receiver with auto-reconnect (`sentry/net/mjpeg_rx.py`), ESP32 placement handshake check (`ESP32Handshake` in `sentry/perception/entrance.py`), offline WAV audio prompt generation (`sentry/app/audio.py`, `assets/audio/`), Phase 1–3 state machine skeleton (`sentry/app/state_machine.py`), Python 3.6 robot tile receiver (`jetson/espcam.py`), and Mid-Term Report paper references.*

## Done

- **ESP32 HTTP MJPEG Stream Receiver with Auto-Reconnect (`sentry/net/mjpeg_rx.py`, `tests/test_mjpeg_rx.py`):**
  - Implemented `MJPEGReceiver` for the OV2640 HTTP MJPEG path (`http://<esp32-ip>:81/stream`) and `tools/esp_mjpeg_relay.py`.
  - Exposes both the single-consumer `read(timeout=None) -> VideoFrame | None` contract (`sentry/net/frame.py`, matching `ZMQReceiver`) and the shared read-only `latest() -> (frame_bgr, frame_id, age_s)` contract (`sentry/espcam.py` `TileReceiver`).
  - Uses SOI/EOI byte scanning (`split_jpegs` with `MAX_JPEG = 2 MiB` runaway-buffer protection), decodes only the newest complete JPEG per read chunk to prevent queue lag, and automatically reconnects after `reconnect_s` on HTTP/socket errors or stream EOF while tracking `reconnects`, `received`, `frames`, `skipped`, and `invalid`.
- **ESP32 Placement Handshake Check (`sentry/perception/entrance.py`, `tools/enroll_entrance.py`, `tests/test_entrance.py`):**
  - Added `EntranceDetector.enroll_esp32(frames, rois=None)` and `ESP32Handshake` to verify stationary ESP32-CAM placement facing the door (`Project Specification.md` §4.3).
  - Enrols a dedicated second `EntranceDetector(camera=None)` with reference frames from the ESP32 lens itself and calibrates its own XFeat/DINOv2 thresholds on ESP32 non-door views (since the robot-eye fisheye reference does not transfer across lenses).
  - Debounces frame-level `EntranceResult` detections through `EntranceFilter` into `ESP32_VERIFIED` / `ESP32_LOST` events for the state machine and supports polling both `TileReceiver` (`.latest()`) and `MJPEGReceiver` (`.latest()` / `.read()`) while skipping duplicate or stale frames (`age_s > max_frame_age_s`).
  - Updated `tools/enroll_entrance.py` to accept `--camera none` when enrolling ESP32 doorway references.
- **Offline Audio Prompts & Playback Dispatch (`sentry/app/audio.py`, `sentry/net/udp_tx.py`, `assets/audio/*.wav`, `tests/test_audio.py`):**
  - Implemented `sentry/app/audio.py` with offline TTS rendering (`pyttsx3` / `espeak-ng` / `espeak` with a deterministic pure-Python formant + earcon speech synthesizer fallback) and WAV validation (`verify_wav`).
  - Generated and committed 7 compact 16-bit mono 8 kHz PCM WAV clips in `assets/audio/` (`place_camera.wav`, `guard_ready.wav`, `camera_verified.wav`, `standby.wav`, `intruder_detected.wav`, `hold_position.wav`, `alarm.wav`, 19–35 KB each) compatible with `jetson/robot_udp.py` `play_clip` (`aplay -q`).
  - Added `UDPSender.play(clip)` in `sentry/net/udp_tx.py` to send validated `{"seq": int, "play": "<clip>"}` packets on UDP port 5556 sharing the monotonic sequence counter with motor commands.
- **Phase 1–3 State Machine Skeleton (`sentry/app/state_machine.py`, `tests/test_state_machine.py`):**
  - Implemented `StateMachine`, `StateMachineConfig`, `Phase`, `State`, `Event`, `Command`, and `TransitionResult` as pure CPU logic (events in, commands out; zero socket or model dependencies).
  - Covers all Phase 1–3 states and transitions:
    - **Phase 1 (`SETUP`):** `EXPLORE` $\leftrightarrow$ `APPROACH_VANTAGE` (`ENTRANCE_FOUND` / `ENTRANCE_LOST`) $\rightarrow$ `WAIT_CAMERA` (`VANTAGE_REACHED`, plays `place_camera`) $\rightarrow$ `RETRACT` (`ESP32_VERIFIED`, plays `camera_verified`, reverses) $\rightarrow$ `STANDBY` (`STANDBY_REACHED` or `retract_duration_s` timeout, emits `save_map`).
    - **Phase 2 (`MONITOR`):** `STANDBY` $\rightarrow$ `PURSUE` on `INTRUDER_QUEUED` (plays `intruder_detected`), or `STANDBY` $\rightarrow$ `WAIT_CAMERA` on `ESP32_LOST`. Additional `INTRUDER_QUEUED` events arriving during Phase 3 are appended to the internal FIFO queue without interrupting active interception.
    - **Phase 3 (`INTERCEPT`):** `PURSUE` $\leftrightarrow$ `HOLD` (`TARGET_STATIONARY` / `TARGET_MOVING`), immediate `STRIKE` preemption from `PURSUE` or `HOLD` into `EVADE` ($v = -1.0, \omega = \pm 0.8$ away from the nearer obstacle side for $0.4\text{ s}$ with post-evade cooldown), and `TARGET_EXITED` handoff into `SEARCH` (`PLAN` $\rightarrow$ `FOLLOW` $\leftrightarrow$ `SCAN` $\rightarrow$ `TARGET_FOUND` $\rightarrow$ `PURSUE`, or `SEARCH_EXHAUSTED` / `search_timeout_s` $\rightarrow$ drop target $\rightarrow$ next queued target or `STANDBY`).
  - Configurable timeouts for every state (`explore_timeout_s`, `approach_timeout_s`, `handshake_timeout_s`, `retract_duration_s`, `evade_duration_s`, `search_timeout_s`).
  - Invalid or out-of-phase events are ignored without mutating state and logged via `sentry.state_machine` and `sm.ignored_events`.
- **Week 3 Extra – Python 3.6 Robot ESP32 Tile Receiver (`jetson/espcam.py`, `tests/test_jetson_espcam.py`):**
  - Created `jetson/espcam.py` as a standalone Python 3.6-compatible port of `sentry/espcam.py` with no `sentry.*` imports (self-contained `local_ipv4()` and `broadcast_targets()`), verified with `ast.parse(..., feature_version=(3, 6))`.
  - Added recorded tile-stream helpers (`encode_frame_packets`, `dump_tile_stream`, `load_tile_stream`, `replay_tile_stream`) and verified frame-by-frame pixel parity against `sentry.espcam.TileReceiver` on multi-frame synthetic recorded tile streams (T0, CPU only).
- **Mid-Term Report Paper List (`docs/Mid-Term Report Plan.md` §2):**
  - Verified full bibliographic details for KR's existing 3 papers (`#1` Rublee et al. ICCV 2011 ORB, `#3` Garrido-Jurado et al. Pattern Recognition 2014 ArUco, `#9` Galceran & Carreras RAS 2013 coverage path planning) and added 4 additional verified references from KR's area (`#12` Fischler & Bolles CACM 1981 RANSAC, `#13` Collins & Bartoli IJCV 2014 IPPE planar PnP, `#14` Siegwart et al. MIT Press 2011 differential-drive kinematics/odometry, `#15` Hart et al. IEEE TSSC 1968 A* search).

## Tests run

| Tier | Command | Result | Evidence |
| :-- | :-- | :-- | :-- |
| T0 | `python3 -m sentry.app.audio` | 7/7 WAV prompts generated & verified (16-bit mono 8 kHz PCM) | `assets/audio/*.wav` |
| T0 | `pytest tests/test_mjpeg_rx.py tests/test_entrance.py tests/test_audio.py tests/test_state_machine.py tests/test_jetson_espcam.py tests/test_udp_tx.py` | All new W3 unit & contract checks pass (Python 3.6 AST check on `common/` and `jetson/`, WAV verification, Phase 1–3 scripted transitions, timeouts, invalid events, recorded tile stream parity) | [pytest.log](week-03/pytest.log) |

## Acceptance criteria status (Implementation Plan §4.3)

- **State machine transitions & invalid-event handling (T0):** Scripted event sequences cover every Phase 1–3 transition, state timeout, multi-intruder queue handoff, `STRIKE` preemption + cooldown, and invalid-event rejection/logging $\rightarrow$ **Pass (T0)**.
- **ESP32 handshake logic (T0 / T2 prep):** `ESP32Handshake` with separate ESP32-enrolled `EntranceDetector` achieves 10/10 accepts on door-facing frames and 10/10 rejects on turned-away frames in T0 fake/synthetic evaluation; live 10/10 accept & 10/10 reject T2 check scheduled for the Sunday integration session $\rightarrow$ **Ready for Sunday T2**.
- **On-robot ESP32 tile receiver port (Extra, Gate G1 T0):** `jetson/espcam.py` passes Python 3.6 AST validation with zero `sentry.*` imports and matches `sentry.espcam.TileReceiver` byte-for-byte on recorded multi-frame tile streams $\rightarrow$ **Pass (T0)**.

## Blockers / risks

- **Sunday Session T2 (2026-10-25):** Live T2 ESP32 handshake accept/reject protocol (10/10 accepts when facing door, 10/10 rejects when turned away) and recording dataset **D2** at the door with DQK and HNHL.
- **D5 Floor-Level Obstacle Labeling:** Ready to split manual bounding-box/polygon correction work on D5 once DQK records the first batch and HNHL runs open-vocabulary auto-labeling.

## Next week (Week 4)

- Implement `sentry/app/target_queue.py` (FIFO of intruder records: ID, face embedding, OSNet appearance vector, departure sector, snapshot path, timestamps).
- Implement departure sector logging (bounding-box horizontal drift over 2 s $\rightarrow$ Left / Center / Right).
- Connect Phase 2 replay pipeline on D2 end to end (`ESP32 stream -> face verification -> OSNet re-ID -> target_queue -> state_machine`).
- Add T0 unit tests for `target_queue` and sector classification, and T1 sector accuracy on D2.
