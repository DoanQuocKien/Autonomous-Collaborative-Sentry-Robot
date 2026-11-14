"""Laptop side: start the audit robot_udp in --dry-run on spare ports plus the heartbeat-age logger in the container,
send v=0.5 at 30 Hz to the dry-run port for DUR s, then print both logs and the host estop.log tail.
The real motor service (port 5556) gets no packets, and the dry run never opens the motors.
Usage: python dryrun_1114.py <ip> [seconds]"""
import socket
import sys
import time

sys.path.insert(0, ".")
from common.protocol import encode_control  # noqa: E402
from tools import jetbot_ssh  # noqa: E402

ip = sys.argv[1]
dur = float(sys.argv[2]) if len(sys.argv) > 2 else 75.0
PORT, CLOCK = 5701, 5702
pw = jetbot_ssh.password()
c = jetbot_ssh.connect(ip, "jetbot", pw)
sftp = c.open_sftp()
sftp.put(sys.argv[0].replace("dryrun_1114.py", "hb_age_1114.py"), "/home/jetbot/sentry/hb_age_1114.py")
sftp.close()

run_s = int(dur + 5)
start = ("docker exec -d -w /workspace/sentry jetbot_jupyter sh -c "
         "'timeout %d python3 -u jetson/robot_udp_audit1114.py --dry-run --port %d --clock-port %d > dryrun_1114.log 2>&1'"
         % (run_s, PORT, CLOCK))
print(jetbot_ssh.sudo(c, start, pw) or "dry-run started")
hb = ("docker exec -d -w /workspace/sentry jetbot_jupyter sh -c "
      "'python3 -u hb_age_1114.py /workspace/sentry %d > hb_age_1114.log 2>&1'" % int(dur))
print(jetbot_ssh.sudo(c, hb, pw) or "heartbeat logger started")
time.sleep(2.0)

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
t0, seq = time.monotonic(), 0
print("sending v=0.5 to %s:%d for %.0f s: ARM (hold Start 1.5 s) and HOLD R1 now; release R1 when told" % (ip, PORT, dur))
last_note = -1
while time.monotonic() - t0 < dur:
    seq += 1
    sock.sendto(encode_control(seq, 0.5, 0.0), (ip, PORT))
    el = int(time.monotonic() - t0)
    if el % 10 == 0 and el != last_note:
        last_note = el
        print("t=%2d s%s" % (el, "  -> RELEASE R1 now" if el == int(dur) - 10 else ""), flush=True)
    time.sleep(1 / 30.0)
time.sleep(6.0)
print("===== dryrun_1114.log")
print(jetbot_ssh.run(c, "cat /home/jetbot/sentry/dryrun_1114.log"))
print("===== hb_age_1114.log (summary + seconds over 0.6 s)")
print(jetbot_ssh.run(c, "grep -E 'SUMMARY|max_age (0\\.[6-9]|[1-9])' /home/jetbot/sentry/hb_age_1114.log; grep -c max_age /home/jetbot/sentry/hb_age_1114.log"))
print("===== estop.log tail")
print(jetbot_ssh.run(c, "tail -8 /home/jetbot/sentry/estop.log"))
c.close()
