# Hardware: decisions and shopping list

The JetBot kit (Jetson Nano 4GB, CSI camera, chassis, motors, board, Wi-Fi card, 18650 batteries, charger, gamepad) is already supplied.
Everything below is what the spec lists as "external", plus gaps we found. **Costs are rough guesses from general knowledge, not quotes; check local shops.**
Spec section 2 is the source for the original list; where this file disagrees with it, this file is the newer decision.

## 0. Budget version (use this one unless money is not a problem)

**Buy about $12-20 worth (my estimate); everything else is free or borrowed.** Sections 1-3 below are the full-price reference.

| Item | Budget choice | Cost | What you give up |
| :-- | :-- | :-: | :-- |
| ESP32-CAM + MB base | **Already bought; kouun-rokku holds it** and does the W1 firmware work. Nothing to buy. | $0 | No spare. If it dies, buy another locally ($8-10, 1-2 days); a W1-W2 failure costs little. |
| ESP32 power | Phone charger (5 V, 1 A or more) + a short, thick cable you own | $0 | Possible reboot loops on a weak charger or thin cable; if so, try another charger before buying anything |
| Camera stand | Tape it to a shelf, or use a stack of books and double-sided tape | $0 | Less adjustable |
| Speaker | **None** (dropped 2026-10-26): the laptop plays the audio prompts and alarm through its own speakers | $0 | The sound comes from the laptop, not the robot; keep the laptop volume up and within earshot in the room |
| Checkerboard backing | Glue the print onto a **flat rigid board you already own** (MDF offcut, cutting board, spare tile). Check flatness with a ruler | $0 | Warped backing ruins the calibration, so reject anything curved. Do not use thin cardboard |
| Printing | Matte or plain paper at a print shop: the checkerboard + **only the 150 mm ArUco set** (7 pages) | $1-2 | The 10 cm set is skipped. After printing, measure a marker and set `aruco_marker_m = 0.15` in `config.toml` |
| Tape measure | Borrow one (5 m) or buy | $0-2 | |
| Lunge prop | A rolled towel or pillow on a cardboard tube | $0 | |
| Cables, ties, tape | Use what you have; label which USB cables carry data | $0 | |
| Down-tilt wedge | Folded foam or cardboard, test both ways in W2 | $0 | |
| Network | **Try the Windows hotspot on 2.4 GHz for both ESP32 and JetBot first.** If it fails, use a phone as a hotspot (check that clients can ping each other). Buy a router only if both fail the 50 ms test | $0 | Single band for everything; video needs only ~5 Mbps so this is fine unless the room is crowded with Wi-Fi |
| Spare batteries | **Do not buy.** Charge between sessions and plan around the measured runtime | $0 | Shorter test sessions; revisit if runtime is under 60 min |
| IMU, overhead camera | **Do not buy** | $0 | Same gates as section 2; the IMU costs only $2-3 if the W2 test fails |

**Still worth paying for even on a budget:** the ESP32-CAM + MB base (the project cannot work without it) . Everything else has a free substitute that I judge low risk.

**Order of upgrades if something fails** (cheapest first): another phone charger or cable, then a second ESP32-CAM ($8-10), then the router ($20-30), then spare batteries ($12-18).

## 1. Buy now (required)

| # | Item | Qty | Needed by | Why / decision |
| :-- | :-- | :-: | :-- | :-- |
| 1 | **ESP32-CAM, AI-Thinker, OV2640, PCB antenna** | 2 | Mon Oct 5 (W1) | One for kouun-rokku to write firmware on without the robot (W1 task), one for the real setup. They also brown out and die, so a spare is cheap insurance. Skip the external-antenna variant: it needs soldering and the room is small. |
| 2 | **ESP32-CAM-MB programmer base (micro-USB, CH340)** | 2 | Oct 5 | **Replaces the spec's FTDI adapter**: plugs onto the board, no jumper wires, no IO0-to-GND juggling. If the shop only sells bare boards, fall back to a 3.3 V FTDI adapter (not 5 V) + 4 female-female jumpers. |
| 3 | **Power for the ESP32-CAM**: 5 V 2 A USB wall adapter + 2 m micro-USB data cable **or** a power bank | 1 | W3 | It needs a stable 5 V and ~0.5 A peaks; weak supplies cause reboot loops. Prefer a wall adapter if there is an outlet near the door. If a power bank, pick one without auto-off at low current. You probably own one already. |
| 4 | **Mini tripod or gooseneck phone clamp** | 1 | W3 | The camera must sit about face height (1.4-1.6 m) facing the door. Against a custom enclosure: not worth team time. |
| 5 | ~~USB speaker with its own USB audio~~ **Not bought (2026-10-26, cost)** | 0 | - | Audio prompts and alarm play on the laptop instead (no hardware). |
| 6 | **5 mm foam board (A4 or A3) + spray adhesive or double-sided tape** | 1 | **Oct 9** | The checkerboard must be perfectly flat and rigid or the fisheye calibration is wrong. D1 (end of W1) needs 30+ checkerboard photos. |
| 7 | **Printing on matte paper**: `assets/print/checkerboard_9x6_25mm.pdf`, `aruco_4x4_50_ids0-5_100mm.pdf`, `aruco_4x4_50_ids0-5_150mm.pdf` | 1 each | Oct 9 | Print at 100 % ("actual size", never "fit to page"), matte (glossy paper reflects). Measure the 100 mm scale bar and the printed square/marker, then update `config.toml`. The 150 mm set is new: see section 4. |
| 8 | **5 m tape measure + masking tape** | 1 each | Oct 5 | Ground truth for obstacle distances (D1), motion calibration, floor marks. |
| 9 | **Soft foam "lunge" prop**: pool noodle or pillow on a stick | 1 | W8 | For the dataset of padded lunges (D4). Nobody is ever struck. |
| 10 | **Micro-USB data cables**, cable ties, velcro / double-sided tape | 2 / pack | W1 | Many cheap cables are charge-only; label the data ones. |

