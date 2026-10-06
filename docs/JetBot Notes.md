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
| Wi-Fi | **Realtek RTL8822CE** (PCI 10ec:c822, vendor driver `rtl8822ce`; the kit's parts list says Intel AC8265, so the installed card differs from the BOM) on `wlan0`. Driver default is `rtw_power_mgnt=2` (maximum power saving). **Power save is ON by default and ruins the link** (measured 2026-10-04: with it ON the video lost 48 % of frames with 4 s typical latency; with `sudo iw dev wlan0 set power_save off` it lost 0 % at 22 ms typical, p95 65 ms; full-size pings went from 15 % loss to 0 %). **Now permanent (2026-10-06):** `/etc/modprobe.d/8822ce-sentry.conf` sets `rtw_power_mgnt=0 rtw_ips_mode=0`; verified after a clean reboot (module parameters 0/0, driver reports `NO IPS` / `NO LPS`, video p95 21 ms with no manual override). **`iw dev wlan0 get power_save` keeps saying `on` and `iwconfig` says `off` regardless; neither is reliable. Check `/proc/net/rtl88x2ce/wlan0/ps_info` instead** (or run `python -m tools.jetbot_status <ip>`). 2.4 GHz and 5 GHz behaved the same; the band was not the problem. Signal was -53 to -71 dBm at short range. **Antennas:** per-chain readings from `/proc/net/rtl88x2ce/wlan0/rx_signal` (2026-10-04, one antenna fitted outside the metal chassis): chain 0 -68 dBm / SNR 20 dB, chain 1 -55 dBm / SNR 29-32 dB, a steady 13 dB imbalance. **Confirmed 2026-10-04 by DoanQuocKien: antenna 0 is missing** (chain 0 is the weak one). A bare port still read -68 dBm / SNR 20 dB, so a 13 dB gap is what an empty port looks like here. Replacement: one 2.4G/5G dual-band SMA antenna + IPEX-to-SMA pigtail, see `docs/Hardware.md`; professor to be asked first. To make power save off permanent: `options rtl8822ce rtw_power_mgnt=0 rtw_ips_mode=0` in `/etc/modprobe.d/` (not applied yet). |
| Gamepad / audio | No gamepad receiver or USB speaker plugged in at test time (only `gpio-keys`, HDMI audio and the on-board codec). Plug the gamepad receiver in to learn its device path for the e-stop. |
| **Disk** | Root is **24 GB, 94 % full (1.6 GB free)**. The card has **36 GB of unallocated space directly after the root partition**, so it can be grown in place (`parted resizepart` + `resize2fs`). Not done yet; needed before recording data or installing anything. |

**Best network setup so far (2026-10-06, `reports/DoanQuocKien/week-01/link_test_2026-10-04.txt` section J):** the *laptop's own* Windows hotspot, robot about 1 m away at -45 dBm, both antenna chains strong (-42/-47 dBm), Wi-Fi power save OFF. The hotspot ran on 5 GHz channel 149, the same channel as the laptop's own school Wi-Fi connection (non-DFS), so one radio could serve both. Result: synthetic video 0 % loss, **p95 22 ms, max 63 ms**; UDP 6 Mbit/s 0 % loss; TCP 16.8 Mbit/s with silences under 190 ms; no hotspot restarts in 3 minutes. The earlier laptop-hotspot failures happened with the hotspot on 2.4 GHz while the laptop client sat on a 5 GHz DFS channel (60 / 112), with power save on and an antenna missing. Conditions to reproduce: hotspot band Auto or 5 GHz, laptop client on a non-DFS channel, power save off, robot close, both antennas fitted.

## Open questions

- ~~Which `jetbot` version and motor driver does the kit's SD image actually use?~~ Answered above: jetbot 0.4.3 in Docker, motor driver at 0x60.
- What does upstream `zmq_camera.py` do? It may already be a ZeroMQ camera client we can learn from.
- Does `nvarguscamerasrc` give us 640x480 at 20+ fps on this image, or must we capture larger and downscale?

## Battery (check it constantly)

- Read it with `python -m tools.jetbot_status <robot-ip>` at the start and end of every session and between long tests (it also shows Wi-Fi, both antenna paths, the driver's power-save state and the containers). Underlying read: `sudo i2cget -y 1 0x41 0x02 w`, byte-swapped, bits 15..3 at 4 mV per step (INA219).
- Assumes that INA219 measures the 3S Li-ion pack (12.6 V full). Our rule of thumb: **>= 11.1 V OK, 10.5-11.1 V LOW (charge soon), < 10.5 V CRITICAL (stop and charge)**. The percentage in the tool is only a rough linear guess between 9.9 and 12.6 V.
- Readings so far: 12.0 V on 2026-10-04 (about 80 %), 11.9-11.95 V on 2026-10-06 after about two hours of tests.
- Never run motor tests below the LOW threshold: under load the voltage sags and the Jetson can brown out and corrupt the SD card.

## Return checklist (the robot is school property; undo what we changed before handing it back)

| Change we made | How to undo |
| :-- | :-- |
| Wi-Fi profile `DoanQuocKien` added on the SD card (`/etc/NetworkManager/system-connections/DoanQuocKien`, contains the hotspot password) | `sudo rm` that file. The original `Deco_One` profiles were left untouched. A backup of the original folder is in `C:\Users\admin\jetbot_card_backup` on the laptop |
| Our code in `/home/jetbot/sentry/` (some `__pycache__` folders are owned by root) | `sudo rm -rf /home/jetbot/sentry` |
| Wi-Fi power save: permanent fix file `/etc/modprobe.d/8822ce-sentry.conf` (2026-10-06) | `sudo rm /etc/modprobe.d/8822ce-sentry.conf` and reboot restores the driver default |
| Docker containers `jetbot_jupyter` / `jetbot_display` | Not modified; our scripts only ran inside the jupyter container and are stopped |
| Antenna 0 missing (not caused by us as far as we know) | Tell the professor; replacement is cheap |
| On the laptop: usbipd-win installed and the card reader shared (busid 1-3) | Optional: `usbipd unbind --busid 1-3`, uninstall usbipd-win |
| SD card filesystem had minor inconsistencies from power-offs by the switch | Prefer a clean shutdown (`sudo shutdown -h now` over SSH) before cutting power |
