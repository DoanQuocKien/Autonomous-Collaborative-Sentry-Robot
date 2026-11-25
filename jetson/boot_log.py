"""Boot power/health logger (diagnostic, 2026-11-23): one line per second for the first --seconds after boot, fsynced, so the file shows the last
seconds before a crash or power loss. Python 3.6, stdlib only; runs as root from sentry-bootlog.service (needs i2cget and tegrastats).

Line: wall time | uptime s | battery V (INA219 0x41) | tegrastats (RAM, CPU load/freq, temperatures, POM_5V_IN = Jetson 5 V input mW now/avg) | loadavg.
Read it after a crash:  tail -40 /home/jetbot/sentry/bootlog.log   ('BOOT' lines separate the boots)
"""
import argparse
import os
import subprocess
import threading
import time

LOG = "/home/jetbot/sentry/bootlog.log"
FAST_LOG = "/home/jetbot/sentry/bootlog_v.log"      # battery only, --fast-hz samples per second, every line fsynced: a short dip right before a crash is not lost


def battery_volts(i2cget_output):
    """`i2cget -y 1 0x41 0x02 w` prints a byte-swapped word like 0xd25d: bus voltage = bits 15..3, 4 mV per step (same as tools/jetbot_status.py)."""
    raw = int(i2cget_output.split()[-1], 16)
    raw = ((raw & 0xFF) << 8) | (raw >> 8)
    return (raw >> 3) * 4 / 1000.0


def read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except (IOError, OSError):
        return "?"


def battery():
    try:
        return "%.2f" % battery_volts(subprocess.check_output(["i2cget", "-y", "1", "0x41", "0x02", "w"], timeout=2).decode())
    except Exception as e:          # a failed read is itself information
        return "ERR(%s)" % type(e).__name__


def sample_loop(read_battery, emit, hz, stop):
    """Battery voltage `hz` times per second until `stop` is set; one line per sample (uptime in s, volts or ERR)."""
    while not stop.is_set():
        emit("%s | up %s | %s V" % (time.strftime("%H:%M:%S"), read("/proc/uptime").split()[0], read_battery()))
        stop.wait(1.0 / hz)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=900.0)
    ap.add_argument("--log", default=LOG)
    ap.add_argument("--fast-hz", type=float, default=10.0, help="battery samples per second in --fast-log (0 = off); i2cget is forked per sample, about 1-2 %% CPU at 10 Hz")
    ap.add_argument("--fast-log", default=FAST_LOG)
    a = ap.parse_args()
    out = open(a.log, "a")

    def emit(s):
        out.write(s + "\n")
        out.flush()
        os.fsync(out.fileno())

    stop = threading.Event()
    if a.fast_hz > 0:
        fast = open(a.fast_log, "a")

        def emit_fast(s):
            fast.write(s + "\n")
            fast.flush()
            os.fsync(fast.fileno())

        emit_fast("BOOT %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
        threading.Thread(target=sample_loop, args=(battery, emit_fast, a.fast_hz, stop), daemon=True).start()
    emit("BOOT %s boot_id=%s uptime=%s" % (time.strftime("%Y-%m-%d %H:%M:%S"), read("/proc/sys/kernel/random/boot_id")[:8], read("/proc/uptime").split()[0]))
    t_end = time.time() + a.seconds
    try:
        proc = subprocess.Popen(["tegrastats", "--interval", "1000"], stdout=subprocess.PIPE, universal_newlines=True)
        lines = iter(proc.stdout.readline, "")
    except OSError:
        proc, lines = None, iter(lambda: (time.sleep(1), "no tegrastats")[1], None)
    for line in lines:
        emit("%s | up %s | %s V | %s | load %s" % (time.strftime("%H:%M:%S"), read("/proc/uptime").split()[0], battery(), line.strip(), read("/proc/loadavg")[:14]))
        if time.time() > t_end:
            break
    stop.set()
    if proc:
        proc.terminate()
    emit("END %s" % time.strftime("%H:%M:%S"))


if __name__ == "__main__":
    main()
