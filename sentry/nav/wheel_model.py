"""Per-wheel motion model fitted on 2026-10-15 (classroom glossy tile, battery 11.8-12.2 V): one law for forward speed AND turn rate.

    wheel speed [m/s] = scale * K_WHEEL * (|motor| - M0)   for |motor| above the dead zone, signed like the motor value, else 0
    motor value       = (command mixed into left / right) * max_speed        (common.mixing.mix, the cap 0.3, then deadzone at min_pwm 0.12, exactly as jetson/robot_udp.py)
    v = (vL + vR) / 2        omega = (vR - vL) / TRACK        (left positive, like w)

Why: the old calibration (v_gain * v, w_gain * w) is right only at command 1.0. The measured steady speeds (marker range fits) at v 0.4 / 0.5 / 0.6 / 0.7 / 0.85 / 1.0 were
0.139 / 0.185 / 0.238 / 0.276 / 0.357 / 0.435 m/s and the turn rates at w 0.4 / 0.5 / 1.0 were 1.98 / 2.62 / 6.27 rad/s: both lie on one wheel law with an offset of about 0.038 motor units
(speed fit 1.64 * (motor - 0.037), turn fit 24.0 * (motor - 0.039) rad/s per unit, which is consistent with a wheel track of 0.137 m). Where it came from and how well it fits: tests/test_wheel_model.py.
CAVEATS: one floor, one battery state (the offset was 0.044 motor units at 10.97-11.3 V: it shrinks as the battery is full), and the tile veers the robot left by tens of degrees (not modelled).
`scale` and `m0` are the knobs an online estimator (sentry/nav/motion_estimator.py) can adjust for the floor and the battery.
"""
from common.mixing import deadzone, mix

K_WHEEL = 1.64          # m/s per motor unit above the offset
M0 = 0.038              # motor units: the wheel offset
TRACK = 0.137           # m between the wheels (fitted from the turn / speed slopes; about 0.128 from the first calibration)


class WheelModel:
    def __init__(self, k=K_WHEEL, m0=M0, track=TRACK, max_speed=0.3, min_pwm=0.12, scale=1.0, k_mix=1.0, w_scale_left=1.0, w_scale_right=1.0, drift_rad_per_m=0.0):
        self.k, self.m0, self.track, self.max_speed, self.min_pwm, self.scale, self.k_mix = k, m0, track, max_speed, min_pwm, scale, k_mix
        # Per-session floor corrections measured with the ArUco boards (tools/motion_check.py): an unlevel floor turns left and right at different rates and bends straight paths.
        self.w_scale_left, self.w_scale_right, self.drift_rad_per_m = w_scale_left, w_scale_right, drift_rad_per_m

    @classmethod
    def from_session(cls, path):
        """The model with the speed scale, the two turn scales and the drift of a calib/motion_session_*.json written by tools.motion_check."""
        import json
        d = json.load(open(path))
        return cls(scale=d["scale"], w_scale_left=d["w_scale_left"], w_scale_right=d["w_scale_right"], drift_rad_per_m=d["drift_rad_per_m"])

    def wheel_speed(self, motor):
        """Signed wheel speed (m/s) for a motor value in [-max_speed, max_speed] (after the dead zone)."""
        m = abs(motor)
        if m < self.min_pwm:
            return 0.0
        s = self.scale * self.k * max(0.0, m - self.m0)
        return s if motor > 0 else -s

    def body_speeds(self, v, w):
        """(forward speed m/s, turn rate rad/s left +) the robot makes for a normalised command (v, w)."""
        left, right = (deadzone(x * self.max_speed, self.min_pwm) for x in mix(v, w, self.k_mix))
        vl, vr = self.wheel_speed(left), self.wheel_speed(right)
        v_m, w_r = (vl + vr) / 2.0, (vr - vl) / self.track
        w_r *= self.w_scale_left if w_r > 0 else self.w_scale_right
        return v_m, w_r + self.drift_rad_per_m * v_m           # the heading changes by drift_rad_per_m per metre driven (left +)
