# Robot checks (Week 1) – DoanQuocKien

Fill the result blocks as you go and commit this file. Safe-testing rules: **wheels off the ground** until the section says otherwise, `--max-speed` low, gamepad in hand.
Reasons for each check are in `docs/JetBot Notes.md`; install steps are in `docs/Setup.md` (section C).

## 0. First connection (course procedure, jetbot.org docs agree)
Needs: the kit's own SD card in the Jetson (do not wipe it), HDMI monitor + cable, USB keyboard. No micro-USB cable needed.
1. Insert the card, power on, wait for boot. Log in on the monitor: `jetbot` / `jetbot`.
2. Join Wi-Fi (the first test can use the same home Wi-Fi the laptop is on; the hotspot question only matters when the ESP32 joins in W3):
   ```
   nmcli device                                   # Wi-Fi interface name, probably wlan0
   sudo nmcli device wifi connect "<SSID>" password "<PASSWORD>"
   hostname -I                                    # IP; after this the OLED screen also shows it
   ```
3. From the laptop: `ping <jetson-ip>`, then `ssh jetbot@<jetson-ip>`. Jupyter is at `http://<jetson-ip>:8888` (password `jetbot`).
4. If ping fails but the Jetson has an IP, the router may isolate Wi-Fi clients: use a phone hotspot (2.4 GHz) instead.
5. Optional: back up the kit's card first to a spare one (any imaging tool), so a mistake is recoverable.
```
(paste: interface, IP, ping result, band from `iw dev wlan0 link`)
```

## 1. What is on the robot
```
cat /etc/nv_tegra_release ; python3 --version
pip list 2>/dev/null | grep -i -E "jetbot|zmq|numpy|opencv|traitlets"
python3 -c "import jetbot; print(jetbot.__file__)"
```
Result:
```
(paste)
```
Question to answer: is `jetbot` inside the system Python or only in a Docker container? (If Docker, scripts must run inside it.)

## 2. Motor driver
```
sudo i2cdetect -y -r 1
```
Expect `60` (Adafruit/Waveshare); `5d` would mean a SparkFun board.
```
(paste)
```

## 3. Camera
```
gst-launch-1.0 nvarguscamerasrc sensor-mode=3 num-buffers=60 ! 'video/x-raw(memory:NVMM),width=1640,height=1232,framerate=30/1' ! nvvidconv ! fakesink
python3 -c "import cv2; print(cv2.getBuildInformation())" | grep -i gstreamer
```
The first command prints the available sensor modes; paste them. Is mode 3 really 1640x1232@30 on this module?
```
(paste)
```
Then: `python3 jetson/camera_pub.py` runs without "failed to open"? Measured FPS: ____

## 3b. Fisheye field of view
Hold a ruler at known distances in front of the camera and note the visible width at 0.5 m: ______ (needed to sanity-check calibration later).

## 4. Motors (wheels in the air)
Run `python3 jetson/robot_udp.py --max-speed 0.3` and send from the laptop: `python -m tools.send_cmd --ip <jetbot-ip> --v 0.3 --seconds 2`.

| Command | Expected | Observed (each wheel: forward/back/still) |
| :-- | :-- | :-- |
| `--v 0.3 --w 0` | both wheels forward | |
| `--v 0 --w 0.3` | **left turn**: left wheel back, right wheel forward | |
| `--v -0.3 --w 0` | both back | |

If a wheel direction is wrong, flip the sign of that motor's `alpha` in the jetbot config; do not change laptop code.

Dead zone: send `--v` = 0.05, 0.10, 0.15, … until each wheel starts to turn. Left starts at ____, right starts at ____. (Becomes `min_pwm` in `calib/motion.json`.) Battery voltage during this test: ____

## 5. Safety
- Watchdog: `python -m tools.send_cmd --ip <jetbot-ip> --v 0.3 --seconds 2 --silent-end`. Motors stop within ~0.35 s of the last packet? ____
- Unplug the laptop network mid-command: motors stop? ____
- Kill `robot_udp.py` with Ctrl-C while wheels spin: motors stop? ____
- **Not done yet:** gamepad hardware e-stop (needs the gamepad's device path from `ls /dev/input/`): ____

## 6. Network
```
iw dev wlan0 link          # frequency 5xxx MHz = 5 GHz band
ping -c 20 <laptop-ip>
```
```
(paste: frequency, packet loss %, avg/max ms)
```

## 7. Whole link
1. Laptop: hotspot on. Jetson: `python3 jetson/robot_udp.py --allow-ip <laptop-ip> --max-speed 0.3`.
2. Laptop: `python -m tools.send_cmd ...` moves the wheels as in section 4.
3. Jetson: `python3 jetson/camera_pub.py --source synthetic`; HuynhNguyenHoaiLoc's receiver (Week 1) reads it.

Open issues found:
-
