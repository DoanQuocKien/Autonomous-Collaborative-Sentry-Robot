"""Dongle-unplug test through the REAL motor service (wheels off the ground). Sends v=0.5 (x cap 0.3 = 0.15 per wheel)
at 30 Hz to the control port for DUR s, then prints the new lines of estop.log, robot_udp.log and the button log.
Motion still needs the operator to arm and hold R1. Usage: python unplug_1114.py <ip> [seconds]"""
import socket
import sys
import time

sys.path.insert(0, ".")
from common.protocol import PORT_CONTROL, encode_control  # noqa: E402
from tools import jetbot_ssh  # noqa: E402

ip = sys.argv[1]
dur = float(sys.argv[2]) if len(sys.argv) > 2 else 40.0
pw = jetbot_ssh.password()
c = jetbot_ssh.connect(ip, "jetbot", pw)
S = "/home/jetbot/sentry"
n_estop = int(jetbot_ssh.run(c, "wc -l < %s/estop.log" % S))
n_udp = int(jetbot_ssh.run(c, "wc -l < %s/robot_udp.log" % S))
print("allow args:", jetbot_ssh.run(c, "cat /etc/default/sentry-control 2>/dev/null") or "(none)")
print("services:", jetbot_ssh.run(c, "systemctl is-active sentry-estop sentry-control | tr '\\n' ' '"))
sftp = c.open_sftp()
sftp.put(sys.argv[0].replace("unplug_1114.py", "js_log_1114.py"), S + "/js_log_1114.py")
sftp.close()
stdin = c.exec_command("sudo -S -p '' sh -c 'nohup python3 -u %s/js_log_1114.py %d > %s/js_log_1114.log 2>&1 &'" % (S, int(dur), S))[0]
stdin.write(pw + "\n")
stdin.flush()
time.sleep(1.0)

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
t0, seq = time.monotonic(), 0
print("sending v=0.5 to %s:%d for %.0f s" % (ip, PORT_CONTROL, dur), flush=True)
while time.monotonic() - t0 < dur:
    seq += 1
    sock.sendto(encode_control(seq, 0.5, 0.0), (ip, PORT_CONTROL))
    time.sleep(1 / 30.0)
for _ in range(10):  # explicit stop packets after the run
    seq += 1
    sock.sendto(encode_control(seq, 0.0, 0.0), (ip, PORT_CONTROL))
    time.sleep(0.03)
time.sleep(1.0)
print("===== estop.log (new lines, host clock)")
print(jetbot_ssh.run(c, "tail -n +%d %s/estop.log" % (n_estop + 1, S)))
print("===== robot_udp.log (new lines, container clock)")
print(jetbot_ssh.run(c, "tail -n +%d %s/robot_udp.log" % (n_udp + 1, S)))
print("===== js_log_1114.log (host clock)")
print(jetbot_ssh.run(c, "cat %s/js_log_1114.log" % S))
jetbot_ssh.sudo(c, "rm -f %s/js_log_1114.py %s/js_log_1114.log" % (S, S), pw)
c.close()
