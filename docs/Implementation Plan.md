# Implementation Plan

Companion to `Project Specification.md` (the spec decides *what*; this file decides *who, how, and how we prove it works*).
Week 1 starts **Mon 2026-10-05**; the calendar runs 13 weeks, to Sun 2027-01-03 (restructured 2026-10-12, section 5).
- **Mid-Term Report due Mon 2026-11-23** (first day of Week 8): 10-15 pages, **includes the code** (tagged snapshot + appendix) and a demo video (optional). Plan, outline and countdown: `Mid-Term Report Plan.md`. Internal draft Wed 2026-11-18.
- **Final submission/defense window Mon 2026-12-28 to Fri 2027-01-02**; we target the first day, **Mon 2026-12-28**, so a late slip still lands inside the window. The final has three deliverables: a **report, a presentation and a live robot demo**, on a day the team chooses inside the window (all subject to change; confirmed by DQK 2026-10-12). The code is submitted as a **public repo link** (tag `final`).
- Dates given by DQK (team lead) on 2026-10-12. They replace the spec's 8-week roadmap and its 15-20 page Week 4 milestone (spec section 6); the spec stays the source of truth for scope.

## 1. Team & Roles

| Handle | CUDA | Hardware | Primary ownership |
| :-- | :-: | :-: | :-- |
| **DoanQuocKien** (DQK) | Yes | Holds the JetBot kit | Jetson side, motor control, calibration, controllers on the robot, hardware-in-the-loop (HIL) testing, integration host; on-robot inference (extra, proposed 2026-10-16) |
| **HuynhNguyenHoaiLoc** (HNHL) | Yes | – | Laptop perception: YOLOv8, ByteTrack, InsightFace, OSNet, YOLOv8-pose, GPU profiling |
| **kouun-rokku** (KR) | No | Holds the ESP32-CAM + MB base | CPU-side logic: record/replay tooling, entrance matching (XFeat / DINOv2; ORB baseline), localization (ArUco + dead reckoning), state machine, queue/handoff logic, simulation, audio assets, test infrastructure, report editing |

Principles behind the split:
- KR has no GPU, so KR owns everything that runs on CPU and the tooling that lets others work without the robot.
- Only DQK has the robot (and only KR has the ESP32 kit), so every task must be developable **offline on recorded data** first. HIL time on DQK's setup is for validation, not development.
- Each member carries roughly equal weekly load (about 3 work items per week).

## 2. Repository Layout (target)

```
sentry/                 # laptop package, Python 3.12 in sentry (see Setup.md)
  net/                  # zmq_rx.py, udp_tx.py, mjpeg_rx.py, clock_sync.py
  perception/           # obstacle.py, entrance.py (XFeat + DINOv2, written 2026-10-12), face.py, reid.py, tracker.py, pose.py, camera_pose.py (live camera tilt)
  nav/                  # localization.py, gridmap.py, vantage.py, coverage.py, controllers.py
  app/                  # state_machine.py, target_queue.py, audio.py (laptop alert/WAV playback), main.py
config.toml             # repo-root tunables (thresholds, gains, ports; [entrance] for the entrance detector); stdlib tomllib
third_party/xfeat/      # vendored XFeat (Apache-2.0, trimmed; LICENSE + NOTICE.md); weights from tools/fetch_models.py
common/                 # Python 3.6-compatible, stdlib only; used by BOTH laptop and Jetson
  protocol.py           # ports, packet encode/decode with validation, SeqFilter, video header, clock echo
  mixing.py             # (v, w) -> wheel values: rescale-not-clip, dead zone (zero below `min_pwm`), setting checks
tools/                  # DONE: check_env.py, send_cmd.py, make_markers.py, record.py, replay.py, sim_robot.py,
                        # calibrate_fisheye.py (calib/camera.json, RMS 0.83 px), calibrate_motion.py (no runs yet),
                        # plus network/ESP32/D1/GPU helpers
                        # TODO: enroll_whitelist.py, label_events.py
jetson/                 # Python 3.6, Ubuntu 18.04; own requirements.txt (see docs/Setup.md)
  camera_pub.py         # CSI -> JPEG q60 -> ZeroMQ PUB; `--source synthetic` works without the robot (tested on the robot 2026-10-06)
  robot_udp.py          # UDP (v, omega) -> motors, watchdog, e-stop interlock (motors tested; the `play`/`aplay` path is unused since the speaker was dropped 2026-10-26)
  estop.py              # gamepad dead-man + e-stop, robot host (tested wheels-off 2026-10-06, first floor drive 2026-10-11)
  systemd/              # boot units for estop / camera / control (written 2026-10-11, not yet tested on the robot)
assets/print/           # ArUco markers (ids 0-5, 10 cm and 15 cm sets; the 150 mm set is the one in use) and 9x6 checkerboard PDFs, from tools/make_markers.py
esp32/tile_stream/      # GC2145 boards: raw Bayer changed-tile UDP stream (the frozen interface, section 3)
esp32/sentry_cam/       # OV2640 boards only: HTTP MJPEG VGA sketch (tested 2026-10-26 on an OV2640 board: about 10-11 FPS over Wi-Fi, one stream client at a time; see docs/ESP32-CAM.md)
assets/audio/           # pre-generated WAV prompts (committed, small)
calib/                  # calibration outputs (camera.json, motion.json); committed
tests/                  # pytest; markers below
data/                   # recordings, face photos (GITIGNORED; shared via team Drive)
reports/<handle>/       # weekly reports + test evidence (section 6)
```

Keep it flat. A module gets split only when it passes about 400 lines.

## 3. Interfaces (frozen by end of Week 1)

Freezing these lets the three members work in parallel against the same contracts. Any change needs a PR that all three approve.

| Link | Transport | Format |
| :-- | :-- | :-- |
| JetBot -> laptop video | ZeroMQ PUB/SUB, port 5555; bounded SUB queue, drain complete messages and overwrite one latest-frame slot | multipart `[header_json, jpeg_bytes]`; header `{"seq": int, "t_cap": float (Jetson monotonic s), "w": int, "h": int}` |
| Laptop -> JetBot control | UDP, port 5556, non-blocking | JSON `{"seq": int, "v": float, "w": float}` with v, w normalized to [-1, 1]; or `{"seq": int, "play": "<clip_name>"}` |
| Clock sync | UDP echo, port 5557 | laptop sends `t0`, Jetson replies `{t0, t_jetson}`; offset by Cristian's algorithm (min-RTT of 20 samples) |
| ESP32-CAM -> laptop | **Decision 2026-10-28 (the team, reported by DQK at the session): the interface is the OV2640 HTTP MJPEG stream `http://<esp32-ip>:81/stream` (VGA, about 9 FPS measured over Wi-Fi, one client at a time); the UDP tile stream below stays as the fallback for GC2145 boards.** Original row: **UDP tiles, port 5600** (GC2145 module, no hardware JPEG): raw Bayer 640x480, changed 64x32 tiles only, laptop found by `HELO` broadcast; `sentry.espcam.TileReceiver.latest()` gives a BGR frame. **Frozen 2026-10-11 by DQK's decision: the UDP tile stream is the interface.** An OV2640 module was nevertheless ordered the same day (`docs/ESP32-CAM.md`; firmware ready in `esp32/sentry_cam`, not tested on a board); switching the interface to it needs a PR all three approve. HNHL approved PR #2, which carried this row; KR was asked in the comments on PR #2 and #6 and had not answered by 2026-10-11, so KR may still object (a change then needs a PR all three approve). With an OV2640 module the original HTTP MJPEG `http://<esp32-ip>:81/stream` (VGA, 15 FPS) is used instead | 640x480 at 14.4 FPS average (fixed camera); see `docs/ESP32-CAM.md` |
| Companion app <-> robot (**proposed 2026-10-16, not frozen**; needs a PR all three approve) | robot -> app: ZeroMQ PUB; app -> robot: ZeroMQ REQ/REP | messages `status` (1 Hz: phase, state, battery, e-stop, FPS, GPU ms, temperature, RAM, `where` = laptop or edge), `frame` (<= 5 Hz, boxes + JPEG), `event` (the state-machine events), `intruder_candidate`, `queue`, `map`; app -> robot `start`, `stop`, `confirm`. Field list: `docs/Edge Feasibility.md` section 5. Motion permission stays with the gamepad dead-man: the app can always stop, never override it |

