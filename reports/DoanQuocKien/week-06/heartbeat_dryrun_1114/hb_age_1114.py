"""Robot side (Python 3.6, runs in the jetbot_jupyter container): sample the age of ESTOP_ALIVE every 10 ms for N s.
Prints one line per second (max age, latch present) and a summary. Usage: python3 hb_age_1114.py <dir> <seconds>"""
import os
import sys
import time

d, dur = sys.argv[1], float(sys.argv[2])
alive, latch = os.path.join(d, "ESTOP_ALIVE"), os.path.join(d, "ESTOP")
ages, over = [], {0.6: 0, 0.8: 0, 1.0: 0}
t_end = time.monotonic() + dur
sec_start, sec_max, sec_latch = time.monotonic(), 0.0, False
errors = 0
while time.monotonic() < t_end:
    now = time.monotonic()
    try:
        with open(alive) as f:
            age = now - float(f.read())
    except (OSError, ValueError):
        errors += 1
        age = None
    lat = os.path.exists(latch)
    if age is not None:
        ages.append(age)
        for k in over:
            if age > k:
                over[k] += 1
        sec_max = max(sec_max, age)
    sec_latch = sec_latch or lat
    if now - sec_start >= 1.0:
        print("%s max_age %.3f latch %s" % (time.strftime("%H:%M:%S"), sec_max, "yes" if sec_latch else "no"), flush=True)
        sec_start, sec_max, sec_latch = now, 0.0, False
    time.sleep(0.01)
ages.sort()
n = len(ages)
print("SUMMARY samples %d read_errors %d max %.3f p99 %.3f p50 %.3f over0.6 %d over0.8 %d over1.0 %d" % (
    n, errors, ages[-1], ages[int(0.99 * (n - 1))], ages[n // 2], over[0.6], over[0.8], over[1.0]), flush=True)
