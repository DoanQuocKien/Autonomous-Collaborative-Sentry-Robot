# **Autonomous Collaborative Sentry Robot: Project Specification**

**Course:** CS532 – Computer Vision in Human-Computer Interaction  
**Institution:** University of Information Technology (UIT – VNU-HCM)  
**Project Scope:** 13-Week Capstone Implementation (2026-10-05 to 2027-01-03; restructured 2026-10-12, see section 6)

## **1\. System Summary & Operational Scope**

The objective of this project is to implement a distributed sentry system using a mobile JetBot, an external stationary camera (ESP32-CAM), and a central processing laptop running an NVIDIA RTX 4050 GPU.  
The system operates across three distinct phases:

> 1. **Setup & Mapping:** The JetBot navigates the room, avoids obstacles, matches the entrance against a reference photo, identifies an unobstructed vantage point, and prompts the user to place the ESP32-CAM.  
> 2. **Access Control:** The ESP32-CAM monitors the entrance, matching entrants against a whitelist of registered occupants. Unregistered entrants are flagged, assigned an appearance embedding, and queued.  
> 3. **Physical Deterrence & Evasion:** The JetBot shadows the intruder, stops and keeps them centered if they remain stationary, and executes an evasive reverse maneuver if an aggressive forward movement or strike is detected. Once the intruder exits, the JetBot searches for the next target in the queue along a coverage path planned on the room map recorded during setup, and drops a target it cannot find.

## **2\. External Hardware Requirements**

*Note: All core JetBot components (Jetson Nano 4GB B01, CSI camera, chassis, motors, expansion board, Wi-Fi card, 18650 batteries, and charger) are already supplied.*

### **Required External Hardware**

* **Processing Base Station:** Windows 11 laptop equipped with an NVIDIA RTX 4050 GPU (6GB VRAM) and dual-band Wi-Fi support.  
* **Stationary Sensor Node:**  
  * ESP32-CAM module: OV2640, or the GC2145 boards the team has (no hardware JPEG, so a UDP changed-tile stream replaces MJPEG; `docs/ESP32-CAM.md`).  
  * 5V power source (lithium cell with 5V boost circuit or compact USB power bank).  
  * FTDI USB-to-TTL adapter (for initial firmware flashing via Arduino IDE).  
  * Minimal enclosure or stand to position the module on the floor or a shelf.  
* **Audio Feedback:** USB mini speaker connected to the Jetson Nano, playing pre-generated WAV prompts (offline TTS, rendered on the laptop) for setup prompts and deterrent alarms.  
* **Localization Markers:** Cardstock ArUco markers (150 mm, `aruco_marker_m` in `config.toml`) as position anchors (the kit has no encoders or IMU), plus a printed checkerboard for one-time fisheye camera calibration.

### **Optional External Hardware**

* **Overhead Room Camera:** \$1080\\text{p}\$ wide-angle USB webcam or RTSP IP camera placed high in the room to maintain continuous 2D coordinates of all occupants.  
* **CSI Camera Down-Tilt Mount:** \$15^\\circ\$ downward angle bracket for the JetBot to improve visibility of feet and floor obstacles at close range.  

## **3\. System Inputs**

> 1. **Entrance Reference Image (\$I\_{\\text{ref}}\$):** A static color photograph of the target doorway.  
> 2. **Occupant Whitelist (\$\\mathcal{F}\_{\\text{whitelist}}\$):** A set of 3 to 5 reference photos per authorized room occupant, stored as pre-calculated 512-dimensional facial feature vectors.

## **4\. Algorithmic Pipeline & Functional Logic**

\[Phase 1: Setup\]  
Reference Photo \+ Floor Exploration   
  \-\> Entrance Match (XFeat; DINOv2 for a phone photo)   
  \-\> Optimal Vantage Point Selected   
  \-\> Audio Prompt   
  \-\> User Places ESP32-CAM   
  \-\> Verification \-\> JetBot Retracts to Standby

