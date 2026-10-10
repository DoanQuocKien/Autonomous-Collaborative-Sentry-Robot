"""Capture an ESP32 / ESP32-CAM serial log, optionally after a clean reset pulse, and count the usual failure signs.

    python -m tools.esp_serial COM3                 # listen passively for 12 s at 115200 baud
    python -m tools.esp_serial COM3 115200 15 reset # pulse EN (reset) first, then listen for 15 s

Never touches IO0 (DTR is held false), so the board always boots normally and is never put into the flasher.
Needs pyserial (in requirements-base.txt). Found on 2026-10-09: a log pasted from a serial monitor was cut off after the
third `load:` line; a captured full boot showed the firmware running and the real error: camera probe 0x106.
"""
import sys
import time

import serial

PORT = sys.argv[1]
BAUD = int(sys.argv[2]) if len(sys.argv) > 2 else 115200
SECS = float(sys.argv[3]) if len(sys.argv) > 3 else 12
RESET = len(sys.argv) > 4 and sys.argv[4] == "reset"

ser = serial.Serial(PORT, BAUD, timeout=0.2)
ser.setDTR(False)   # IO0 high: normal boot, never the bootloader
if RESET:
    ser.setRTS(True)   # EN low
    time.sleep(0.15)
    ser.setRTS(False)  # EN high: boot
t0 = time.time()
buf = b""
while time.time() - t0 < SECS:
    d = ser.read(512)
    if d:
        buf += d
ser.close()
text = buf.decode("utf-8", errors="replace")
print("=== %d bytes in %.0f s at %d baud%s" % (len(buf), SECS, BAUD, " after a reset pulse" if RESET else " (passive)"))
print(text if text.strip() else "(nothing received)")
resets = text.count("rst:0x")
print("\n--- boot banners seen: %d | brownout messages: %d | 'entry 0x' lines: %d | 'Guru Meditation': %d | 'invalid header': %d | 'flash read err': %d" % (
    resets, text.count("Brownout"), text.count("entry 0x"), text.count("Guru Meditation"), text.count("invalid header"), text.count("flash read err")))
