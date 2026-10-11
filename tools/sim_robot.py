"""Simulated JetBot for offline control work: UDP (v, w) in, unicycle pose out (Implementation Plan, W1).

    python -m tools.sim_robot                          # listens on the control port from config.toml, prints the pose while moving
    python -m tools.sim_robot --log data/sim/pose.csv  # also writes every step: t, x, y, theta, v, w

Packets go through the same decoder and SeqFilter as jetson/robot_udp.py (common.protocol), so the sim accepts and
rejects exactly what the robot does (NaN, out of range, stale or duplicated seq, malformed JSON). The watchdog is
config.toml [safety] watchdog_s, the robot's default. Not modelled: the gamepad e-stop, the motor dead zone and the
wheel mixing; the sim integrates the normalised (v, w) directly, scaled by [sim] v_max_mps / w_max_radps.
SimRobot is pure logic (no sockets, no clock), so controller tests can drive it step by step.
"""
import argparse
import csv
import math
import socket
import time
from pathlib import Path

from common.protocol import SeqFilter, decode_control
from sentry.config import load


class SimRobot:
    """Unicycle kinematics; positive w turns left (counter-clockwise), as on the robot."""

    def __init__(self, v_max=0.5, w_max=2.0, watchdog_s=0.3):
        self.v_max, self.w_max, self.watchdog_s = v_max, w_max, watchdog_s
        self.x = self.y = self.theta = 0.0
        self.v = self.w = 0.0          # normalised command in [-1, 1]
        self.last_cmd = None           # time of the last accepted motion command; None = stopped
        self.seq = SeqFilter()

    def on_packet(self, data, now):
        """-> the decoded message, or None when the robot would ignore the packet."""
        try:
            msg = decode_control(data)
        except ValueError:
            return None
        if not self.seq.accept(msg["seq"], now):
            return None
        if "play" not in msg:
            self.v, self.w, self.last_cmd = msg["v"], msg["w"], now
        return msg

    def step(self, now, dt):
        """Apply the watchdog at `now`, then advance the pose by dt seconds. -> True if the watchdog just stopped it."""
        stopped = self.last_cmd is not None and now - self.last_cmd > self.watchdog_s
        if stopped:
            self.v = self.w = 0.0
            self.last_cmd = None
        v, w = self.v * self.v_max, self.w * self.w_max
        if abs(w) < 1e-9:
            self.x += v * math.cos(self.theta) * dt
            self.y += v * math.sin(self.theta) * dt
        else:  # exact arc for a constant (v, w) over dt
            th = self.theta + w * dt
            self.x += v / w * (math.sin(th) - math.sin(self.theta))
            self.y -= v / w * (math.cos(th) - math.cos(self.theta))
        self.theta = (self.theta + w * dt + math.pi) % (2 * math.pi) - math.pi
        return stopped

    @property
    def moving(self):
        return self.v != 0.0 or self.w != 0.0


def main():
    cfg = load()
    sim = cfg["sim"]
    ap = argparse.ArgumentParser(description="Simulated JetBot: UDP (v, w) -> unicycle pose")
    ap.add_argument("--port", type=int, default=cfg["net"]["control_port"])
    ap.add_argument("--log", type=Path, help="CSV of every step: t, x, y, theta, v, w")
    args = ap.parse_args()

    robot = SimRobot(sim["v_max_mps"], sim["w_max_radps"], cfg["safety"]["watchdog_s"])
    dt = 1.0 / sim["loop_hz"]
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", args.port))
    sock.setblocking(False)
    log_file = writer = None
    if args.log:
        args.log.parent.mkdir(parents=True, exist_ok=True)
        log_file = args.log.open("w", newline="", encoding="utf-8")
        writer = csv.writer(log_file)
        writer.writerow(["t", "x_m", "y_m", "theta_rad", "v", "w"])
    print(f"[Sim] Listening on UDP {args.port}; v_max {robot.v_max} m/s, w_max {robot.w_max} rad/s, watchdog {robot.watchdog_s} s")
    rejected = 0
    t_prev = time.perf_counter()
    try:
        while True:
            while True:
                try:
                    data, _ = sock.recvfrom(1024)
                except BlockingIOError:
                    break
                msg = robot.on_packet(data, time.perf_counter())
                if msg is None:
                    rejected += 1
                elif "play" in msg:
                    print(f"[Sim] Audio play command: {msg['play']}")
            now = time.perf_counter()
            if robot.step(now, now - t_prev):
                print("[Sim] Watchdog timeout. Stopping motors.")
            t_prev = now
            if writer:
                writer.writerow(["%.4f" % now, "%.4f" % robot.x, "%.4f" % robot.y, "%.4f" % robot.theta, robot.v, robot.w])
            if robot.moving:
                print(f"[Sim Pose] x={robot.x:.3f} m, y={robot.y:.3f} m, theta={math.degrees(robot.theta):.1f}° "
                      f"(v={robot.v:.2f}, w={robot.w:.2f}, rejected packets {rejected})")
            time.sleep(max(0.0, dt - (time.perf_counter() - now)))
    except KeyboardInterrupt:
        print("\n[Sim] Terminated.")
    finally:
        sock.close()
        if log_file:
            log_file.close()


if __name__ == "__main__":
    main()