\[Phase 2: Monitoring\]  
ESP32-CAM Stream \-\> Face Detection (InsightFace)   
  \-\> Whitelist Cosine Similarity   
  \-\> Unregistered?   
  \-\> Extract OSNet Re-ID Embedding   
  \-\> Push to Target Queue

\[Phase 3: Interception\]  
JetBot Deploys \-\> Pursue Target (YOLOv8 \+ ByteTrack)  
  ├── Target Moving   \-\> Distance Maintenance & Obstacle Avoidance  
  ├── Target Stops    \-\> Hold Position & Re-center (no orbit)  
  ├── Attack Detected \-\> Preemptive Reverse/Yaw Evasion  
  └── Target Exits    \-\> Receive Exit Event \-\> Coverage-Path Search on Room Map \-\> Found? Pursue : Drop from Queue

### **4.1 Exploratory Pre-Scanning & Obstacle Avoidance**

* The JetBot navigates through open floor areas to inspect occluded corners rather than solely spinning in place.  
* The onboard video feed is processed on the RTX 4050 using YOLOv8. The bottom edge of each detected furniture bounding box \$(x\_{\\text{mid}}, y\_{\\text{max}})\$ is converted into an approximate ground distance:

\$\$d\_{\\text{obs}} \= \\frac{f \\cdot H\_{\\text{cam}}}{y\_{\\text{max}} \- c\_y}\$\$

* The IMX219-160 is a fisheye lens: calibrate once with a checkerboard (OpenCV fisheye model) and undistort frames before applying the formula. $f$, $c_y$ and $H_{\text{cam}}$ come from the calibration config.  
* Robot pose is tracked by dead reckoning from calibrated $(v, \omega)$ commands, and corrected whenever an ArUco marker is visible.  
* **Room map:** while exploring, the base station builds a 2D occupancy grid in world coordinates: robot pose comes from dead reckoning, the ground point of each detected obstacle marks occupied cells, floor the robot has driven over or seen is free, and unseen cells stay unknown. YOLO does not detect walls or unclassified objects, so the map only covers known-free floor. It is saved at the end of Phase 1 (with the guarding position) and used by the search in section 4.6.  
* If any obstacle falls within \$0.6\\text{ m}\$, the base station injects a repulsive angular velocity component to steer the robot into open floor space.

### **4.2 Entrance Localization & Vantage Selection**

* While moving, the system matches the onboard video feed against the entrance reference \$I\_{\\text{ref}}\$: XFeat local features (mutual nearest neighbours, RANSAC homography) against a reference frame from the robot's own camera, or DINOv2 global descriptors (cosine similarity) when only a phone photo of the doorway is available. Thresholds are calibrated per room. ORB was the original choice and was dropped after the D1 bake-off (Implementation Plan risk 14).  
* Once the matches (RANSAC inliers, or the DINOv2 similarity) pass the calibrated threshold, the entrance direction vector (the bearing of the door through the fisheye model) is recorded. One entrance door per room is assumed (decision 2026-10-12): the detector answers "is the entrance in view, and where".  
* The robot identifies a stopping position ("sweet spot") that meets three conditions:  
  * Unobstructed line of sight to the entrance.  
  * Distance to the entrance between \$1.5\\text{ m}\$ and \$3.0\\text{ m}\$ (sufficient for face resolution on the ESP32-CAM).  
  * Proximity to an adjacent boundary or furniture item for unobtrusive staging.

### **4.3 HCI Deployment Protocol**

* The JetBot stops at the sweet spot, turns toward the center of the room, and plays a pre-generated audio message through the USB speaker: *"Guarding position reached. Please place the entrance camera."*  
* The user positions the ESP32-CAM at the designated spot facing the door.  
* The base station ingests the ESP32-CAM stream and checks that \$I\_{\\text{ref}}\$ is visible.  
* Upon validation, an audio confirmation plays, and the JetBot reverses into a nearby standby position.

### **4.4 Entrance Verification & Target Queuing**

