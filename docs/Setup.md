# Setup

Three machines, three install paths. Do the one for your machine, then run the check at the end of it.
Versions below are the ones we actually verified (Windows 11, RTX 4050, driver 581, 2026-10-04).

| Machine | Who | Path |
| :-- | :-- | :-- |
| Laptop with NVIDIA GPU | DoanQuocKien, HuynhNguyenHoaiLoc | [A](#a-gpu-laptop) |
| Laptop without GPU | kouun-rokku | [B](#b-cpu-only-laptop) |
| JetBot (Jetson Nano) | DoanQuocKien | [C](#c-jetbot) |

## A. GPU laptop

Needs Miniconda and an up-to-date NVIDIA driver (CUDA 12.8 wheels need a driver that supports CUDA 12.8; check `nvidia-smi`).

```powershell
conda create -n sentry python=3.12 -y
conda activate sentry

# 1. torch FIRST, from the CUDA index. PyPI's Windows torch is CPU-only.
pip install torch==2.9.1 torchvision==0.24.1 --index-url https://download.pytorch.org/whl/cu128

# 2. everything else
pip install -r requirements.txt

# 3. step 2 can pull in plain onnxruntime, which hides the GPU one. Always run this:
pip uninstall -y onnxruntime onnxruntime-gpu
pip install onnxruntime-gpu==1.23.2

# 4. verify
python tools/check_env.py
pytest
```
`check_env.py` must end with `ALL GOOD`. DoanQuocKien's env was made differently (cloned from an existing torch env); the result is the same.

## B. CPU-only laptop

```powershell
conda create -n sentry python=3.12 -y
conda activate sentry
pip install torch==2.9.1 torchvision==0.24.1 --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements-cpu.txt
python tools/check_env.py --cpu-ok
pytest -m "not gpu and not hil"
```
You can do everything except GPU speed measurements. The `gpu` tests skip themselves.

## C. JetBot

Ubuntu 18.04 / JetPack 4.5 / **Python 3.6**. Not verified on the device yet: record what you actually see in `reports/DoanQuocKien/week-01/robot_checks.md`.

```bash
sudo apt update && sudo apt install -y python3-pip libzmq3-dev alsa-utils
pip3 install -r jetson/requirements.txt

# OpenCV and numpy must be the JetPack ones; the camera needs GStreamer support:
python3 -c "import cv2; print(cv2.__version__)"
python3 -c "import cv2; print(cv2.getBuildInformation())" | grep -i gstreamer     # expect: YES
```
On our robot the `jetbot` library, pyzmq 21, OpenCV and numpy are **inside the `jetbot_jupyter` Docker container**, not the host (verified 2026-10-04, see `docs/JetBot Notes.md`), so the pip step above is not needed. Deploy by copying `common/`, `jetson/`, `calib/` (once it exists) and `assets/audio/` (WAV clips) to `/home/jetbot/sentry/` on the robot, e.g. `scp -r common jetson jetbot@<ip>:~/sentry/`. The container sees that folder as `/workspace/sentry`; run scripts there with `docker exec`, e.g. `docker exec -w /workspace/sentry jetbot_jupyter python3 jetson/robot_udp.py --dry-run`.

First runs, wheels off the ground, low speed (default `--max-speed 0.5`):

```bash
python3 jetson/robot_udp.py --dry-run             # prints motor values, touches no hardware
python3 jetson/robot_udp.py --allow-ip <laptop-ip> --max-speed 0.3
python3 jetson/camera_pub.py --source synthetic   # test pattern, same wire format as the camera
python3 jetson/camera_pub.py                      # real camera
```
**Safety interlock:** `robot_udp.py` refuses to move unless `jetson/estop.py` is running on the robot host (heartbeat file) and armed with the gamepad (hold Select+Start 2 s) **and then only while R1 is held** (dead-man); any other button is a hard stop. For dry-run development only, add `--no-estop`. See `docs/JetBot Notes.md`.

Laptop-side command sender: `python -m tools.send_cmd --ip <jetbot-ip> --v 0.3 --seconds 2` (add `--silent-end` to test the 300 ms watchdog).

## D. ESP32-CAM firmware (PlatformIO in VS Code)

Install the PlatformIO IDE extension; it installs its own core on first start (several hundred MB, slow on bad Wi-Fi). Then `python -m tools.fetch_esp_jpeg`, copy `esp32/sentry_cam/secrets.example.h` to `secrets.h` (hotspot name and password; 2.4 GHz only), open `esp32/tile_stream` and build or upload. PlatformIO's `pio.exe` is not on the PATH of a normal terminal: use `~/.platformio/penv/Scripts/pio.exe` or the PlatformIO terminal. Never flash another person's board without asking: it overwrites their firmware. The serial port number can change after a replug (COM3 -> COM4). Full story, interface and limits: `docs/ESP32-CAM.md`.

## GPU checks

`python -m tools.gpu_baseline` is HuynhNguyenHoaiLoc's Week 1 GPU baseline (single-model speed and memory; on their branch until merged). `python -m tools.gpu_pipeline_check` (sections `osnet`, `pipeline`; choose with `--only`) checks what that tool does not: the whole multi-model pipeline and the re-ID OSNet weights. On DoanQuocKien's RTX 4050 the 3-model pipeline (YOLOv8n + YOLOv8n-pose + OSNet on two crops) runs at **37 FPS** using about 300 MB of GPU memory, against the plan's 15 FPS and 5.5 GB. Results: `reports/DoanQuocKien/week-01/gpu_baseline_2026-10-06.txt`. InsightFace's detector and embedder run on the GPU (CUDAExecutionProvider, about 7 ms per 640x480 frame) and OSNet runs in 11-13 ms per batch with re-ID weights.

**Get the models (all team members):** `python -m tools.fetch_models` downloads the InsightFace face detector + embedder (about 16 MB, from HuggingFace `immich-app/buffalo_s`, into `~/.insightface/models/buffalo_s/`) and two **re-ID-trained** OSNet weight files into `weights/` (gitignored): `osnet_ain_x1_0` (multi-source domain generalisation, the default for a new camera and new people) and `osnet_x0_25` (Market1501, small and fast). It resumes, retries, and loads checkpoints with torch's `weights_only` safety left ON (only the NumPy types a file names are allowed). YOLO weights download on first use. **Do not use torchreid's `pretrained=True`: those weights are ImageNet-only, not re-identification weights.** On a bad network day (about 10 KB/s) just run it again.

## Running the tests

| Command | Runs | Needs |
| :-- | :-- | :-- |
| `pytest` | T0 (+ T1/gpu if present, skipped when impossible) | nothing |
| `pytest -m "not gpu and not hil"` | CPU-only subset | nothing |
| `pytest --hil` | adds hardware-in-the-loop tests | the real robot, DoanQuocKien only |

## Known problems

| Symptom | Cause / fix |
| :-- | :-- |
| `torch.cuda.is_available()` is False, version has no `+cu128` | CPU wheel got installed. `pip uninstall -y torch torchvision`, redo step 1 |
| ONNX Runtime silently on CPU; log mentions `cudart64_13.dll` | onnxruntime-gpu 1.30+ wants CUDA 13. Pin 1.23.2 (step 3) |
| `check_env` says two onnxruntime packages installed | step 3 above |
| `ModuleNotFoundError: tensorboard` from torchreid | `pip install tensorboard` (already in `requirements-base.txt`) |
| pip stalls or fails on a slow/unstable connection | download the wheel with `curl.exe -L -C - --retry 30 --retry-all-errors -o x.whl <url>` and `pip install --no-deps x.whl` |
| Video over ZeroMQ is slow or loses most frames, seconds of latency, big packets lost in `ping -f -l 1472` | **Wi-Fi power save on the Jetson** (Realtek RTL8822CE, driver default `rtw_power_mgnt=2`). Permanent fix on our robot: `/etc/modprobe.d/8822ce-sentry.conf` with `options rtl8822ce rtw_power_mgnt=0 rtw_ips_mode=0`, then reboot; check with `python -m tools.jetbot_status <ip>` (`iw get power_save` is misleading). Quick runtime alternative: `sudo iw dev wlan0 set power_save off` (reverts on reboot). Measured effect: 48 % frame loss to 0 %, p95 latency 21 s to 65 ms |
| Models run 5-8x slower than expected (e.g. a 3-model pipeline at 5 FPS instead of 35), GPU clock stuck near 250-450 MHz | Windows throttles processes started from a background or hidden shell. Run from a normal foreground terminal, or opt the process out of power throttling and raise its priority (see `run_unthrottled()` in `tools/gpu_pipeline_check.py`). Measured 2026-10-06: 5.3 -> 34.9 FPS |
| `ModuleNotFoundError: common` when running a script from `tools/` | run it as a module from the repo root: `python -m tools.send_cmd` |
