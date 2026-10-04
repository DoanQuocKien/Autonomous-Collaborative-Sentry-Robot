"""Send (v, w) to the Jetson at 30 Hz for a few seconds; for robot checks and HIL tests.

    python -m tools.send_cmd --ip 192.168.137.20 --v 0.3 --w 0 --seconds 2
    python -m tools.send_cmd --ip ... --v 0.3 --silent-end      # then go quiet: the motors must stop within ~0.35 s

By default the last packet is a zero command, so the robot stops at once even without the watchdog.
"""
import argparse
import time

from sentry.config import load
from sentry.net.udp_tx import UDPSender


def main():
    ap = argparse.ArgumentParser()
    cfg = load()["net"]
    ap.add_argument("--ip", required=True)
    ap.add_argument("--port", type=int, default=cfg["control_port"])
    ap.add_argument("--v", type=float, default=0.0)
    ap.add_argument("--w", type=float, default=0.0)
    ap.add_argument("--seconds", type=float, default=2.0)
    ap.add_argument("--hz", type=float, default=cfg["control_rate_hz"])
    ap.add_argument("--silent-end", action="store_true", help="stop sending instead of sending a zero command")
    a = ap.parse_args()

    if not 0 < a.seconds < float("inf"):
        ap.error("--seconds must be positive and finite")
    sender = UDPSender(a.ip, a.port, a.hz)
    end = time.perf_counter() + a.seconds
    completed = False
    try:
        while time.perf_counter() < end:
            sender.send(a.v, a.w)
            time.sleep(min(sender.period_s, max(0, end - time.perf_counter())))
        completed = True
    finally:
        # An exception always attempts a stop; silent-end applies only to a normal HIL run.
        sender.close(stop=not (completed and a.silent_end))
    print("sent %d packets; %d send-buffer drops" % (sender.sent, sender.dropped))


if __name__ == "__main__":
    main()