* The ESP32-CAM monitors incoming individuals. Detected faces are normalized and processed through InsightFace (MobileFaceNet).  
* Embeddings are evaluated against \$\\mathcal{F}\_{\\text{whitelist}}\$ using cosine similarity:

\$\$\\text{Sim}(\\vec{e}\_{\\text{det}}, \\vec{e}\_{\\text{white}}) \= \\vec{e}\_{\\text{det}} \\cdot \\vec{e}\_{\\text{white}}\$\$

* If the maximum similarity is below \$0.45\$, the person is marked as an intruder.  
* A full-body crop is passed to OSNet to generate an appearance feature vector (\$\\vec{a}\_{\\text{target}}\$).  
* The intruder is pushed to a First-In, First-Out (FIFO) queue \$\\mathcal{Q}\$. The JetBot is signaled to engage.

### **4.5 Pursuit, Standoff Hold & Evasion**

* **Pursuit:** The JetBot uses its onboard camera to track the assigned intruder using YOLOv8 and ByteTrack, filtered by \$\\vec{a}\_{\\text{target}}\$. A Proportional-Derivative (PD) controller adjusts motor speeds to center the bounding box and maintain a \$1.2\\text{ m}\$ separation distance.  
* **Obstacle Override:** If an obstacle is detected in the foreground (\$d\_{\\text{obs}} \< 0.5\\text{ m}\$) during pursuit, the controller adds an angular offset to bypass the obstacle while maintaining the target in the field of view.  
* **Standoff Hold:** If the target's ground speed stays below 0.1 m/s for more than 2.0 s, the JetBot stops translating, keeps tracking the intruder, and rotates in place (yaw-only PD) to keep the bounding box centered. It does not orbit: a differential-drive robot circling a point always faces along its path, which would put the target 90 degrees to the side, outside the camera's field of view. Target speed is computed in world coordinates (robot pose and yaw compensated), not from image displacement, because the robot itself rotates while holding. Pursuit resumes when the target's ground speed rises above an exit threshold (proposed 0.2 m/s, so the state does not flicker).

* **Kinematic Strike Evasion:** YOLOv8-pose monitors keypoints (hips, knees, ankles) alongside bounding box geometry. If a forward lunge occurs—indicated by a bounding box area growth rate \$\\frac{\\Delta A}{A} \> 0.40\$ within \$100\\text{ ms}\$ or rapid ankle elevation—the pursuit logic is overridden with an immediate high-speed reverse and yaw pulse (\$v \= \-1.0, \\omega \= \\pm 0.8\$ for \$400\\text{ ms}\$) to evade before physical impact.

### **4.6 Target Handoff & Next-Intruder Acquisition**

When the active intruder ($T_1$) exits through the door, the JetBot stops pursuit and searches for the next target ($T_2$) in $\mathcal{Q}$ using a **Map-Based Coverage Search**:

> 1. **Room map:** the occupancy grid saved in Phase 1 (section 4.1) provides the known-free floor, the obstacles, and the guarding position.  
> 2. **Coverage path:** from the map and an assumed effective detection radius $r_{\text{det}}$ (the distance within which a person crop can still be re-identified; placeholder 3.0 m, measured in Week 7), the base station plans a path with maximum floor coverage and minimum length. It picks viewpoints on known-free cells until at least 90 % of the known-free cells are within $r_{\text{det}}$ and line of sight of some viewpoint, orders them into a short tour, and connects them with obstacle-avoiding grid paths starting from the robot's current pose.  
> 3. **Follow & scan:** the JetBot follows the path and, at each viewpoint, pivots slowly in place for a full turn while the laptop runs detection on every frame.  
> 4. **Re-ID matching:** detected person crops are passed through OSNet. When the cosine distance matches $\vec{a}_{\text{target2}}$, the JetBot locks on and initiates the pursuit state.  
> 5. **Not found:** if the path ends without a match, $T_2$ is removed from $\mathcal{Q}$ (the event is logged with timestamp and snapshot) and the JetBot continues with the next target in $\mathcal{Q}$, or returns to standby if $\mathcal{Q}$ is empty.

