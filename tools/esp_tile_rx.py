"""Watch / record the ESP32-CAM stream (640x480 from the GC2145, see docs/ESP32-CAM.md). Prints one line per second and can save stills or show a live window.

    python -m tools.esp_tile_rx --seconds 60 --save reports/<handle>/week-NN/camera
    python -m tools.esp_tile_rx --show            # live window, q to quit
Allow python through the Windows firewall for UDP on Private networks.
"""
import argparse
import time
from pathlib import Path

import cv2

from sentry.espcam import TileReceiver


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5600)
    ap.add_argument("--seconds", type=float, default=60)
    ap.add_argument("--save", default="", help="folder: the picture is saved there every 3 s as tile_latest.png")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--pattern", default="BG", choices=["BG", "GB", "RG", "GR"], help="Bayer pattern of the sensor output")
    ap.add_argument("--wb", default="gray", choices=["gray", "none"], help="white balance")
    ap.add_argument("--gamma", type=float, default=1.0)
    a = ap.parse_args()
    rx = TileReceiver(a.port, a.pattern, a.wb, a.gamma).start()
    t0 = time.perf_counter()
    t_rep, t_save = t0 + 1, 0.0
    last = (0, 0, 0, 0)
    print("listening on UDP %d for %.0f s ..." % (a.port, a.seconds))
    try:
        while time.perf_counter() - t0 < a.seconds:
            time.sleep(0.02)
            now = time.perf_counter()
            if a.show:
                frame, _, _ = rx.latest()
                if frame is not None:
                    cv2.imshow("esp32-cam", frame)
                if cv2.waitKey(1) == ord("q"):
                    break
            if a.save and now - t_save >= 3:
                frame, _, _ = rx.latest()
                if frame is not None:
                    Path(a.save).mkdir(parents=True, exist_ok=True)
                    cv2.imwrite(str(Path(a.save) / "tile_latest.png"), frame)
                    t_save = now
            if now >= t_rep:
                cur = (rx.frames, rx.tiles, rx.missing, rx.bytes)
                d = [c - l for c, l in zip(cur, last)]
                print("%5.1f fps | tiles/frame %5.1f | missing %3d | %5.2f Mbit/s | gains B %.2f G %.2f R %.2f" % (
                    d[0], d[1] / max(d[0], 1), d[2], d[3] * 8 / 1e6, *rx.gains))
                last, t_rep = cur, t_rep + 1
    finally:
        rx.stop()


if __name__ == "__main__":
    main()
