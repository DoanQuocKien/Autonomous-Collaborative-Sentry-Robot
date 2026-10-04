# JetBot Notes

How the JetBot platform works, read from NVIDIA's source (`github.com/NVIDIA-AI-IOT/jetbot`, master) on 2026-10-03.
**Not yet verified on our kit.** Our kit is the Waveshare JetBot AI Kit, whose SD image may ship a different `jetbot` version than upstream master (see "Verify on the robot").

## Software and access

| Item | Value |
| :-- | :-- |
| OS | Ubuntu 18.04, JetPack 4.5 (Jetson Nano 4GB B01) |
| Python on Jetson | **3.6**, so no `dataclasses`, no walrus, no `X \| Y` types; `jetson/` code must stay 3.6-compatible |
| Login | `jetbot` / `jetbot` |
| Remote | Jupyter at `http://<ip>:8888`, password `jetbot` |
| IP discovery | shown on the OLED screen after boot |
| Wi-Fi | `sudo nmcli device wifi connect <SSID> password <PW>`; auto-reconnects at boot |
| First boot | JetPack 4.5 images need one boot of plain JetPack 4.5 for one-time device setup |

## Motors (`jetbot/robot.py`, `motor.py`)

- `Robot.set_motors(left, right)`, values in **[-1, 1]**. Shortcuts: `forward(s)`, `backward(s)`, `left(s)` (left motor -s, right motor +s, a left turn), `right(s)`, `stop()`.
- `Robot` is a singleton; each `Motor.value` write goes straight to an I2C motor driver (Adafruit MotorHAT, I2C address 0x60 = 96).
- Per-motor calibration traits: `alpha` (gain, default 1.0) and `beta` (offset, default 0.0). Mapped speed = `int(255 * (alpha*value + beta))`, clipped to 0-255.
- **No watchdog**: if the program dies the motors keep their last value. `atexit` releases them only on a clean exit.
- The upstream `Heartbeat` class is a Jupyter-widget (browser) heartbeat, so it is **not** usable for our safety stop.
- **No encoders or IMU**: speed is open-loop PWM, so it varies with battery voltage, and low values fall in a dead zone where the wheels do not turn.

## Camera (`jetbot/camera/`)

- `Camera` = `OpenCvGstCamera` by default (or `ZmqCamera` if `JETBOT_DEFAULT_CAMERA=zmq_camera`; not read yet).
- Pipeline: `nvarguscamerasrc sensor-mode=3 ... ! nvvidconv ! BGRx ! videoconvert ! appsink`; frames are BGR uint8 in `.value`, updated by a capture thread.
- Defaults: output 224x224, capture 816x616, 30 fps. **Too small for us**; we set our own resolution (target 640x480).
- Fisheye field of view depends on the sensor mode and crop, so **calibration must use exactly the mode we run in**.
- `jetbot.image.bgr8_to_jpeg(value, quality=75)` is `cv2.imencode('.jpg', ...)`; we call it with quality 60.

## Decisions for our code (apply in `jetson/robot_udp.py`)

1. **Command units.** The laptop sends normalized `v, w` in [-1, 1]. The Jetson converts: `left = v - K*w`, `right = v + K*w`, with `K` in `config.toml` (starts at 1.0, tuned in motion calibration).
2. **Saturation: rescale, never clip.** If `max(|left|, |right|) > 1`, divide both by that max. This keeps the turn ratio. Example: the spec's evasion `v=-1.0, w=+0.8` gives (-1.8, -0.2), which becomes (-1.0, -0.11): a reverse arc rather than a reverse spin. Spec section 4.5 does not say which is intended; confirm during the Week 6 evasion tests.
3. **Sign convention.** Positive `w` = turn **left** (counter-clockwise from above), matching `Robot.left()`. Verify on the robot, because the MotorHAT code maps negative values to `FORWARD`, so wiring may invert it; if so, fix it with the sign of `alpha`, not in the laptop code.
4. **Dead zone.** Measure the smallest |value| that moves each wheel (Week 2 motion calibration) and store it as `min_pwm`; below it send 0.
5. **Watchdog.** `robot_udp.py` stops both motors if no valid packet arrives for 300 ms, and also on any exception (`try/finally`).
6. **Battery.** Log battery voltage with the course's battery script (see `reference_links.md`) with every calibration run, since speed depends on it.