*Optional prior:* when $T_2$ originally crosses the entrance threshold, the ESP32-CAM may log the horizontal drift of their bounding box over 2 s as a departure sector (Left / Center / Right). If available, the planner visits viewpoints on that side first; the search does not depend on it.

*Optional Extension:* If a third overhead camera is available, the base station continuously tracks $(X, Y)$ ground coordinates across the entire room, allowing the JetBot to drive directly toward $T_2$ without searching.

### **4.7 Optional Extension: On-Robot Inference (proposed 2026-10-16, to be agreed at the Week 2 meet-up on Sun 2026-10-18)**

The core system above keeps every neural model on the laptop (section 5). That stays the **default and the fallback**. This extension asks whether the Jetson Nano can run the time-critical models itself, so that the control loop no longer depends on the Wi-Fi link and the laptop becomes a companion application: start and stop, a live view of what the robot sees, and confirmation of intruders. Nothing in it is due before Week 3.

* **Evidence so far (2026-10-16, `docs/Edge Deployment.md`):** the eight models (YOLOv8n, YOLOv8n-pose, OSNet x0.25 and AIN, the XFeat backbone, SCRFD, MobileFaceNet, DINOv2) convert to TensorRT 7.1 FP16 engines built on the robot and match the ONNX Runtime outputs (cosine >= 0.9999 on the checked models). The pursuit model mix runs at 20 FPS on live frames with a capture-to-result p95 of about 51 ms (nobody in view), about 72 ms with the door pipeline running in its own thread, using about 2.1 GB RAM and 5-6 W of board power. DINOv2 (0.4 to 2.8 FPS) and XFeat stay on the laptop.
* **Stages, each behind a gate (Implementation Plan section 5):** A, a local obstacle layer (YOLOv8n) and the existing 300 ms watchdog on the robot, with the laptop path as fallback; B, the pursuit loop (YOLOv8n-pose, ByteTrack, OSNet lock, PD controller, hold) on the robot; C (stretch), the ESP32 door pipeline, the search and the network on the robot.
* **Rules:** the safety design does not change (dead-man switch, e-stop, speed cap, 300 ms watchdog); the on-robot code sends the same control packets to `robot_udp.py`; engines are built on the robot from ONNX (opset 11 or lower) and **every engine is checked against ONNX Runtime**, because TensorRT 7.1 can compute an operator wrongly without any error; a stage counts only when its acceptance rows (Implementation Plan section 4.3) pass, and the laptop mode remains available for the final demo.
* **Not a change to the deliverables:** the core system, the three phases and the final deliverables stay as written above.

## **5\. Network & Processing Architecture**

* **Network Host:** Windows 11 Mobile Hotspot configured with dual-band broadcast (a single-radio hotspot serves one band at a time and the video target p95 < 50 ms is missed on 2.4 GHz: Implementation Plan risk 16, an open team decision).  
  * **2.4 GHz Band:** Connects the ESP32-CAM: an MJPEG feed (VGA, 15 FPS) with an OV2640 module, or the UDP changed-tile stream (640x480, 14.4 FPS average) with the GC2145 boards we have, which is the frozen interface (2026-10-11).  
  * **5 GHz Band:** Connects the JetBot. Streams CSI video frames to the laptop via ZeroMQ (JPEG compressed, quality 60\) and receives motor control datagrams (\$v, \\omega\$) via non-blocking UDP packets.  
* **Compute Allocation:** The RTX 4050 processes both video streams, executes all neural models (YOLOv8, YOLOv8-pose, InsightFace, OSNet), and evaluates state machine transitions. The Jetson Nano is restricted to frame acquisition and low-level motor execution.
* **Optional on-robot inference (extension, section 4.7; proposed 2026-10-16):** the allocation above is the default. If the extension's gates pass, the Jetson also runs YOLOv8n (obstacles), YOLOv8n-pose and OSNet x0.25 (pursuit) through TensorRT FP16 on live frames, and the laptop keeps the ESP32 door pipeline, mapping, the state machine and the companion application. The control packets and the safety design are unchanged.

