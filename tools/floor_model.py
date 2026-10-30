"""Load a measured floor model (reports/.../classroom_1030/analysis/floor_model_1030.json, written by tools.analyse_classroom_1030) into the existing code.

    from tools.floor_model import load, wheel_model, FloorSim
    fm = load()
    model = wheel_model(fm, battery_v=11.4)          # sentry.nav.wheel_model.WheelModel: m0 for that voltage, the measured spin rate, the drift
    sim = FloorSim(fm, battery_v=11.4)               # tools.sim_robot.SimRobot that moves like that floor; sim.camera_pose(now) = the pose the video shows (latency)

PROVISIONAL: one floor (classroom glossy tile), one pack, 11.28-11.70 V; outside that range wheel_model() refuses. Not modelled: the motor start lag (the turn fit says it nets
out to about 0.02 s), the per-run spread of the drift and of the turn (use the *_std fields of the JSON for noise), the floor's other areas.
"""
import json
import math
from collections import deque

from sentry.nav.wheel_model import WheelModel
from tools.sim_robot import SimRobot

DEFAULT = "reports/DoanQuocKien/week-04/classroom_1030/analysis/floor_model_1030.json"


def load(path=DEFAULT):
    with open(path) as f:
        return json.load(f)


def wheel_model(fm, battery_v, margin_v=0.1):
    """WheelModel with m0(V) from the floor model, its drift, and turn scales that give the measured spin rate at w = 0.45."""
    w = fm["wheel"]
    lo, hi = w["valid_battery_v"]
    if not lo - margin_v <= battery_v <= hi + margin_v:
        raise ValueError("battery %.2f V outside the measured %.2f-%.2f V" % (battery_v, lo, hi))
    m0 = w["m0_at_11_5"] + w["m0_per_volt"] * (battery_v - 11.5)
    model = WheelModel(k=w["k"], m0=m0, track=w["track"], max_speed=w["max_speed"], min_pwm=w["min_pwm"], drift_rad_per_m=fm["drift"]["sim_rad_per_m"])
    scale = fm["turn"]["rate_rad_per_s_at_w_0_45"] / model.body_speeds(0.0, 0.45)[1]
    model.w_scale_left = model.w_scale_right = scale
    return model


class FloorSim(SimRobot):
    """SimRobot whose normalised command goes through the floor's wheel model (dead zone, wheel law, spin rate, drift) instead of v_max / w_max."""

    def __init__(self, fm, battery_v, watchdog_s=0.3):
        super().__init__(watchdog_s=watchdog_s)
        self.model = wheel_model(fm, battery_v)
        self.latency_s = fm["video"]["sim_latency_s"]
        self.history = deque(maxlen=600)

    def step(self, now, dt):
        stopped = self.last_cmd is not None and now - self.last_cmd > self.watchdog_s
        if stopped:
            self.v = self.w = 0.0
            self.last_cmd = None
        v, w = self.model.body_speeds(self.v, self.w)
        if abs(w) < 1e-9:
            self.x += v * math.cos(self.theta) * dt
            self.y += v * math.sin(self.theta) * dt
        else:
            th = self.theta + w * dt
            self.x += v / w * (math.sin(th) - math.sin(self.theta))
            self.y -= v / w * (math.cos(th) - math.cos(self.theta))
        self.theta = (self.theta + w * dt + math.pi) % (2 * math.pi) - math.pi
        self.history.append((now + dt, self.x, self.y, self.theta))
        return stopped

    def camera_pose(self, now):
        """The pose the robot's video shows at `now` (the newest pose at least latency_s old), or None before that."""
        old = [p for p in self.history if p[0] <= now - self.latency_s]
        return old[-1][1:] if old else None