Laptop-internal contract:
- JetBot video adapters use `read(timeout) -> VideoFrame | None`, single consumer, with `frame_bgr`, original `jpeg`, `seq`, source `t_cap`, laptop `t_rx` and `t_decode` (see `sentry/net/frame.py`). Latest-frame receivers deliberately skip old frames; record/replay preserves source timestamps. `tools.replay.ReplayStream.read()` implements this offline contract; legacy tuple iteration remains supported. The ESP32 tile interface uses `latest()` as documented separately above.
- Do not use `ZMQ_CONFLATE` on the multipart video link: [libzmq documents that it retains only one part](https://libzmq.readthedocs.io/en/latest/zmq_setsockopt.html#zmq-conflate-keep-only-last-message). The wire format stays unchanged; review this correction with the team before the W1 interface freeze.
- Every perception module is a class with a `__call__(frame_bgr, t) -> dataclass` method and no global state.
- Every module can be fed from `replay.py` exactly as from a live stream.
- **Entrance** (`sentry/perception/entrance.py`): `EntranceDetector(camera)(frame_bgr, t) -> EntranceResult(in_view, inliers, similarity, bearing_rad, quad)`, bearing positive = left (the sign of `w`); `EntranceFilter.update(result)` -> `None | ("ENTRANCE_FOUND", bearing_rad) | ("ENTRANCE_LOST", None)` is what the state machine consumes. One entrance door per room: enrolment is per room (`tools/enroll_entrance.py`, `EntranceDetector.save/load`).
- The state machine only consumes **events** (e.g. `ENTRANCE_FOUND`, `INTRUDER_QUEUED`, `TARGET_STATIONARY`, `STRIKE`, `TARGET_EXITED`, `TARGET_FOUND`, `SEARCH_EXHAUSTED`) and emits **commands**. It never touches sockets or models directly, so it is unit-testable on CPU.

**Motion convention** (details and reasons in `JetBot Notes.md`):
- `v, w` are normalized to [-1, 1]; positive `w` turns left. The Jetson mixes `left = v - K*w`, `right = v + K*w`.
- If either wheel value exceeds 1 in magnitude, **rescale both** by the larger one (never clip), so the turn ratio is kept.
- Jetson code must run on Python 3.6.

**Safety (non-negotiable):**
- The Jetson stops the motors if no control packet arrives for 300 ms.
- The kit gamepad is a **dead-man switch plus e-stop** (`jetson/estop.py`, runs on the robot host): the robot moves only while R1 is held and the e-stop is armed (hold Start 1.5 s); releasing R1 stops it, any other button or losing the pad is a hard stop, and every stop cuts the motor driver directly over I2C. `robot_udp.py` refuses to drive without the e-stop's heartbeat. Verified on the robot 2026-10-06 (wheels off the ground), including with `robot_udp.py` frozen. Details and limits in `docs/JetBot Notes.md`.
- Speed is capped during all HIL tests by `robot_udp.py --max-speed` on the robot (0.3 in `jetson/systemd/sentry-control.service`; the Jetson cannot read `config.toml`). Commands are scaled by the cap and then pass a dead zone (`deadzone(x, min_pwm)` in `common/mixing.py`: motor values below `min_pwm` 0.12 become 0, no compensation since PR #19), so at a 0.3 cap the usable command range is v 0.4-1.0, and an evasion arc with a small inner-wheel value loses that wheel; evasion also reaches only 0.3 of full speed. Raising the cap for the Week 9 evasion trials (Week 6 in the old calendar) is a safety decision for the team, recorded in the weekly log of whoever runs them.

## 4. Testing Policy

### 4.1 Tiers

| Tier | Marker | Runs where | Content |
| :-- | :-- | :-- | :-- |
| T0 Unit | (none) | Any machine, CPU, no network, whole suite < 60 s | Pure logic: geometry, formulas, state transitions, queue, packet encode/decode, controllers against `sim_robot` |
| T1 Replay | `replay` (+ `gpu` if it needs models) | Machine with `data/` synced | Run a module on a recorded dataset, assert metric thresholds, write a metrics JSON |
| T2 HIL | `hil` | DQK's setup | Scripted protocol on the real robot, N trials, results table |

- KR's machine runs `pytest -m "not gpu and not hil"`. CUDA members run `pytest -m "not hil"`. DQK also runs `-m hil`.
- `gpu` tests skip themselves when `torch.cuda.is_available()` is false.
- Every non-trivial function has at least one T0 test that fails if its logic breaks. Every perception module has a T1 test with a numeric threshold.
- Metrics are written as JSON to `reports/<handle>/week-NN/` so results are comparable across weeks.

### 4.2 Datasets (recorded with `tools/record.py`, stored in `data/`, never committed)

| ID | When | Recorded by | Content |
| :-- | :-- | :-- | :-- |
| D1 | End of W1 (door data continues in W2) | DQK (all present) | Room sweeps with the JetBot; **doorway views of 3+ different doors (2026-10-11: the method matches a user-supplied `I_ref`, so it must work for the door of any room; one entrance door per room is assumed, so each recorded door is a different room: cafe glass door, classroom door, one more), each with its own `I_ref` photo (colour, front-on, about 2 m), 10+ positions at 1-4 m and about -45 to +45 deg, plus negatives (no door visible; no second door in the room); labels in `assets/d1/doorway_labels_template.csv` format**; 20 obstacles at tape-measured distances 0.3-2.0 m in the room that is mapped (ground truth in `assets/d1/obstacles_template.csv` format); 30+ checkerboard images (done 2026-10-10: 58); ESP32 view of each door (label the camera: GC2145 tile stream or OV2640) |
| D2 | End of W3 | DQK + HNHL | ESP32 entries: each team member x 10 entries; non-enrolled entries: **leave-one-out with the three team members (decided 2026-10-24, no outside volunteers available)**: two members are enrolled, the third is the stranger, rotated so each member is the stranger once, and the 10 entries per member serve both roles; a public face set adds extra negatives for the ROC; outside volunteers (3+ x 5 entries, consenting) are added whenever available; logged walk direction (L/C/R) per entry for sector tests. **Report limit: only 3 non-enrolled identities, all teammates, so the false-accept rate is an optimistic estimate** |
| D3 | End of W5 | DQK | JetBot following one or two people: walking, stopping, occlusions, crossing paths |
| D4 | End of W8 (**changed** from W6 by the 2026-10-12 restructure) | DQK + KR labels | 20+ padded "lunges" (pillow on a stick, never a real strike) + 10 min of normal walking; onset timestamps labelled with `label_events.py` |
| D5 | W3 (collection), grows with every session | DQK records, all three label | **Floor-level objects from the robot's own camera (lens 0.10 m): legs and feet, wires (black, white, straight, curled), footwear, backpacks, bags, plus furniture and empty-floor negatives (20 %).** At least 150 labelled images per class, 2+ floors (matte and glossy), 2+ rooms, 3+ lighting conditions, 0.3-1.5 m; one whole session kept out of training for the T1. Stays in `data/`; people's legs only with consent and no faces in frame |

Privacy: face photos and recordings of volunteers stay in `data/` and the team Drive, are used only with consent, and are deleted after grading. **Exception (team decision 2026-10-24, to avoid passing the folder back and forth): the D5 frames (`data/D5/`, floor-level objects) are committed to this private repository, with every detected head painted over by `tools/mask_faces.py` and the borderline frames dropped; the unmasked originals (`data/D5_unmasked/`) and the excluded frames stay local and are never committed. Git history cannot be erased: after grading, delete or archive the repository rather than only the folder.** **Second exception (DQK's decision at the 2026-10-28 session, with the team's agreement as reported): D2 (ESP32 door entries) was recorded in a public cafe, so the frames include incidental bystanders in the background (small, far from the camera) and nothing was deleted because of them. Same handling: `data/D2/` is git-ignored and never committed, the frames stay on DQK's laptop and the team Drive, no unmasked frame appears in the report or the demo video (`tools/mask_faces.py` first), and everything is deleted after grading.**

### 4.3 Acceptance criteria per feature

| Feature | Metric | Pass threshold | Tier |
| :-- | :-- | :-- | :-- |
| Video uplink | Capture-to-laptop latency (clock-synced), FPS | p95 < 50 ms, >= 20 FPS at 640x480 | T2 |
| Control link | Packet loss; watchdog stop | < 1 % at 30 Hz; motors stop <= 350 ms after link loss | T2 |
| Fisheye calibration | RMS reprojection error | < 1.0 px | T1 |
| Camera tilt self-calibration (extra, DQK) | Live tilt from an ArUco marker (`LiveTilt`): median ground-distance error of the wall base against the marker-pose truth in drive runs from 2 m to 0.5 m (`reports/DoanQuocKien/week-02/live_tilt/`), live vs the fixed strips tilt; marker <= 1.5 m, speed <= 0.3 m/s | live median error <= 10 % and at least 2x lower than the fixed tilt; marker tilt within 0.5 deg of the strips at 1 m (the old "<= 1.5 deg" is 21 % at 1 m). 2026-10-14: fixed tilt 14-39 % off, live 0.5-6 % standing and 3-20 % moving (window 15 lagged; default now 3), 0.08-0.16 deg from the strips at 1 m | T1 |
| Obstacle distance | Relative error vs tape on D1 | median <= 10 %, p90 <= 20 % over 0.3-2.0 m | T1 |
| Obstacle repulsion | Collisions in exploration runs | 0 collisions in 5 x 3-min runs | T2 |
| **Floor-level obstacles: legs, wires, footwear, backpacks (REQUIRED minimum set, 2026-10-18)** | Detection on the robot's own view (lens 0.10 m): **human legs and feet, wires (black and white), footwear (shoes, sandals, slippers), backpacks and bags**, plus the furniture classes. T1 on **D5** (section 4.2), whole sessions held out of training (another day, floor or room): per class recall and precision at 0.3-1.5 m (wires 0.3-1.0 m), distance error as for 'Obstacle distance'. T2: the exploration protocol above with the whole set scattered in the arena | **Legs, footwear, backpacks and bags: recall >= 90 % and precision >= 80 %. Wires: recall >= 80 % and <= 1 false alarm per 20 empty-floor frames. Distance median <= 10 %, p90 <= 20 %. T2: 0 drive-overs of any item and 0 collisions in 5 x 3-min runs.** The numbers are the assistant's proposal (research in `docs/Small Object Detection.md`): **confirmed unchanged by the team at the 2026-10-28 session (reported by DQK)** and not lowered afterwards. A class that misses its target is reported as not met, with the mitigation in risk 30 | T1 + T2 |
| Entrance recognition (XFeat, DINOv2; ORB baseline; one door per room) | Frame-level TPR / FPR on D1 for the **primary demo door (the classroom door)**; thresholds calibrated on a sweep of that room's negatives, reference position left out of the evaluation. Other doors (the cafe glass door) are **secondary and optional**: measured and reported, no pass threshold | Classroom door: TPR >= 90 %, FPR <= 5 % (2026-10-12: 1.00 / 0.00, n = 210 / 52); secondary doors: report only (cafe glass 0.87 / 0.06) | T1 |
| Motion calibration + dead reckoning | Position error after 3 m path | <= 15 cm with ArUco correction, <= 40 cm without | T2 |
| Sweet-spot selection | Chosen spot satisfies the 3 spec conditions | 5/5 runs | T2 |
| ESP32 handshake | I_ref detection when camera faces door / is turned away | 10/10 correct accepts, 10/10 correct rejects | T2 |
| Face verification | TAR @ FAR on D2 | TAR >= 95 % at FAR <= 1 %; report ROC and justify 0.45 or a replacement | T1 |
| OSNet re-ID | Rank-1 on D2/D3 gallery (>= 5 people) | >= 85 %; threshold picked from ROC | T1 |
| Sector logging (optional search prior) | L/C/R accuracy on D2 | >= 90 % | T1 |
| Tracking | ID switches on D3 | <= 1 per minute (2-person scenes) | T1 |
| Pursuit PD | Steady-state distance; centering | 1.2 +/- 0.2 m; bbox centre within +/- 10 % of frame width, 80 % of the time | T2 |
| Hold detector | Target speed in the world frame while the robot yaws | robot rotation alone never triggers HOLD (sim); HOLD exits when target speed > exit threshold | T0 |
| Standoff hold | Trigger delay; re-centering | stops 2.0-3.0 s after the target stops; bbox centre within +/- 10 % of frame width within 1.5 s; no orbiting | T2 |
| Strike detection | Recall; false triggers; latency (frame to command) | recall >= 90 % on D4; <= 1 false trigger / 5 min of walking; <= 150 ms | T1 + T2 |
| Room map | Obstacle cells vs tape-measured positions on D1 | >= 80 % of the 20 obstacles within 20 cm | T1 |
| Coverage planner | 3 synthetic rooms in the recorded-map format | coverage >= 90 % of known-free cells, plan time < 2 s, tour no longer than a lawnmower baseline | T0 |
| Search & re-acquire | T2 present, T1 exits | T2 found during the planned path in >= 4/5 trials; record time to find | T2 |
| Search exhausted | T2 absent (removed from the room) | path completes, T2 dropped from the queue, robot reaches the next target or standby; 3/3 trials, 0 collisions | T2 |
| Full loop | Two consecutive intruders, start to standby | >= 4/5 runs without steering or intervention (the operator may hold R1; risk 15) | T2 |
| GPU budget | All models running together | peak VRAM <= 5.5 GB; pipeline >= 15 FPS | T1 (gpu) |
| Edge conversion parity (extra, proposed) | Every TensorRT engine against ONNX Runtime FP32 on the same input: cosine of the raw outputs; decoded boxes of the detectors; our parity set (200 D1 obstacle frames without faces, a public face set) | cosine >= 0.999 on every output; detector boxes matched at IoU >= 0.9 for >= 95 % of detections and the same count; 2026-10-16 on public photos: YOLOv8n, pose, OSNet, XFeat, MobileFaceNet, SCRFD (after the Resize fix) all >= 0.9999 | T1 (robot) |
| Edge latency and load (extra, proposed) | Stage B mix on live frames with a person in view, door pipeline in its own thread at 5 Hz, on battery, 15 min: capture-to-result, FPS, RAM, temperature | >= 20 FPS, capture-to-result p95 <= 100 ms, RAM < 3.0 GB, GPU temperature < 80 C, battery stays >= 11.1 V (2026-10-16, nobody in view: p95 72 ms, 2.1 GB, 40 C, 12.14 -> 11.93 V in 10 min) | T2 (wheels still) |
| Edge obstacle layer, Stage A (extra, proposed) | The same exploration protocol as 'Obstacle repulsion', with the obstacle layer on the robot; distance error against the laptop path on D1 | 0 collisions in 5 x 3-min runs; median distance error within 2 percentage points of the laptop's; the laptop fallback takes over within 1 s when the robot layer is switched off | T1 + T2 |
| Edge pursuit, Stage B (extra, proposed) | The 'Pursuit PD', 'Standoff hold' and 'Strike detection' rows run with the loop on the robot | the same thresholds as those rows; strike latency frame to command <= 150 ms with the link unplugged | T2 |
| Edge safety (extra, proposed) | Laptop disconnected (Wi-Fi off, app closed) while the robot runs the on-robot layer | motors stop <= 350 ms after the dead-man is released or a packet stream ends; e-stop and speed cap unchanged; companion-app `stop` stops the robot | T2 |

## 5. Weekly Plan

Each week is closed by an **integration session on the Monday of the following week, in the classroom** (decided 2026-10-25: working in the cafe is inefficient and costly, the classroom is cheaper, and the extra day leaves everyone more room to work to their deadlines; Week 3's session is Mon Oct 26), hosted by DQK (in person or screen-share): merge PRs, run T0/T1 on main, run that week's T2 protocols, record any dataset due. The week's work does not stop at Sunday: PRs and weekly logs are due Sunday night, so the session starts from a clean main.

**Calendar (restructured 2026-10-12).** Weeks 1-2 are unchanged. The old Weeks 3-8 are spread over Weeks 3-12: everything a 10-15 page report and a demo video can honestly show (Phases 1-2 on the robot, first pursuit and hold) is done before the mid-term; evasion and the next-target search come after it.

| Week | Dates | Theme | Milestone |
| :-- | :-- | :-- | :-- |
| 1 | Oct 5-11 | Networking & Telemetry | interfaces frozen, D1 started |
| 2 | Oct 12-18 | Pre-Scanning & Setup | calibration, D1 classroom, exploration T2 |
| 3 | Oct 19-25 | HCI Deployment & Biometrics | D2; ESP32 handshake T2 |
| 4 | Oct 26-Nov 1 | Re-ID Handoff & Phase 1 end to end | Phase 1 on the robot, Phase 2 on replay; report outline (T-3 w) |
| 5 | Nov 2-8 | Pursuit & Live Phase 2 | D3; Phase 2 live; first video shots |
| 6 | Nov 9-15 | Pursuit + Hold on the robot, Model Optimization | pursuit/hold T2; figures frozen, video shot (Mon Nov 16) |
| 7 | Nov 16-22 | Mid-Term Report & Buffer | draft Wed Nov 18, tag `midterm` Sat Nov 21 |
| 8 | Nov 23-29 | **Mid-term submission (Mon)** & Threat Evasion | D4 (moved from W6) |
| 9 | Nov 30-Dec 6 | Evasion Validation & Search Building Blocks | evasion T2, `r_det`, coverage planner |
| 10 | Dec 7-13 | Next-Target Integration | full loop with two intruders; overhead camera gate |
| 11 | Dec 14-20 | Integration Buffer & Stress Tests (contingency) | everything in section 4.3 green or explained |
| 12 | Dec 21-27 | Validation, Freeze & Rehearsal | code freeze Wed Dec 23, rehearsal Sat Dec 26, tag `final` Sun Dec 27 |
| 13 | Dec 28-Jan 3 | Final Submission & Defense | **submit Mon Dec 28**; defense by Fri Jan 2 |

**Extra task (proposed 2026-10-16, agreed by all three 2026-10-17): on-robot inference.** Aim: the Jetson Nano runs the time-critical models itself so the control loop does not depend on the Wi-Fi link, and the laptop becomes a companion app (start/stop, live view, confirm intruders). The laptop pipeline stays the default and the fallback for every deliverable; this is an extra, owned by DQK (Jetson side) with HNHL (parity, model choice) and KR (CPU-side ports). **Nothing in it is due in Week 2: the team agreed to take it before the Week 2 weekend meet-up (G0 passed, 2026-10-17; reported by DQK, confirm the owners at the Sun Oct 18 meet-up), and every work item below starts in Week 3 or later.** Evidence so far, the TensorRT 7.1 limits and how to repeat it: `docs/Edge Deployment.md`; the desk study and its staging: `docs/Edge Feasibility.md`; spec: section 4.7.

| Gate | When | Question | Pass | If it fails |
| :-- | :-- | :-- | :-- | :-- |
| G0 | Sun Oct 18 (W2 meet-up); **passed 2026-10-17, all three agreed** | Do we take the extra task? | all three agree and the owners below are accepted | nothing changes; the evidence is the report's optimisation chapter |
| G1 | Mon Oct 26 (W3 session) | Is the bench closed? | the section 4.3 'Edge latency and load' row passes with a person in view and live ESP32 frames, and the parity row passes on the parity set | stop; the report keeps the bench results as they are |
| G2 | Mon Nov 9 (W5 session) | Stage A: obstacle layer on the robot | the section 4.3 'Edge obstacle layer' and 'Edge safety' rows pass | stay on the laptop path; no further edge work before the mid-term |
| G3 | Mon Nov 30 (W8 session, after the submission) | Stage B: pursuit loop on the robot | pursuit, hold and the laptop-path strike rows already pass (W6, W8); G2 passed | pursuit stays on the laptop |
| G4 | Mon Dec 7 (W9 session) | Stage C (stretch): door pipeline, search, network on the robot | Stage B passed its rows and the team has a free week | the door and the search stay on the laptop; **no new edge work after Mon Dec 14**; code freeze Dec 23 applies as for everything |

Effort estimate (desk study, to be re-estimated at G1): Stage A about 4 person-days, Stage B 8-10, Stage C 8-12 (stretch). The bench and the conversion tooling (about 3 person-days) are already done and recorded.

### Week 1 (Oct 5-11): Networking & Telemetry

- **DQK**
  - First, run the "Verify on the robot" checks in `JetBot Notes.md` (jetbot version, motor driver address, Python version, camera modes) and record the outputs.
  - Bring up the JetBot (flash image, Wi-Fi on 5 GHz) and configure the Windows dual-band hotspot (ESP32 on 2.4 GHz).
  - `jetson/camera_pub.py`: GStreamer `nvarguscamerasrc` -> JPEG q60 -> ZMQ with the header from section 3.
  - `jetson/robot_udp.py`: (v, w) -> left/right motor speeds, 300 ms watchdog, gamepad e-stop, clock-sync echo.
  - Tests: T0 for packet decode and v/w-to-wheel mixing; T2 latency, FPS, packet loss and watchdog.
- **HNHL**
  - `sentry/net/zmq_rx.py`: latest-frame receiver thread with JPEG decode.
  - `udp_tx.py`: rate-limited 30 Hz sender.
  - `clock_sync.py` and a latency logger that writes CSVs. **Use `time.perf_counter()` for Windows-side timestamps: `time.monotonic()` ticks only every 15.6 ms there, which corrupts RTT and offset estimates (measured 2026-10-04).**
  - GPU baseline: YOLOv8n/s FPS and VRAM at 640 on the RTX 4050; confirm torch, insightface and onnxruntime-gpu run in `sentry` (Python 3.12, see Setup.md), and record versions. HNHL's RTX 5060 measurements must be labelled separately; they do not substitute for the RTX 4050 baseline.
  - Tests: T0 for clock-sync math with synthetic delays.
- **KR**
  - `tools/record.py` + `tools/replay.py`: record both streams with timestamps; replay through the same interface as the live receivers.
  - `tools/sim_robot.py`: UDP sink that integrates (v, w) with unicycle kinematics and logs pose.
  - `esp32/sentry_cam` sketch (based on CameraWebServer, VGA, 15 FPS, static IP). KR holds the ESP32 kit, so KR flashes and tests it directly, and brings it to the Monday session (needed for the ESP32 door view in D1 and the Week 3 handshake). **Update 2026-10-09:** DQK's modules turned out to be GC2145 (no JPEG); the 640x480 stream for that module is `esp32/tile_stream` + `sentry/espcam.py` (see `docs/ESP32-CAM.md`). KR: check which sensor your board has (`Camera PID=` in the boot log, or run `tile_stream` and read `esp_tile_rx`); an OV2640 board uses the stock sketch.
  - pytest skeleton: `conftest.py`, markers, `config.toml` loader.
  - Tests: T0 record-then-replay round trip gives identical frames and timestamps.
- **Session:** freeze the section 3 interfaces; record **D1**.

### Week 2 (Oct 12-18): Pre-Scanning & Setup

- **DQK**
  - `tools/calibrate_fisheye.py`: `cv2.fisheye` calibration on D1 checkerboards, writing `calib/camera.json`; measure `H_cam`.
  - `tools/calibrate_motion.py`: command fixed (v, w) for set durations, tape-measure the results, fit gains to `calib/motion.json`.
  - Tests: T1 reprojection error; T2 motion repeatability (5 runs each of straight 1 m and 90° turn).
  - **Extra (added 2026-10-12, DQK volunteers this week): camera tilt self-calibration.** The camera mount is tiltable and moved by about 3.6° between two sessions (2.6° down on 2026-10-11, about 1° up on 2026-10-12), and a lunge or evasion can shake it. `perception/camera_pose.py`: detect an ArUco marker (known size, known height on the wall) on undistorted frames, `solvePnP` -> camera tilt and height above the floor; median of the last N frames, reject jumps over 5°, keep the last value (or the session's `calib/camera_pose_<session>.json`) when no marker is in view; `obstacle.py` takes `pitch` as an input (pitched ground-plane model). `tools/measure_camera_pose.py` (floor strips + tape) stays the reference and the end-of-session check. Tests: T0 synthetic marker renders recover the tilt; T1 live tilt vs the strip method on the D1 classroom data. Keep the mount locked meanwhile (tape + pencil mark).
- **HNHL**
  - `perception/obstacle.py`: YOLOv8 on undistorted frames, COCO furniture classes (chair, couch, bed, dining table, potted plant, tv, refrigerator, suitcase), bottom-centre ground distance `d = f*H/(y_max - c_y)` (valid for a level optical axis; with the optional 15° down-tilt wedge use the pitched ground-plane model instead, and skip boxes cut off by the bottom image border, whose `y_max` is not the ground contact), repulsive angular term.
  - `nav/gridmap.py`: occupancy grid (robot pose + obstacle ground points -> occupied, driven/seen floor -> free, rest unknown); saved at the end of Phase 1 for the Week 9-10 search.
  - `nav/vantage.py`: score candidate stops on the grid for line of sight, 1.5-3.0 m from the door, and nearness to a boundary.
  - Tests: T0 for the distance formula, repulsion sign and grid updates on synthetic data; T1 distance error and map-vs-tape error on D1.
- **KR**
  - `sentry/perception/entrance.py` (**first version written 2026-10-12, KR owns it from here: tune, extend, own the tests**) + `tools/enroll_entrance.py` + `third_party/xfeat/` (vendored XFeat, Apache-2.0). `EntranceDetector(camera)(frame_bgr, t) -> EntranceResult(in_view, inliers, similarity, bearing_rad, quad)`; `EntranceFilter` turns the results into `ENTRANCE_FOUND` (with the bearing) / `ENTRANCE_LOST` events for the state machine. **Enrolment per room** (one entrance door per room is assumed): a frame from the robot's own camera with the door in view (2 m, straight on; keep that position out of every evaluation) + the door box (`--roi`), optionally a phone photo, and a sweep of the room without the door to calibrate the thresholds (`EntranceDetector.save/load`). **XFeat** (top_k 2048, mutual nearest neighbours, RANSAC homography, sanity check on the inliers' hull scale) against the robot-eye reference: door in view when the inliers pass the threshold (27, raised by `calibrate()` above the room's negatives); bearing = the door box projected through the homography (positive left, via the fisheye model), the centroid of the inliers without a box. **DINOv2** (cls + GeM of the patch tokens, cosine, `dino_size` b or s) is the phone-photo mode and an optional second opinion (`policy` auto | xfeat | dino | and | or; default `auto` = XFeat with a robot reference). ORB is dropped. Measured through the module on D1 with per-room calibration (`reports/DoanQuocKien/week-02/d1/entrance_bench_2026-10-12.md`, `python -m tools.enroll_entrance`): classroom door TPR 1.00 / FPR 0.00 (n = 210 / 52), bearing within about 6 deg at 1.5-3 m (no ground truth, indicative); cafe glass door (secondary and optional, no pass threshold: the classroom door is the primary demo door and the one that must pass 0.90 / 0.05) TPR 0.87 / FPR 0.06-0.08 (a harder door; thresholds from 6 negative positions lower TPR to 0.72 at FPR 0.00): DINOv2 thresholds are brittle per room (cafe TPR 0.37-1.00, FPR 0.00-0.27). Weights: `python -m tools.fetch_models` (`--dino b` for DINOv2, pinned commits). XFeat on a CPU is about 0.5 s per match (not re-measured on an idle machine): call it on demand on KR's laptop. Tests: T0 with injected fakes (`tests/test_entrance.py`), T1 replay on the D1 classroom door, real-XFeat warp test.
  - `nav/localization.py`: dead reckoning from `motion.json`, corrected by ArUco pose (`cv2.aruco`, 150 mm markers, `aruco_marker_m` in `config.toml`).
  - Tests: T0 for pose integration (closed square path returns to the origin in sim) and ArUco pose on synthetic renders; T1 entrance TPR/FPR on D1.
- **Status (Fri 2026-10-16):** merged: fisheye calibration (RMS 0.83 px), the motion calibration tools and the affine speed / turn fits and wheel law (`calib/motion.json`, `docs/Classroom Session 2026-10-15.md`), live camera tilt with roll (`LiveTilt`, PRs #35, #38), the entrance detector (PR #31; the classroom door, the primary demo door, passes at TPR 1.00 / FPR 0.00; the cafe glass door is optional), HNHL's obstacle detector with reflection handling (PR #34), KR's dead reckoning and ArUco correction (PRs #33, #37), the D1 classroom data and the 24-row obstacle pack for HNHL (PR #42). Still open: see the list below (this is Week 2: everything on it is due before the Sunday Oct 18 meet-up).
- **Still open before the Sunday Oct 18 meet-up (this is Week 2; checked at the session):**
  - DQK: the PR for the 2026-10-15 evidence log (`DoanQuocKien/w02-log`, not merged; `calib/motion.json` cites it); the Week 2 log with the Fri-Sun hours. Not a Week 2 blocker: the random heading error needs online correction from the marker, which is Week 3 work.
  - HNHL: issue #43 (chairs on the glossy floor get no distance, small or low objects are not detected); the T1 obstacle-distance result (median <= 10 %, p90 <= 20 %, 0.3-2.0 m) on the 24-row pack of 2026-10-15; the week-02 report is dated 2026-10-12.
  - KR: issue #41 (switch `localization.py` to the new wheel model); the week-02 report still describes the old ORB `entrance.py` (it is XFeat + DINOv2 now and KR owns it): update it and re-run the T1 entrance check on the classroom door, the primary demo door.
  - Session (Sunday Oct 18, hosted by DQK, run with HNHL and KR; these are the session's T2 protocols, not personal tasks): T2 exploration with obstacle repulsion, connected end to end (0 collisions in 5 x 3-min runs, section 4.3), which needs HNHL's obstacle layer, KR's pose, a cleared floor, a camera pose measured for that day's mount, and a runner that connects them (none is in the repo yet); T2 dead reckoning over a 3 m path with ArUco correction (DQK with KR), which needs the markers on rigid boards and issue #41 done first.
  - All: PR #45 is merged and G0 passed (agreed 2026-10-17); confirm the owners at the meet-up.
- **Session:** first small-object baseline (DQK, 2026-10-18, `reports/DoanQuocKien/week-02/small_objects_1018/`): the stock detector, an Open Images detector (601 classes incl. footwear, human leg, backpack) and the semantic floor find none of table, backpack, box; the open-vocabulary YOLO-World finds the large ones but never a wire (0 of 20). Result: the minimum set (section 4.3) needs a detector trained on the robot's view (`docs/Small Object Detection.md`). T2 exploration with obstacle repulsion, connected end to end; T2 dead reckoning over a 3 m path with ArUco correction (DQK with KR; position error <= 15 cm with the correction, <= 40 cm without, section 4.3; moved here from Week 4 on 2026-10-16).

### Week 3 (Oct 19-25): HCI Deployment & Biometrics

- **DQK**
  - Motion calibration is done (2026-10-15: affine speed and turn fits, wheel law, heading statistics; `calib/motion.json`). This week: wire `MotionEstimator` (marker range and bearing) into the drive tools and do the demo-room check from `docs/Classroom Session 2026-10-15.md`.
  - ~~USB speaker playback on the Jetson~~ replaced 2026-10-26 (no speaker, cost): the laptop plays the WAV prompts / alert sound (`sentry/app/audio.py`, `winsound`), triggered by the state machine; the Jetson `play`/`aplay` path stays in the code but is not used.
  - Deployment behaviour on the robot: stop at the sweet spot, face the room centre, prompt, wait for validation, reverse to standby.
  - **D5 (required, first item of the week):** record the floor-level object set from the robot's own camera with `tools/record.py` (legs and feet of team members, or volunteers with consent, black and white wires straight and curled, shoes, sandals, slippers, backpacks, bags, furniture, empty-floor negatives; matte and glossy floor; 0.3-1.5 m; section 4.2), at least 150 images per class, and hand the first batch (50 per class) to HNHL by Tue Oct 20 so training starts in Week 3; keep one whole session aside for the T1. **Added 2026-10-24: DQK records the first batch (50 per class) himself this week.** Then T2 exploration runs with the set in the arena once the detector exists.
  - Tests: T2 motion repeatability with the estimator in the loop; T2 deployment sequence, 5 runs.
- **HNHL**
  - **Floor-level obstacles (required minimum set: legs, wires, footwear, backpacks; issue #43 continues):** (1) auto-label D5 with the open-vocabulary backend (PR #46) and correct by hand, splitting the correction work with DQK and KR; (2) fine-tune YOLOv8n from the COCO weights on D5 (classes leg, footwear, backpack/bag, wire, plus furniture), compare 320 / 416 / 640 input; (3) for wires, if box recall stays under 80 %, a segmentation model (YOLOv8n-seg or a small strip-convolution network) on polygon labels plus pasted synthetic wires; (4) a geometric fallback for wires (thin dark or bright line on the floor, ground-plane check) so the keep-clear rule has a signal; per class recall and precision by Wed Oct 28.
  - `perception/face.py`: InsightFace detection + 512-d embedding. Check the insightface 2.0 API first; the spec names MobileFaceNet, so prefer the `buffalo_s` pack.
  - `tools/enroll_whitelist.py`: 3-5 photos per person, stored as **all** normalized embeddings (the spec uses max similarity, so no averaging).
  - Verification with a configurable threshold.
  - Tests: T0 for cosine and max-similarity logic; T1 ROC on D2, recording the chosen threshold and evidence.
- **KR**
  - `sentry/net/mjpeg_rx.py`: ESP32 stream with auto-reconnect (OV2640 path; the GC2145 tile stream already has `sentry.espcam.TileReceiver`).
  - ESP32 handshake check (reuses `sentry/perception/entrance.py` on the ESP32 frames: enrol the door with a reference from the ESP32 camera itself, a second `EntranceDetector` with its own thresholds; the robot-eye reference does not transfer to another lens).
  - Generate audio prompts offline (Windows SAPI via `pyttsx3`, or another offline TTS) into `assets/audio/`; they play on the laptop.
  - `app/state_machine.py` skeleton with all phase 1-3 states, transitions and timeouts.
  - Tests: T0 scripted event sequences for every transition, including invalid events, which are ignored and logged.
- **Extra (agreed 2026-10-17 at G0; checked at G1, Mon Oct 26)**
  - DQK: close the bench (`jetson/edge_bench.py`, `docs/Edge Deployment.md`): Stage B mix with a person in view; Stage C with live ESP32-CAM frames; a 15-minute run on battery with the voltage log; `tools/export_edge_onnx.py` and the evidence under `reports/DoanQuocKien/week-03/edge_deploy/`.
  - HNHL: the parity set (200 D1 obstacle frames without faces, a public face set) and the pass thresholds of the 'Edge conversion parity' row; review the conversion tooling PR.
  - KR: a Python 3.6 variant of the ESP32 tile receiver for the robot (`sentry.espcam.TileReceiver` imports `sentry.net.discover`), tested on recorded tile streams (T0, CPU only).
- **Report (all):** each member adds 3+ papers from their area to the list in `Mid-Term Report Plan.md` section 2.
- **Session:** record **D2**; T2 ESP32 handshake accept/reject.
- **Status (Sat 2026-10-24, DQK; ill Mon-Fri):** done: D5 first batch (397 frames, PR #59), papers 12-14, D2 leave-one-out (PR #57), edge bench with a person in view (PR #60: p95 78.1 ms, 2.13 GB, 40 C, 11.48 V min, 19.97 FPS), marker heading fix and T2 3 m dead reckoning closed loop (PR #56: 14.5 cm with correction, one run). Open for DQK: edge bench with live ESP32 frames and USB speaker playback (both need PR #55), deployment behaviour and its T2 (needs a door), D2 entries, more T2 repeatability runs. KR: PR #55 has one failing test (review comment). HNHL: no Week 3 branch or PR yet (`perception/face.py`, `tools/enroll_whitelist.py`, parity set, D5 labelling, which can start from the committed D5 frames).

### Week 4 (Oct 26-Nov 1): Re-ID Handoff & Phase 1 End to End

- **DQK**
  - Phase 1 end-to-end HIL: explore -> find entrance -> sweet spot -> prompt -> camera placed -> verified -> standby. Make sure the exploration covers the room (risk 8).
  - Tests: T2, 5 runs.
- **HNHL**
  - `perception/reid.py`: person crop from YOLO on ESP32 frames -> OSNet via torchreid with **re-ID-trained weights from `python -m tools.fetch_models`** (`osnet_ain_x1_0` domain-generalised, and `osnet_x0_25` Market1501); compare both on D2/D3 and keep the better one. Not `pretrained=True`: that is ImageNet-only.
  - Tests: T1 rank-1 and ROC on D2.
  - **Floor-level obstacles:** T1 on the held-out D5 session (section 4.3, row 'Floor-level obstacles'); freeze the detector and its class list for the exploration runs; edge export of the chosen model with the TensorRT recipe of `docs/Edge Deployment.md` (YOLOv8n at 320 is 14.8 ms on the Nano).
- **KR**
  - `app/target_queue.py`: FIFO of intruder records (id, face embedding, appearance vector, sector, snapshot path, timestamps).
  - Sector logging: bounding-box horizontal drift over 2 s -> L/C/R (optional prior for the Week 9 search).
  - Phase 2 replay pipeline on D2, connected end to end.
  - Tests: T0 for the queue and sector classification; T1 sector accuracy on D2.
- **Extra (proposed; only if G1 passed)**
  - DQK: Stage A: the obstacle ground-distance and repulsion logic as a Python 3.6 module on the robot (a local safety layer between the laptop's commands and the motors), engines built on the robot, laptop fallback switch.
  - HNHL: parity table of the robot's distances against the laptop path on D1 (median and p90 error), including the glossy-floor rows.
- **Report (all):** agree the outline, page budget and owners in `Mid-Term Report Plan.md` by Mon Nov 2 (T-3 weeks).
- **Milestone:** Phase 1 runs end to end on the robot; Phase 2 runs end to end on replayed D2. Both are the core of the mid-term demo.
- **Status (Wed 2026-10-28, DQK; the Mon 2026-10-26 session was solo, the teammates were busy):** done: the robot speaker is dropped (the laptop plays the alert sound, PR #70); the ESP32 board on hand is an OV2640 and `esp32/sentry_cam` works over Wi-Fi (about 10-11 FPS VGA, camera-fail and Wi-Fi supervision fixed, PRs #71-#73, one stream client at a time). **G1 live-ESP32 half closed on 2026-10-28** (full 900 s with a person in view of both cameras, cafe: 20.00 FPS, capture-to-result p95 69.7 ms, RAM 2.11 GB max, GPU 33 C max, battery 11.83 V min; the ESP32 frames reached the Jetson at only 2.36 fps in that run, since fixed on the firmware side to about 9 fps, see `docs/ESP32-CAM.md`; evidence in `reports/DoanQuocKien/week-04/edge_deploy/`). **G1 parity row measured on 2026-10-28 (PR #79):** TensorRT FP16 on the robot against ONNX Runtime FP32, cosine >= 0.999 on 13 of 13 outputs (lowest 0.999972), detector boxes matched at IoU >= 0.9 for 99.1 % (YOLOv8n), 100 % (pose, SCRFD); the literal 'same count' part is missed in 3 of 208 images by one borderline chair box each (for HNHL and the team to accept). **ESP32 handshake rehearsal in the cafe on 2026-10-28 (PR #80, `reports/DoanQuocKien/week-04/handshake/`): 9 of 10 correct accepts, 10 of 10 correct rejects, accepted as a pass by DQK; the plan's test at the classroom door is still to do.** **Also built on 2026-10-28 (sim-tested, not run on the robot):** the laptop plays the prompts (`LocalSpeaker`, PR #83), the Phase 1 deployment runner (go to the vantage, prompt, face the room centre, ESP32 handshake, retract; every command legal for the motor dead zone; the first version passed in the simulator with commands the real robot would not follow, found and fixed with the wheel model, PR #84), `tools/deploy_live` (R1/e-stop interlock, 30 Hz loop, handshake detector, obstacle STOP, T2 sheet answers; rehearsed with --no-robot, PR #85), the team data sharing protocol (`tools/team_data`, PRs #81-#82). Open from Week 3: the deployment on the real robot (the T2 deployment sequence, 5 runs, and the handshake at the classroom door; needs a door and a clear floor; DQK, later this week) the rehearsal and the robot dry run of `tools/deploy_live` (merged into the same classroom session). **Second D5 batch: not possible this week (no matte floor; decision DQK 2026-10-28):** D5 stays one glossy floor in one room, so the T1 'held-out session' of HNHL's Week 4 floor-level row has no separate session; HNHL holds out by another split (for example whole distance or position groups) and the report states that limit. Checklist for the classroom session: `docs/Classroom Session Deployment Checklist.md`. Outline agreed by all three (PR #86). **D2 recorded in the cafe on 2026-10-28:** one continuous clip per member (60 s), cut by `tools/d2_segment.py`: DQK 11 entries / 56 face frames, HNHL 5 / 41, KR 5 / 28 (125 frames, faces 45-86 px wide, KR's clip mostly motion-blurred); the plan's 10 entries per member is not met for HNHL and KR, every frame is used as it is (`data/D2/1028/d2_faces.csv`). Planned for a two-person session later this week: the deployment sequence, KR's handshake test, the teammates' D2 entries. If it slips past this week, Phase 1 end to end likely moves a week; no dates are changed here.

### Week 5 (Nov 2-8): Pursuit & Live Phase 2

- **DQK**
  - `nav/controllers.py` PD pursuit (heading from bbox centre, distance from the foot-point ground distance, target 1.2 m) and obstacle override when `d_obs < 0.5 m`.
  - Tune gains from logged step responses.
  - Tests: T2 standoff and centering metrics (first trials); record **D3**.
- **HNHL**
  - `perception/tracker.py`: YOLOv8 + ByteTrack (ultralytics tracker) on the JetBot stream; target lock filtered by the OSNet vector, with re-lock after occlusion.
  - GPU profiling of all models together.
  - Tests: T1 ID switches on D3; T1 (gpu) VRAM and FPS budget.
- **KR**
  - Hold detector: target ground speed in the world frame (robot pose and yaw compensated, so the robot's own rotation is not mistaken for target motion) < 0.1 m/s for > 2.0 s -> HOLD; exit when > 0.2 m/s (hysteresis).
  - HOLD behaviour: zero translation, yaw-only PD that keeps the bbox centered (reuses the PD yaw term from DQK's controller). No orbiting: the target would sit 90 degrees off-axis, outside the camera's field of view.
  - Closed-loop tests of PD and hold against `sim_robot` with a scripted target.
  - Tests: T0 for detector timing, hysteresis, and "robot yawing alone never triggers hold".
- **Extra (proposed; Stage A gate G2, Mon Nov 9)**
  - DQK: T2 obstacle layer on the robot, 5 x 3-min runs, and the link-unplugged safety check ('Edge obstacle layer', 'Edge safety' rows).
  - HNHL: the OSNet x0.25 against AIN Rank-1 comparison (W4) also in TensorRT FP16; the result picks the lock model for the robot.
  - KR: vendor the original ByteTrack tracker (MIT, numpy + scipy, Python 3.6; Ultralytics needs Python 3.8) into `third_party/bytetrack/`; T0 on synthetic tracks and a D3 replay against the Ultralytics tracker (ID agreement >= 95 %).
- **Report (all):** chapter drafts from the Week 1-4 evidence; figures F1-F15 (`Mid-Term Report Plan.md` section 3).
- **Session:** Phase 2 live at the door (ESP32 -> face -> re-ID -> queue); T2 pursuit first trials; first demo video shots (Phase 1, Phase 2).

### Week 6 (Nov 9-15): Pursuit + Hold on the Robot, Model Optimization

- **DQK**
  - Pursuit and hold on the robot: final gains, T2 pursuit PD and standoff hold protocols.
  - Chain Phase 2 -> Phase 3: `INTRUDER_QUEUED` -> deploy -> pursue -> hold, driven by the state machine.
  - Record the robot shots of the demo video (`Mid-Term Report Plan.md` section 5).
  - Tests: T2 pursuit PD and standoff hold (section 4.3 thresholds).
- **HNHL**
  - Model optimization for the report: FP16 (and TensorRT if it installs cleanly) vs FP32 for YOLOv8n and OSNet on the RTX 4050: latency, VRAM, accuracy change on D1/D2. Keep FP32 if accuracy drops.
  - Laptop screen recordings of the perception overlays for the video.
  - Tests: T1 (gpu) before/after optimization, same protocol as `tools.gpu_baseline`.
- **KR**
  - State machine: PURSUE/HOLD wired to the hold detector and the controller commands; Phase 1-3 transitions replayed from logged events.
  - Report editor: merge the chapter drafts, check the page budget, start the code appendix.
  - Tests: T0 for the Phase 2 -> Phase 3 event chain.
- **Extra (proposed):** DQK refreshes figures F20 and F21 (`Mid-Term Report Plan.md` section 3) with a person in view, the door thread and a battery run, and writes the 'Optimization and on-device deployment' section of chapter 5 with HNHL's laptop FP32 against FP16 numbers beside the robot's; figures frozen Mon Nov 16. No new edge features.
- **Session (Mon Nov 16, classroom):** T2 pursuit + hold; pick-up shots for the video. **Milestone:** experiments for the mid-term closed and figures frozen (T-7 days). Anything not working by now goes into the report as "in progress" with its plan; it is not rushed.

### Week 7 (Nov 16-22): Mid-Term Report & Buffer (no new features)

- **DQK**
  - Chapters 3, 4 and 8 final; edit the demo video (2-4 min) by Wed Nov 18.
  - Re-run any T2 whose evidence is missing for the report (battery check first).
- **HNHL**
  - Chapter 5 final with the ROC, distance-error, GPU and optimization figures.
  - Fix perception items that slipped in Weeks 5-6 (bug fixes only, via PR).
- **KR**
  - Editor: merged document, consistency of numbers against evidence files, code appendix (modules, owners, tests).
  - Clean-checkout test run and the submission package (`Mid-Term Report Plan.md` section 6).
- **Extra (proposed):** no edge work except the report text and figures; the report states plainly which mode (laptop or on-robot) each result was measured in.
- **Milestones:** Wed Nov 18 full draft + video cut (internal draft deadline); Thu-Fri Nov 19-20 internal review by all three, PR freeze Fri; Sat Nov 21 tag `midterm` on `main`; Sun Nov 22 PDF and video final.

### Week 8 (Nov 23-29): Mid-Term Submission & Threat Evasion

- **Mon Nov 23: submit the Mid-Term Report** (PDF + video link + `midterm` tag).
- **DQK**
  - Evasion override in the control path with the highest priority: v = -1.0, w = +/-0.8 for 400 ms, yawing away from the nearer obstacle side, then a cooldown.
  - Measure end-to-end reaction time with a high-FPS phone camera.
  - Tests: T2 evasion wheels-off and at the 0.3 cap; record **D4** (moved from W6).
- **HNHL**
  - `perception/pose.py`: YOLOv8-pose and a lunge detector (`dA/A > 0.40` within 100 ms using timestamps, not frame counts; or rapid ankle rise).
  - Tests: T0 for the detector on synthetic bbox series.
- **KR**
  - `tools/label_events.py`: keypress labeller for onset timestamps (ready before the D4 session).
  - False-trigger harness (false triggers per minute on normal walking).
  - EVADE state + cooldown in the state machine.
  - Tests: T0 for the state machine preempting PURSUE/HOLD with EVADE.
- **Extra (proposed; Stage B gate G3, Mon Nov 30):** the team decides Stage B once pursuit, hold and the laptop-path strike rows pass. If go, DQK starts it only after the evasion T2 passes (it competes with evasion in W8 and path following in W9); the plan: pursuit loop (pose model, ByteTrack, OSNet lock, PD and hold) in a Python 3.6 process on the robot, control packets to `robot_udp.py` unchanged.
- **Session:** record **D4**; evasion wheels-off and at low cap.

### Week 9 (Nov 30-Dec 6): Evasion Validation & Search Building Blocks

- **DQK**
  - T2 padded-lunge trials (the speed-cap decision of section 3 is recorded first).
  - Follow a planned path on the robot (waypoint following with the obstacle override and ArUco pose corrections) and the slow in-place 360° scan at each viewpoint.
  - Measure the effective detection radius `r_det` (distance at which OSNet still matches reliably; 3 people) and write it to `config.toml`.
  - Tests: T2 strike evasion (latency part); path-following error over the 3 m protocol of the Week 2 dead-reckoning test.
- **HNHL**
  - Tune the lunge detector on D4.
  - Exit-event detection on the ESP32 (re-ID matches T1 at the door and motion is toward the door).
  - Tests: T1 recall and latency on D4; T1 exit detection on recorded exits.
- **KR**
  - Label D4 with `label_events.py`; T1 false-trigger rate.
  - `nav/coverage.py`: viewpoints chosen greedily on the saved map until the coverage target is met within `r_det` and line of sight; tour ordered by nearest neighbour + 2-opt; legs connected by A* on an obstacle-inflated grid; optional departure-sector prior.
  - Tests: T0 for the planner on 3 synthetic rooms (coverage, plan time, tour length vs a lawnmower baseline); T1 false-trigger rate.
- **Extra (proposed; gate G4, Mon Dec 7):** Stage B continues (T2: pursuit, hold and strike latency <= 150 ms with the link unplugged); G4 decides whether Stage C (door pipeline, search, network on the robot) is attempted at all.
- **Session:** T2 strike evasion; first path-following run on the saved map.

### Week 10 (Dec 7-13): Next-Target Integration

- **DQK**
  - Search on the robot: plan -> follow -> scan -> re-acquire, and the not-found drop.
  - Full-loop HIL with two intruders.
  - Tests: T2 search & re-acquire (5 trials), search exhausted (3 trials), full loop (5 runs).
- **HNHL**
  - Search-time re-ID matching on the JetBot stream while moving and scanning, with a lock threshold.
  - GPU budget with every model running together (YOLOv8, YOLOv8-pose, InsightFace, OSNet, tracker).
  - Tests: T1 re-acquisition precision; T1 (gpu) VRAM and FPS budget.
- **KR**
  - Handoff orchestration in the state machine: TARGET_EXITED -> PLAN -> FOLLOW/SCAN -> TARGET_FOUND -> PURSUE, or SEARCH_EXHAUSTED -> drop from queue -> next target or STANDBY.
  - Tests: T0 for the two-intruder event script, including the not-found drop.
- **Extra (proposed):** only Stage C if G4 passed, and only until Mon Dec 14; otherwise the door pipeline and the search run on the laptop as specified.
- **Session:** two-intruder rehearsal. **Gate (Mon Dec 14):** overhead camera decision (`Hardware.md` section 2).

### Week 11 (Dec 14-20): Integration Buffer & Stress Tests (contingency week)

First finish any section 4.3 row that failed or slipped in Weeks 8-10; only then the stress tests below.
- **DQK**
  - Stress tests: low battery, Wi-Fi drop (watchdog), dim and bright lighting, cluttered room.
  - Full-loop re-runs if Week 10 missed 4/5.
- **HNHL**
  - Perception stress tests (backlight, partial faces, hats and masks, similar clothing).
  - Re-run every perception T1 whose code or threshold changed since Week 6.
- **KR**
  - Edge-case state machine tests (empty queue, lost ESP32 stream, T2 never found leading to a timeout and return to standby, intruder leaving during evasion).
  - README with the run steps from a clean checkout.
- **Session:** full loop re-runs; list what is still red in section 4.3.

### Week 12 (Dec 21-27): Validation, Freeze & Rehearsal

- **DQK**
  - Record the final demo footage.
  - Presentation: system and robot section.
- **HNHL**
  - Final metrics tables against section 4.3.
  - Presentation: perception section.
- **KR**
  - Final test report, presentation assembly, final package check (same rules as the mid-term package; tag `final`).
- **Milestones:** **code freeze Wed Dec 23** (bug fixes only, via PR); full rehearsal with the robot Sat Dec 26 (charged battery, `tools.jetbot_status` first); package and tag `final` Sun Dec 27. Dec 24-25 are holidays: plan nothing that needs all three.
- **Final check:** every section 4.3 row has an evidence link in someone's report.

### Week 13 (Dec 28-Jan 3): Final Submission & Defense Window

- **Submit Mon Dec 28** (first day of the window, the safe target). The defense can fall on any day up to Fri Jan 2; Jan 1 is a holiday.
- Until the defense: keep the robot charged and the demo setup packed; fixes only for blocking bugs.
- After grading: robot return checklist (`JetBot Notes.md`), delete volunteer data (section 4.2, Privacy).

## 6. Workflow & Reports

**Git:**
- Branch `<handle>/wNN-<topic>` (e.g. `kouun-rokku/w02-orb-entrance`), then a PR to `main` with one approving review and T0 passing.
- Review rotation: DQK's PRs -> KR, KR's -> HNHL, HNHL's -> DQK (a CUDA reviewer for GPU code).
- No direct pushes to `main`.

**Definition of done for a work item:**
1. Code is merged via a reviewed PR.
2. Tests at the tiers listed for it exist and pass.
3. Evidence is in the owner's weekly report.

**Report directories:**
```
reports/<handle>/week-NN.md     # weekly progress log (template: reports/TEMPLATE.md)
reports/<handle>/week-NN/       # test evidence: pytest logs, metrics JSON/CSV, plots, T2 trial tables
```
- Weekly logs are due Sunday night, before the integration session.
- Large media (videos) go to the team Drive and are linked from the log, never committed.

## 7. Assumptions & Open Risks

| # | Item | Plan |
| :-- | :-- | :-- |
| 1 | Spec's strike window of "100 ms" is only 1.5 frames at 15 FPS | Measure the actual JetBot pipeline FPS in W1; use timestamp-based windows; if FPS < 20, widen the window to 2 frames and re-tune the 0.40 threshold on D4 |
| 2 | The spec does not say how "T1 exits" is detected | ESP32 re-ID + direction of motion toward the door (W9, HNHL) |
| 3 | COCO classes miss walls, boxes and bags | Accept for W2; if exploration collisions occur, add a bottom-of-frame floor-edge check or fine-tune on D1 frames |
| 4 | The L/C/R departure sector is in ESP32 camera coordinates, not world, and is now only an optional prior | Record the ESP32 placement pose in phase 1; KR maps it to a world bearing only if the planner uses the prior (W9) |
| 5 | Model package upgrades can change Python, CUDA or API compatibility | **Resolved for the recorded W1 environments:** Python 3.12 verified by HNHL; DQK's InsightFace CUDA detector + embedder about 7 ms, OSNet 11-13 ms and 3-model pipeline 37 FPS under 300 MB (`reports/DoanQuocKien/week-01/gpu_baseline_2026-10-06.txt`). Record versions and rerun checks after upgrades. |
| 11 | torchreid `pretrained=True` gives ImageNet-only weights, not re-ID weights, which would make the 85 % Rank-1 target unreachable | Use the re-ID weights from `tools.fetch_models`; osnet_ain_x1_0 (domain-generalised) vs osnet_x0_25 (Market1501, same-domain) is decided by Rank-1 on D2/D3 |
| 6 | All HIL depends on DQK's availability | Offline-first development; two scheduled sessions per week from W5 onward |
| 8 | The room map only knows floor the robot has seen: YOLO misses walls and unclassified objects | Plan only over known-free cells with inflated obstacles; report the coverage fraction achieved; make sure the Week 4 exploration covers the room |
| 9 | The effective detection radius `r_det` is unknown | Placeholder 3.0 m in `config.toml`; DQK measures it in W9 and the plan is recomputed from it |
| 10 | Dead-reckoning drift along a long search path (no encoders) | Re-localize whenever an ArUco marker is seen; measure path-following error in W9; shorten the path by lowering the coverage target if error is too large |
| 7 | Mid-term due date was assumed to be Nov 1 | **Resolved 2026-10-12 (DQK):** due Mon 2026-11-23 (10-15 pages, with the code), final window 2026-12-28..2027-01-02. Section 5 restructured to 13 weeks; Week 7 is the report week (internal draft Wed Nov 18) |
| 12 | The ESP32-CAM modules (both the Shopee and the local one) carry a GC2145, which has no hardware JPEG: the plan's HTTP MJPEG VGA 15 FPS is impossible with the stock sketch (1.7-7.7 FPS) | **Worked around in software on 2026-10-09:** raw Bayer + changed-tile UDP stream, 14.4 FPS average, 9-10 FPS worst case; needs a fixed camera. Alternative: buy an OV2640 module (about 25 FPS VGA, stock sketch). **Decision 2026-10-11 (DQK): keep the tile stream as the interface.** An OV2640 was also ordered that day as an option (`docs/ESP32-CAM.md`); using it changes the frozen interface, so it needs a PR all three approve. **2026-10-26: the board on hand is the OV2640** (the tile firmware on it gave 1.6 FPS and wrong colours); with `esp32/sentry_cam` it streams about 10-11 FPS at VGA over Wi-Fi and the laptop finds a face in 65 of 65 frames (one person, one position). It serves **one client at a time** (the Jetson bench and the laptop cannot both read it). The interface switch is still undecided: agenda for the next session. Details: `docs/ESP32-CAM.md` |
| 13 | The second ESP32-CAM board loses its Wi-Fi uplink while the camera runs (cause unknown); the first board is fine | Use the first board for the stream; ask KR to test their board; if a board shows send failures only while the camera runs, swap it |
| 14 | ORB entrance matching is weak from the robot's low 160 deg fisheye view on both a frameless glass door (cafe, 2026-10-11) and a plain white solid door (classroom, 2026-10-12: positives p10 at or below the negatives' p95 in every ORB / SIFT variant; a phone photo as reference gives AUC 0.6-0.7) | **Replaced by XFeat + DINOv2 (2026-10-12, `sentry/perception/entrance.py`).** Through the module with per-room calibration: classroom TPR 1.00 / FPR 0.00, cafe glass door TPR 0.87 / FPR 0.06. **Decision (DQK, 2026-10-12, confirmed 2026-10-16): the classroom door is the primary demo door and the only one that must pass the 0.90 / 0.05 target; other doors (the cafe glass door) are secondary and optional, reported without a threshold.** Open: one session per room with a same-session reference, so a second session on the classroom door decides how robust the primary result is (a third room is optional); DINOv2 thresholds are brittle (use XFeat as the primary); a marker on the door only as a fallback, with the team's approval |
| 15 | **Decided provisionally 2026-10-12 (DQK), subject to change.** The full-loop criterion says "without manual help" (section 4.3), but the robot moves only while an operator holds R1 (section 3, Safety) | Holding R1 stays allowed during the pursuit and full-loop trials: reword the criterion to "without steering or intervention" (the operator only holds the dead-man) and say so in every report. Do not loosen the dead-man; a supervised mode would need its own safety case |
| 16 | **Open, needs a team decision (audit 2026-10-11).** The video target p95 < 50 ms is missed on the default 2.4 GHz hotspot (53-62 ms measured, `docs/JetBot Notes.md`), and the spec's simultaneous 2.4 + 5 GHz bands are not what the single-radio Windows hotspot provides | `docs/Hardware.md` section 2 has the router gate (ping p95 > 50 ms): decide whether it has triggered, or record the conditions under which the hotspot meets the target |
| 17 | The mid-term report competes with integration work in Weeks 5-7 | Week 7 has no new features; figures are made from each week's evidence as it lands (W5-W6), not at the end; anything not working by Mon Nov 16 is reported as "in progress" with its plan. Evasion and search are deliberately after the mid-term |
| 18 | The demo video needs a working robot on a charged battery, on a given day | Shoot each shot as soon as its feature works (W5-W6 sessions), pick-up session Mon Nov 16, spare day Sat Nov 21; `tools.jetbot_status` before every take (>= 11.1 V); fallback shots from replay or `sim_robot`, captioned as such, never passed off as live |
| 19 | Only one robot (DQK holds it): a motor, camera, SD card or battery failure stops every T2 and the video | Offline-first (section 1); record datasets early; back up the robot's SD card once the systemd setup is final; keep a replay-based demo path for every phase |
| 20 | The school-owned robot's return date | **Resolved 2026-10-12 (DQK): the robot is returned after the final.** Keep the return checklist in `JetBot Notes.md` current; the final live demo can use the robot; back up its SD card before the final |
| 21 | The final window 2026-12-28..2027-01-02 sits in the holidays (Dec 24-25, Jan 1; members may travel) | Report, presentation and live demo are all due, on a day we choose (subject to change): pick the day by the end of W9 and ask the instructor early; code freeze Wed Dec 23, package Sun Dec 27, W11 is the contingency week; rehearse the live demo on Sat Dec 26 |
| 22 | The camera tilt changes between sessions (tiltable mount, 3.6° seen on 2026-10-12) and a wrong tilt gives a wrong ground distance (1° is about 15 % at 1 m and 26 % at 2 m with the lens 0.10 m high) | Lock the mount mechanically and put a pencil mark on it; one `camera_pose_<session>.json` per D1 session; re-check with 3 strips at the end of each session; live tilt from an ArUco marker (Week 2 extra, `LiveTilt`, validated on the robot 2026-10-14) with a fallback to the stored value. **Measured: the chassis tilt itself differs by up to 1.7° between floor spots (a 10 cm wheelbase follows tile edges), so the live value is needed, not only the mount lock.** Pitch and camera roll are a coupled pair (`LiveTilt` sets both; a roll mismatch costs 15-70 % above a 20° bearing; measured roll +1.1°, the strip-click value -1.85° was wrong). A 150 mm marker is about 15 px wide at 3 m, so trust the live value only within about 1.5 m (the marker pose is noisiest at 2 m); use the median of 3 frames (15 lagged a moving robot by about 1 s) |
| 23 | **Glossy floor reflections bias the ground distance (found 2026-10-12, D1 classroom).** The polished tile mirrors low objects, so the box/mask bottom that the detector returns includes the reflection: with the strip-verified camera pose (flat paper at 1.0 m: -5 %), a 3 cm wooden block at 0.70 m read 0.59 m (-16 %) and a chair front rail at 1.40 m read 1.21 m (-14 %); the offset is about `fy * h / d` px for an object of height `h`. The 10 % median-error target (section 4.3) would fail on this floor | HNHL (`obstacle.py`): treat the contact row as the join of the object and its mirror image (symmetry search at the bottom of the box) or use segmentation masks, and report the error on a glossy and a matte floor separately; keep every D1 obstacle row with the floor type; DQK: add a matte-floor setup to the next session |
| 24 | **Assumption (DQK, 2026-10-12): one entrance door per room.** The entrance detector answers "is THE entrance in view, and where"; telling two similar doors apart, or a door from a second door in the same room, is out of scope | Enrolment is per room (`tools/enroll_entrance.py`); the D1 doorway sets record one door per room (a room with several doors is recorded for its entrance only); say it in the report's assumptions; if a demo room has two doors the entrance reference must be unique-looking (a marker on it, with the team's approval) |
| 25 | **TensorRT 7.1 can compute an operator wrongly without an error or warning.** Found 2026-10-16: the insightface SCRFD `Resize` nodes (opset-11 `sizes` form) gave a cosine of 0.88 to 0.99 against ONNX Runtime in FP32 and FP16 alike, face scores 0.72 instead of 0.81 and landmarks off by about 10 px | Every engine is checked against ONNX Runtime before use (section 4.3 'Edge conversion parity'); the fix is in `tools/export_edge_onnx.py` (nearest 2x upsampling as a grouped ConvTranspose, with a test); a layer-by-layer comparison locates a bad operator; opset 11 or lower, no `grid_sample`, no bicubic Resize |
| 26 | The on-robot stack is Python 3.6 with OpenCV 4.1.1: no Ultralytics, `sentry/` code uses 3.7+ features and `cv2.aruco.ArucoDetector`, whether the JetPack OpenCV has the aruco module is unchecked | Edge code stays in 3.6-compatible `jetson/` modules (`yolo_post.py`, `face_post.py`, `trt_runtime.py`, tests included); ByteTrack vendored (W5, KR); check `cv2.aruco` on the robot before any localization port; `pycuda` and TensorRT are already in the JetBot container |
| 27 | A self-contained robot needs its own network: on 2026-10-16 the robot lost its network when the phone hotspot left and was unreachable for about 20 minutes | Gate G4 (stretch) covers it; a travel router (`Hardware.md` section 2) is the safe option, the robot as an access point on the RTL8822CE is unverified (2.4 GHz only at best); until then keep the laptop hotspot and the phone fallback |
| 28 | SD card integrity on the only robot: the card was removed twice without `sudo shutdown now` (unreplayed journal), and the laptop-side USB card reader plus `usbipd` path silently dropped writes during a repair, so the same fixes never stuck; a second card from the same image showed far more filesystem errors | Rules in `JetBot Notes.md` (shut down cleanly, never write the card through that reader, check any new card with `e2fsck -n` before use); root grown to 58 GB (34 GB free) and the filesystem repaired on 2026-10-16; back up the card once the setup is final (risk 19) |
| 29 | Power: on-robot inference adds about 3 W (board 4.6 to 5.8 W against 2.5 W idle) and 10 minutes of compute alone dropped the battery from 12.14 to 11.93 V; motors will add much more | Drain test from full to 11.1 V with a driving profile before any runtime claim (section 4.3 'Edge latency and load'); keep the 10.5 V stop rule; MAXN stays on (the 5 W mode costs about a third of the frame rate, desk study) |
| 30 | **Legs, wires, footwear and backpacks must be detected (required minimum set; issue #43; found 2026-10-15, measured 2026-10-18).** Stock YOLOv8n, an Open Images YOLOv8n (601 classes with footwear, human leg, backpack) and the semantic-floor backend find none of table, backpack, box from the robot's 0.10 m view; the open-vocabulary YOLO-World finds large objects (10-14 % short) but not a wire (0 of 20). The viewpoint, not the label set, is the cause: public datasets are shot from human height, and there is no public set from a floor-level robot camera. Cables are 1-2 px thick | Train on our own view (D5, section 4.2): fine-tune YOLOv8n, auto-labelling with the open-vocabulary model, segmentation or synthetic wires for the wires, a geometric wire check as fallback; required row in section 4.3 with per-class targets; the exploration arena holds the whole set; speed cap and keep-clear rule if a class stays unmet; the report states the measured result per class | HNHL, DQK |
