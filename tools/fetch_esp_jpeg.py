"""Fetch Espressif's esp_new_jpeg encoder (MIT licence, prebuilt for the classic ESP32) into esp32/lib_shared/esp_new_jpeg/ for the ESP32-CAM firmware.

    python -m tools.fetch_esp_jpeg
The library is a 2.4 MB binary, so it is not committed (esp32/lib_shared/ is gitignored). Source: https://github.com/espressif/esp-adf-libs/tree/master/esp_new_jpeg
"""
import sys
import time
import urllib.request
from pathlib import Path

BASE = "https://raw.githubusercontent.com/espressif/esp-adf-libs/master/esp_new_jpeg/"
DEST = Path(__file__).resolve().parent.parent / "esp32" / "lib_shared" / "esp_new_jpeg"
FILES = [  # (remote path, local path)
    ("include/esp_jpeg_common.h", "include/esp_jpeg_common.h"),
    ("include/esp_jpeg_enc.h", "include/esp_jpeg_enc.h"),
    ("include/esp_jpeg_version.h", "include/esp_jpeg_version.h"),
    ("lib/esp32/libesp_new_jpeg.a", "lib/libesp_new_jpeg.a"),
    ("LICENSE", "LICENSE"),
]


def fetch(remote, local, tries=6):
    dest = DEST / local
    if dest.exists() and dest.stat().st_size > 0:
        print("have  ", local)
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    for i in range(tries):
        try:
            urllib.request.urlretrieve(BASE + remote, part)
            part.replace(dest)
            print("fetch ", local, "(%d bytes)" % dest.stat().st_size)
            return True
        except Exception as e:  # noqa: BLE001 - network errors are many kinds; retry them all
            print("   attempt %d failed (%s)" % (i + 1, type(e).__name__))
            time.sleep(3)
    return False


def main():
    ok = all([fetch(r, l) for r, l in FILES])
    print("ALL PRESENT" if ok else "MISSING FILES: run again")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
