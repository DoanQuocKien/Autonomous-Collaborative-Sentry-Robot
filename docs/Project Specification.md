# **Autonomous Collaborative Sentry Robot: Project Specification**

**Course:** CS532 – Computer Vision in Human-Computer Interaction  
**Institution:** University of Information Technology (UIT – VNU-HCM)  
**Project Scope:** 8-Week Capstone Implementation

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
  * ESP32-CAM module (OV2640).  
  * 5V power source (lithium cell with 5V boost circuit or compact USB power bank).  
  * FTDI USB-to-TTL adapter (for initial firmware flashing via Arduino IDE).  
  * Minimal enclosure or stand to position the module on the floor or a shelf.  
* **Audio Feedback:** USB mini speaker connected to the Jetson Nano, playing pre-generated WAV prompts (offline TTS, rendered on the laptop) for setup prompts and deterrent alarms.  
* **Localization Markers:** Cardstock ArUco markers ($10 \times 10\text{ cm}$) as position anchors (the kit has no encoders or IMU), plus a printed checkerboard for one-time fisheye camera calibration.

### **Optional External Hardware**

* **Overhead Room Camera:** \$1080\\text{p}\$ wide-angle USB webcam or RTSP IP camera placed high in the room to maintain continuous 2D coordinates of all occupants.  
* **CSI Camera Down-Tilt Mount:** \$15^\\circ\$ downward angle bracket for the JetBot to improve visibility of feet and floor obstacles at close range.  

## **3\. System Inputs**

> 1. **Entrance Reference Image (\$I\_{\\text{ref}}\$):** A static color photograph of the target doorway.  
> 2. **Occupant Whitelist (\$\\mathcal{F}\_{\\text{whitelist}}\$):** A set of 3 to 5 reference photos per authorized room occupant, stored as pre-calculated 512-dimensional facial feature vectors.

## **4\. Algorithmic Pipeline & Functional Logic**

\[Phase 1: Setup\]  
Reference Photo \+ Floor Exploration   
  \-\> ORB Feature Match   
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

* While moving, the system extracts ORB features from the onboard video feed and matches them against \$I\_{\\text{ref}}\$.  
* Once the matched keypoints exceed a set threshold, the entrance direction vector is recorded.  
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

## **5\. Network & Processing Architecture**

* **Network Host:** Windows 11 Mobile Hotspot configured with dual-band broadcast.  
  * **2.4 GHz Band:** Connects the ESP32-CAM. Streams an MJPEG feed (VGA resolution at \$15\\text{ FPS}\$).  
  * **5 GHz Band:** Connects the JetBot. Streams CSI video frames to the laptop via ZeroMQ (JPEG compressed, quality 60\) and receives motor control datagrams (\$v, \\omega\$) via non-blocking UDP packets.  
* **Compute Allocation:** The RTX 4050 processes both video streams, executes all neural models (YOLOv8, YOLOv8-pose, InsightFace, OSNet), and evaluates state machine transitions. The Jetson Nano is restricted to frame acquisition and low-level motor execution.

## **6\. 8-Week Implementation Roadmap**

Per-member tasks, interfaces, test tiers and acceptance criteria: see `Implementation Plan.md`.

| Week | Focus Area | Core Deliverables |
| :---- | :---- | :---- |
| **1** | Networking & Telemetry | Configure dual-band hotspot; establish ZeroMQ video uplink (\$\< 50\\text{ ms}\$ latency); verify motor UDP commands. |
| **2** | Pre-Scanning & Setup | Implement YOLO ground-distance obstacle estimation; write ORB entrance matching and sweet-spot selection logic; fisheye calibration and ArUco-assisted dead-reckoning pose; occupancy-grid room map saved at the end of Phase 1. |
| **3** | HCI Deployment & Biometrics | Implement audio prompts and ESP32-CAM connection handshake; build InsightFace whitelist and verification thresholds. |
| **4** | Re-ID Handoff & Mid-Term Report | Implement OSNet appearance extraction and FIFO queueing; write and submit the 15–20 page Mid-Term Technical Report. |  
| **5** | Pursuit & Obstacle Handling | Implement YOLOv8 \+ ByteTrack pursuit controller; integrate obstacle repulsion; build the stationary hold-and-re-center behavior. |  
| **6** | Threat Evasion | Deploy YOLOv8-pose; calibrate bounding box expansion and ankle kinematic triggers; test motor dodge override. |  
| **7** | Next-Target Integration | Implement map-based coverage search and connect it to the exit handoff (including dropping targets that are not found); test full loop with two consecutive intruders. |  
| **8** | Validation & Defense | Stress-test edge cases; record demonstration footage; prepare project presentation and repository. |

**Milestone:** Submit 15–20 page Mid-Term Technical Report (Week 4).