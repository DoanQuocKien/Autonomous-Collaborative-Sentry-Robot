"""Read one raw Bayer frame the ESP32 prints over serial (esp32/cam_rate: FRAME_START <n> ... FRAME_END), demosaic it with each of the four Bayer
patterns and save the results, so the right pattern can be picked by eye.

    python -m tools.esp_grab_raw COM4 --out reports/DoanQuocKien/week-01/camera
"""
import argparse
import time
from pathlib import Path

import cv2
import numpy as np
import serial

W, H = 640, 480


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("port")
    ap.add_argument("--out", default=".")
    ap.add_argument("--seconds", type=float, default=90)
    a = ap.parse_args()
    ser = serial.Serial(a.port, 115200, timeout=0.5)
    ser.setDTR(False)  # IO0 stays high: normal boot
    ser.setRTS(True)
    time.sleep(0.15)
    ser.setRTS(False)
    buf = b""
    t0 = time.time()
    raw = None
    while time.time() - t0 < a.seconds:
        buf += ser.read(65536)
        i = buf.find(b"FRAME_START ")
        if i >= 0:
            j = buf.find(b"\n", i)
            if j > 0:
                n = int(buf[i + 12:j])
                if len(buf) >= j + 1 + n:
                    raw = buf[j + 1:j + 1 + n]
                    break
    ser.close()
    if raw is None:
        print("no frame received")
        return 1
    print("got %d bytes, mean %.1f, min %d, max %d" % (len(raw), np.mean(np.frombuffer(raw, np.uint8)), min(raw), max(raw)))
    img = np.frombuffer(raw, np.uint8)[:W * H].reshape(H, W)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "gc2145_raw_bayer.bin").write_bytes(raw)
    cv2.imwrite(str(out / "gc2145_raw_gray.png"), img)
    for name, code in (("BG", cv2.COLOR_BAYER_BG2BGR), ("GB", cv2.COLOR_BAYER_GB2BGR), ("RG", cv2.COLOR_BAYER_RG2BGR), ("GR", cv2.COLOR_BAYER_GR2BGR)):
        cv2.imwrite(str(out / ("gc2145_raw_demosaic_%s.png" % name)), cv2.cvtColor(img, code))
    print("saved gray + 4 demosaic variants to", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