Rough total for the table: about **$40-60** (my estimate).

**Borrow, don't buy:** an HDMI monitor + cable and a USB keyboard for the first Jetson login (Wi-Fi setup); a phone that records 120/240 fps video for measuring evasion reaction time (W8). The kit's gamepad is the hardware e-stop.

## 2. Conditional: buy only if the gate triggers

| Item | Gate (decide on this date, on this measurement) | If triggered | Rough cost |
| :-- | :-- | :-- | :-- |
| **Dual-band travel/mini router** | **Mon Oct 5 hotspot test.** Windows Mobile Hotspot (as far as I know) serves one band at a time and shares the laptop's own Wi-Fi radio. If it cannot serve ESP32 (2.4 GHz) and JetBot together, or ping p95 > 50 ms (docs/Setup.md, robot_checks section 6) | Buy locally the same day. A router gives both bands at once, fixed IPs (DHCP reservation) and does not load the laptop radio | $20-30 |
| **Spare 18650 set (3 protected cells, genuine brand)** | **End of W1**: measured runtime < 60 min with Wi-Fi + camera streaming (use the course battery script) | Buy a second set and swap during test sessions. No unbranded cells | $12-18 |
| **Wi-Fi antenna + IPEX-to-SMA pigtail (only if the professor confirms one was never supplied or says to replace it)** | **Now (Oct 4).** The robot's Wi-Fi card has two antenna ports but one antenna fitted; per-antenna readings show a steady 13 dB gap (see `JetBot Notes.md`). Waveshare's package for this card is "card x1, IPEX to SMA cable ~20 cm x2, antenna x2" | Ask the professor first (the lab may have a spare). Otherwise buy **one 2.4G/5G dual-band SMA antenna + one IPEX (U.FL) to SMA ~20 cm pigtail**, matching the ones already fitted (same SMA vs RP-SMA, same IPEX size). Verify by comparing with the fitted pigtail before buying | about $2-5 (my estimate; Waveshare sells the whole card with both antennas for $5.99) |
| **MPU6050 IMU** | **End of W2**: dead reckoning without ArUco misses the plan's threshold (> 40 cm error after 3 m, or visible heading drift) | Buy (1-2 days locally), wire to the Jetson I2C bus, add yaw to localization. **Against buying it now**: we chose ArUco + dead reckoning, and it adds wiring and code | $2-3 |
| **15° CSI down-tilt wedge** | **W2**, decide with data from robot_checks 3b (field-of-view test) | Make it (3D print at the lab, or folded foam/cardboard): near-free. It helps see the floor and obstacles but cuts the view of a person's upper body at 1.2 m, so choose by testing both | ~$0 |
| **Overhead room camera** | **Sun Dec 13 (end of W10; was Wed Nov 18, W7, before the 2026-10-12 restructure)**: only if the coverage search finds the target in < 4/5 trials **and** at least a week remains (W11 is the buffer) | See section 3 | $25-40 + $8-12 |

## 3. Decided against

| Item | Decision | Reason |
| :-- | :-- | :-- |
| **Overhead camera (now)** | **Against** | Spec calls it an optional extension. It adds a third video stream, a ground-plane calibration, more bandwidth and GPU load, for a 3-person team with one robot and about 5 weeks between the mid-term and the final freeze. The map-based coverage search replaces its job. If the W10 gate triggers: 1080p USB webcam with >= 90° field of view, 5 m active USB extension, tripod |
| GPIO buzzer | Against | Spoken prompts chosen |
| DIY lithium cell + 5 V boost circuit for the ESP32-CAM | Against | Brown-outs and safety risk; a USB supply is simpler |
| Custom enclosure / 3D-printed case for ESP32 | Against | Tripod clamp is enough |
| Wheel encoders, LiDAR, ultrasonic sensors, depth camera | Against | Spec is vision-only; each adds an integration we have no time for. ArUco covers drift |
| New lens/camera for the JetBot | Against | Keep the IMX219-160; calibrate the fisheye |
| New Jetson / Raspberry Pi / extra GPU | Against | The RTX 4050 handles the model budget (Week 5 profile checks it) |
| FTDI adapter (spec) | Replaced by item 2 | MB base is easier |

## 4. Two risks the hardware choices do not fix

- **Face size on the ESP32-CAM.** A typical OV2640 lens has about 65° horizontal view (my assumption). At 640 px width, a face is roughly 30-32 px wide at 2.5 m and 27 px at 3 m, small for reliable recognition. People get closer as they walk in, so it may work, but **measure it in Week 3** (D2). Fallbacks: SVGA resolution if the frame rate allows, place the camera closer to where people stand, recognise on the nearest frames only. Not a purchase.
- **ArUco size.** The JetBot camera is only about 10 cm off the floor. With a guessed focal length of 350 px, a 10 cm marker is only about 17 px wide at 2 m, too small to read; it works to roughly 1.5 m. That is why the 15 cm set is on the list. Place markers on small stands or low on walls, at camera height. Check the real range in Week 2.