## Verify on the robot (Week 1, before writing code)

```
pip list | grep -i jetbot          # which jetbot version the image ships
i2cdetect -y -r 1                  # expect 0x60 (Waveshare/Adafruit); 0x5d (93) means a SparkFun board
python3 --version                  # expect 3.6.x
nvgstcapture-1.0                   # or a short nvarguscamerasrc test: does the camera work, which sensor modes exist
```
Record the outputs in `reports/DoanQuocKien/week-01/`.

## Verified on our robot (2026-10-04; raw output in `reports/DoanQuocKien/week-01/robot_remote_checks.txt`)

| Item | Result |
| :-- | :-- |
| Board / OS | Jetson Nano Developer Kit, L4T R32.5.0 (JetPack 4.5), Ubuntu 18.04, hostname `nano-4gb-jp45`, Python 3.6.9 |
| Where `jetbot` lives | **Inside Docker, not the host.** Containers `jetbot_jupyter` (`jetbot/jetbot:jupyter-0.4.3-32.5.0`) and `jetbot_display` (OLED) run with `--restart always`. Host Python has no `jetbot` and no `zmq`. |
| Jupyter container | `net=host`, privileged, mounts `/dev/bus/usb`, `/tmp/argus_socket` (camera) and host `/home/jetbot` as `/workspace`. Inside: Python 3.6.9, jetbot 0.4.3, pyzmq 21.0.1, OpenCV 4.1.1, numpy 1.19.4. |
| **So: how to run our scripts** | Copy `common/`, `jetson/` (and later `calib/`, `assets/audio/`) to `/home/jetbot/sentry/` on the host; run inside the container, e.g. `docker exec -w /workspace/sentry jetbot_jupyter python3 jetson/robot_udp.py --dry-run`. Host networking means UDP 5556 / ZMQ 5555 are on the Jetson's own IP. Anything that opens the Robot in a Jupyter notebook at the same time will conflict. |
| I2C devices | `0x3c` OLED, `0x41` INA219 (battery monitor), `0x60` motor driver (Waveshare/Adafruit, as expected), `0x70` all-call. |
| Battery | INA219 register read gave about **12.0 V** (3S pack, roughly 80 % charged). Assumes the 0x41 INA219 measures the pack. |
| Camera | `/dev/video0` present, `nvargus-daemon` active. Host OpenCV 4.1.1 has GStreamer 1.14.5 (YES). Sensor modes not yet read. |
| Wi-Fi | AC8265 on `wlan0`, joined 2.4 GHz channel 1, -67 dBm, 174 Mbit/s. **Power save is ON** (adds latency spikes; turn off with `sudo iw dev wlan0 set power_save off`, not yet persistent). |
| Gamepad / audio | No gamepad receiver or USB speaker plugged in at test time (only `gpio-keys`, HDMI audio and the on-board codec). Plug the gamepad receiver in to learn its device path for the e-stop. |
| **Disk** | Root is **24 GB, 94 % full (1.6 GB free)**. The card has **36 GB of unallocated space directly after the root partition**, so it can be grown in place (`parted resizepart` + `resize2fs`). Not done yet; needed before recording data or installing anything. |

## Open questions

- ~~Which `jetbot` version and motor driver does the kit's SD image actually use?~~ Answered above: jetbot 0.4.3 in Docker, motor driver at 0x60.
- What does upstream `zmq_camera.py` do? It may already be a ZeroMQ camera client we can learn from.
- Does `nvarguscamerasrc` give us 640x480 at 20+ fps on this image, or must we capture larger and downscale?
