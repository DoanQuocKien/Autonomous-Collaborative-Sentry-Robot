# ESP32-CAM (entrance camera)

Everything verified on 2026-10-09 with DoanQuocKien's two AI-Thinker ESP32-CAM boards. Raw evidence and every measurement: `reports/DoanQuocKien/week-01/esp32_gc2145_jpeg_2026-10-09.txt`.

## What we found about the camera module

The modules we bought (Shopee listing "OV3660, OV2640 or OV5640, random"; local shop) carry a **GC2145**, sensor ID `0x2145`, I2C address `0x3c`. The GC2145 has **no hardware JPEG**. With the stock CameraWebServer sketch it fails with `JPEG format is not supported on this sensor` (core 3.x) or `Camera probe failed 0x105/0x106`, which can also be caused by a torn or half-seated flat cable (the first module had a torn ribbon).

| Option | VGA 640x480 | Notes |
| :-- | :-- | :-- |
| Stock sketch, camera swapped for an **OV2640** | about 25 fps (others report 29 fps; not measured by us) | hardware JPEG, the HTTP MJPEG interface of the plan applies unchanged. Cheapest guaranteed route |
| GC2145 + software JPEG (`frame2jpg`) | 1.7 fps | 596 ms per frame |
| GC2145 + Espressif `esp_new_jpeg` (full frames) | 4.6-7.7 fps | CPU-bound: 0.65 us per pixel, and it does not scale to two cores |
| **GC2145 + raw Bayer + changed-tile stream (this firmware)** | **14.4 fps average** over a 68 s walk-through test (13.8 fps in large motion; worst case 9-10 fps) | needs a **fixed camera**; details below. **Caveat (2026-10-26):** the board used that day had an **OV2640** (sensor PID 0x26), not a GC2145. This firmware on it gave 1.6 fps (camera interval 639 ms, the same with Wi-Fi off) and wrong colours. The 14.4 fps was measured on a GC2145 with the ESP alone in bright light. Check the sensor first: `SENSOR PID=` in the `esp32/sentry_cam` boot log (0x0026 = OV2640, use `sentry_cam`; 0x2145 = GC2145, use this firmware) |

## How the tile stream works (`esp32/tile_stream`, laptop side `sentry/espcam.py`)

1. **Raw capture, 1 byte per pixel.** The stock driver offers only YUV422/RGB565 for this sensor and the ESP32 camera layer rejects RAW, but it only counts bytes: 480x320 YUV422 = 307,200 B = one 640x480 raw frame. So the camera is started as HVGA YUV422, then `set_framesize(VGA)` and register `0x84 = 0x17` switch the sensor itself to VGA raw Bayer (pattern BG: only checked on a grey scene. The strong colour casts seen on 2026-10-26 came from running this firmware on an OV2640 board, so the pattern is still unverified on a real GC2145 scene).
2. **Sensor timing registers** (write with `set_reg`): clock 10 MHz (below 10 MHz the driver packs 2 bytes per DMA word instead of 1, half the capture work), `0xf8 low 6 bits` (PLL multiplier) = 11, `0xfa high nibble` (divider) = 1, vertical blanking `0x07/0x08` = 12 lines. Measured 15.7 fps clean with Wi-Fi off; divider 13 drops frames; blanking below 280 columns or 12 lines corrupts frames.
3. **Camera on core 0, stream logic on core 1.** The camera interrupt lands on the core that calls `esp_camera_init`; Wi-Fi also steals time from the camera input (13 -> 7.7 fps just by being connected), and started on core 0 the camera keeps 12-15 fps with Wi-Fi on.
4. **Only changed tiles are sent.** The picture is 10 x 15 tiles of 64x32. Each frame a small fingerprint of every tile (8 rows x 16 bytes, kept in internal RAM) is compared with what the laptop last received; tiles above the noise threshold (16) are encoded, biggest change first, within a 35 ms budget. The two oldest tiles are resent every frame, so a lost packet heals in about 75 frames.
5. **Cheap coding.** Each tile is split into its four Bayer colour planes (R, G1, G2, B, shown in the four quadrants), coded as a 64x32 grey JPEG (quality 60) with Espressif's `esp_new_jpeg` encoder on core 1, the shared JPEG header is sent once a second, and several tiles share one UDP packet.
6. **Laptop** (`sentry/espcam.py`, `tools/esp_tile_rx.py`): pastes tiles into a raw canvas, demosaics (`COLOR_BAYER_BG2BGR`) and applies gray-world white balance. A receiver that starts late sends `REFR`, and the ESP32 resends every tile.

## Interface (replaces the "ESP32-CAM -> laptop" row for the GC2145)

UDP, little endian. The laptop broadcasts `HELO` to port 5601 once a second; the ESP32 sends to whoever announced (no IP is configured, the hotspot IP can change). It follows one laptop: another host's `HELO` or `REFR` is ignored while the current laptop keeps announcing (5 s). The receiver likewise follows one ESP32, and `latest()` returns the picture as of the last frame end, read-only and shared by all callers. `REFR` (port 5601) asks for a full picture. Packet = 16-byte header `'S' 'T' type flags frame_id u32 esp_ms u32 a u16 b u16` + payload to port **5600**:

| type | meaning |
| :-- | :-- |
| 1 | JPEG header shared by all tiles (`a` = length), resent once a second |
| 4 | `a` tiles, each `[index u16][length u16][JPEG scan data]` |
| 2 | frame end: `a` = tiles sent, `b` = tiles that were changed; the laptop answers `ACK` + frame_id + esp_ms (the ESP32 prints the round trip) |
| 0, 3 | single tile / complete JPEG tile (legacy, handled by the receiver) |

