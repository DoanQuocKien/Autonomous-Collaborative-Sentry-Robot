"""Send (v, w) to the Jetson at 30 Hz for a few seconds; for robot checks and HIL tests.

    python -m tools.send_cmd --ip 192.168.137.20 --v 0.3 --w 0 --seconds 2
    python -m tools.send_cmd --ip ... --v 0.3 --silent-end      # then go quiet: the motors must stop within ~0.35 s

By default the last packet is a zero command, so the robot stops at once even without the watchdog.
"""
import argparse
import socket
import time

from common.protocol import PORT_CONTROL, encode_control


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ip", required=True)
    ap.add_argument("--port", type=int, default=PORT_CONTROL)
    ap.add_argument("--v", type=float, default=0.0)
    ap.add_argument("--w", type=float, default=0.0)
    ap.add_argument("--seconds", type=float, default=2.0)
    ap.add_argument("--hz", type=float, default=30.0)
    ap.add_argument("--silent-end", action="store_true", help="stop sending instead of sending a zero command")
    a = ap.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    seq, end = 0, time.monotonic() + a.seconds
    while time.monotonic() < end:
        sock.sendto(encode_control(seq, a.v, a.w), (a.ip, a.port))
        seq += 1
        time.sleep(1.0 / a.hz)
    if not a.silent_end:
        sock.sendto(encode_control(seq, 0.0, 0.0), (a.ip, a.port))
    print("sent %d packets" % (seq + (0 if a.silent_end else 1)))


if __name__ == "__main__":
    main()
