"""Robot host (Python 3.6): log every gamepad button event from /dev/input/js0 for N s (a second reader; estop.py keeps
its own). Usage: python3 js_log_1114.py <seconds>"""
import os
import select
import struct
import sys
import time

EV = struct.Struct("IhBB")
t_end = time.monotonic() + float(sys.argv[1])
fd = os.open("/dev/input/js0", os.O_RDONLY | os.O_NONBLOCK)
while time.monotonic() < t_end:
    if not select.select([fd], [], [], 0.1)[0]:
        continue
    while True:
        try:
            data = os.read(fd, EV.size)
        except BlockingIOError:
            break
        if len(data) < EV.size:
            break
        _, value, typ, number = EV.unpack(data)
        if (typ & 0x7F) == 1:
            print("%s button %2d %s%s" % (time.strftime("%H:%M:%S"), number, "DOWN" if value else "up",
                                          " (init)" if typ & 0x80 else ""), flush=True)