`REFR`: the ESP32 forgets what the laptop has, resends the JPEG header at once, then every tile (a receiver started late has a complete picture after about 0.2 s in the simulator).

Use it from Python:

```python
from sentry.espcam import TileReceiver
rx = TileReceiver().start()
frame, frame_id, age_s = rx.latest()   # 640x480 BGR, white balanced; None until the first tiles arrive
```

It can be fed from `record.py` like any other stream by saving the frames `latest()` returns.

## Build and flash (PlatformIO in VS Code, no Arduino IDE)

1. `python -m tools.fetch_esp_jpeg` (downloads Espressif's prebuilt encoder into `esp32/lib_shared/`, gitignored).
2. Copy `esp32/sentry_cam/secrets.example.h` to `secrets.h` and put the 2.4 GHz hotspot name and password in it (gitignored).
3. Open `esp32/tile_stream` in VS Code, or run `pio run -t upload --upload-port COMx` (PlatformIO's `pio.exe` is in `~/.platformio/penv/Scripts/`). The board needs an unplugged ribbon check first: gold contacts toward the board, latch fully closed.
4. Laptop: `python -m tools.esp_tile_rx --show` (allow Python through the Windows firewall for UDP, Private networks).

## Using it with `record.py` / `replay.py` (D1 recording) and without the board

- **Recording:** `tools/record.py` reads `http://<esp32_ip>:81/stream`. With the GC2145 boards run `python -m tools.esp_mjpeg_relay` first (it serves exactly that MJPEG stream from the tile stream; `config.toml` has `esp32_ip = "auto"`, which uses the relay when it runs on this laptop), then `python -m tools.record D1`. Tested end to end with a simulated ESP32: 223 JPEGs in about 15 s at 14.9 fps. With an OV2640 board, put the board's IP in `config.toml` and skip the relay.
- **Replay** needs nothing new: `tools/replay.py` already serves the recorded ESP32 frames as MJPEG on port 81.
- **No board at hand:** `python -m tools.esp_tile_sim` sends the same tile stream of a synthetic moving scene, so the receiver, the relay and the recorder can be developed and tested on any laptop.

`esp32/sentry_cam` is the stock CameraWebServer (HTTP MJPEG) for an OV2640 module, patched to build on Arduino core 2.0.17 (`ledcAttach` guard).

### OV2640 module (ordered 2026-10-11, **firmware not tested on a board yet**)

`esp32/sentry_cam` is set up for it (builds, 23% flash): JPEG, VGA 640x480, quality 12, two frame buffers, `GRAB_LATEST`, the same Wi-Fi settings as `tile_stream` (channels 1-13, 20 MHz, no power save), and a warning in the boot log if the sensor is not an OV2640 (`PID=0x26`). On arrival:
1. Copy `secrets.example.h` to `secrets.h`, then `cd esp32/sentry_cam && pio run -t upload --upload-port COMx`.
2. Boot log: expect `SENSOR PID=0x0026` and `Camera Ready! Stream: http://<ip>:81/stream`. A `0x2145` or a `Camera init failed 0x105/0x106` means it is a GC2145 again: send it back (or use `tile_stream`).
3. Stop `esp_mjpeg_relay` (it also uses port 81 on the laptop) and run `python -m tools.record D1`: with `esp32_ip = "auto"` it finds the board on the LAN by its open port 81. Or put the IP in `config.toml`.
4. Measure the frame rate (about 25 fps VGA is reported by others, not by us) and write it here and in the plan. `esp32/experiments/` holds the measurement sketches behind the numbers above.

## Known limits and things that went wrong

- **Fixed camera only.** A moving or shaking camera makes every tile change; throughput then falls to 9-10 fps (full-load test) and large moving regions refresh at about 5 fps.
- **Tuned on one board.** The second board (ESP32-D0WD-V3 rev 3.1) lost its Wi-Fi uplink as soon as the camera ran, on every setting we tried (not power, memory, encoder, channel width or camera clock; cause unknown, same camera module). The first board works. If a board shows `send-fail` and missing acks only while the camera runs, swap boards.
- **Wi-Fi.** Hotspot channel 13 worked on the first board with country `VN` (channels 1-13) and 20 MHz width set in the firmware. Laptop Wi-Fi and laptop hotspot on different bands make the radio time-slice (95 % ping loss); keep the laptop's own Wi-Fi on the same 2.4 GHz channel, or off.
- **Ghost slivers (reduced, 2026-10-10).** A thin edge that covers a tile only partly used to leave a stale sliver for up to about 5 s. The detector now also flags a tile when 8 or more fingerprint samples differ by 48 or more (pieces spread over the tile, gaps at most 12 px: an edge 14 px wide is caught at every position, tested in `tests/test_tile_detect.py`), and while the scene is quiet 4 tiles per frame are refreshed (a full refresh in about 2.5 s). Hairline slivers can still appear behind a fast edge until the refresh reaches them.
- **Flash status of the 2026-10-10 firmware changes:** flashed and checked on 2026-10-11 (still scene, 45 s: about 15 fps, 0 missing tiles after the first second, 0.06-0.2 Mbit/s, no send failures; MJPEG relay serves 640x480 JPEGs; `reports/DoanQuocKien/week-01/camera/esp32_tile_stream_2026-10-11.txt`). **Not yet measured with the new detector:** large motion and the thin-edge ghost slivers; do this with the door view.
- **Colour** is only gray-world white balanced; no colour-correction matrix.
- **Power:** the camera needs a stable 5 V (a phone charger did not change the results; the laptop USB port is fine).
- The `GC2145` driver comment says the ESP32 can only take about 15 MHz PCLK: it is also why raw at 1 byte per pixel (half the data of YUV) is what makes 15 fps possible.