## **6\. 13-Week Implementation Roadmap**

The calendar was restructured on 2026-10-12 (team lead): 13 weeks from Mon 2026-10-05, everything a 10-15 page report and a demo video can honestly show done before the mid-term, evasion and the next-target search after it. Per-member tasks, interfaces, test tiers, acceptance criteria and gates: see `Implementation Plan.md` (section 5 is the source for this table).

| Week | Dates | Focus Area | Core Deliverables |
| :---- | :---- | :---- | :---- |
| **1** | Oct 5-11 | Networking & Telemetry | Configure the hotspot; ZeroMQ video uplink (\$\< 50\\text{ ms}\$ latency target); motor UDP commands; interfaces frozen; dataset D1 started. |
| **2** | Oct 12-18 | Pre-Scanning & Setup | YOLO ground-distance obstacle estimation; XFeat / DINOv2 entrance matching and sweet-spot selection; fisheye calibration, motion calibration and ArUco-assisted dead reckoning; occupancy-grid room map; live camera tilt (extra). |
| **3** | Oct 19-25 | HCI Deployment & Biometrics | Audio prompts and ESP32-CAM handshake; InsightFace whitelist and verification thresholds; state machine skeleton; dataset D2. |
| **4** | Oct 26-Nov 1 | Re-ID Handoff & Phase 1 end to end | OSNet appearance extraction, FIFO queue, sector logging; Phase 1 on the robot, Phase 2 on replayed data; report outline. |
| **5** | Nov 2-8 | Pursuit & Live Phase 2 | YOLOv8 + ByteTrack pursuit with PD control and obstacle override; hold-and-re-center detector; Phase 2 live at the door; dataset D3. |
| **6** | Nov 9-15 | Pursuit + Hold on the robot, Model Optimization | Pursuit and hold trials; FP16 / TensorRT optimization; report figures frozen and demo video shot (Sun Nov 15). |
| **7** | Nov 16-22 | Mid-Term Report & Buffer | No new features: draft Wed Nov 18, tag `midterm` Sat Nov 21. |
| **8** | Nov 23-29 | Mid-term submission & Threat Evasion | **Submit the Mid-Term Report Mon Nov 23.** Evasion override, YOLOv8-pose lunge detector; dataset D4. |
| **9** | Nov 30-Dec 6 | Evasion Validation & Search Building Blocks | Lunge detector tuned; evasion trials; effective detection radius; map-based coverage planner and path following. |
| **10** | Dec 7-13 | Next-Target Integration | Coverage search connected to the exit handoff (including dropping targets that are not found); full loop with two consecutive intruders; overhead-camera decision. |
| **11** | Dec 14-20 | Integration Buffer & Stress Tests | Contingency week: finish what slipped, stress-test edge cases. |
| **12** | Dec 21-27 | Validation, Freeze & Rehearsal | Code freeze Wed Dec 23, rehearsal Sat Dec 26, tag `final` Sun Dec 27. |
| **13** | Dec 28-Jan 3 | Final Submission & Defense | **Submit Mon Dec 28** (window Dec 28 to Jan 2): report, presentation and live robot demo on a day the team chooses; the code as a public repository link. |

**Milestones:** the **Mid-Term Report is due Mon 2026-11-23** (10-15 pages, includes the code, with an optional demo video; internal draft Wed Nov 18; plan in `Mid-Term Report Plan.md`). This replaces the earlier "15-20 page report in Week 4". The **final submission** window is 2026-12-28 to 2027-01-02, target Mon Dec 28.

*Extension schedule (proposed, Implementation Plan section 5): agreed or rejected at the Week 2 meet-up (Sun 2026-10-18); work from Week 3 with gates on the Sundays of Weeks 3, 5, 8 and 9. It does not change the core deliverables above.*
