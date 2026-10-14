"""Online speed and heading-drift estimation from an ArUco marker's range and bearing (dynamic motion tuning).

Why: the speed per command depends on the floor (2026-10-14/15: about 0.8 of the glossy-floor values on a rugged floor) and is not proportional to the command, and the heading drift changed from
-0.19 rad/m (right, smooth floor, v = 1.0) to strong left turns (rugged floor). A fixed calibration cannot be right everywhere, so the gains are re-estimated whenever a marker is in view.

Model (prior from the marker fits of the classroom drive runs plus the cafe gain at v = 1.0): speed [m/s] = scale * slope * (|v| - v0) for |v| >= v_min, else 0 (below v_min = min_pwm / max_speed
the robot stands still). `scale` is the floor factor estimated online; `drift_rad_per_s` (left +) is the heading rate the commands did NOT ask for; `startup_lag_s` is the time from the command to the first real motion (it explains why a 4 s drive from rest averages less than the steady speed).

Use: feed every frame in which the marker was seen, with the command that was applied then:
    est = MotionEstimator()
    est.observe(t, range_m, bearing_rad, v_cmd, w_cmd)        # bearing positive = marker to the left; range = floor-plane distance camera -> marker
    est.speed(v)                                              # predicted forward speed for a command, with the current scale
A drive segment (constant v, small w) is closed when the command drops below v_min or changes; it updates the estimates only if it was long enough, steady (low fit error) and plausible.
Heading: the marker's bearing b changes at db/dt = -omega + s * sin(b) / r (omega = heading rate, left +, s = speed, r = range), so omega = -db/dt + s sin(b) / r. No marker orientation is used
(the orientation of a small marker is noisy beyond about 1.5 m).
"""
import math


class MotionEstimator:
    def __init__(self, slope=0.48, v0=0.146, v_min=0.4, w_gain=6.48, settle_s=0.6, min_span_s=0.8, min_samples=6,
                 beta=0.35, scale_limits=(0.5, 1.5), ratio_limits=(0.3, 1.7), max_rms_m=0.04, max_w=0.05):
        self.slope, self.v0, self.v_min, self.w_gain = slope, v0, v_min, w_gain
        self.settle_s, self.min_span_s, self.min_samples, self.beta = settle_s, min_span_s, min_samples, beta
        self.scale_limits, self.ratio_limits, self.max_rms_m, self.max_w = scale_limits, ratio_limits, max_rms_m, max_w
        self.scale = 1.0
        self.drift_rad_per_s = 0.0
        self.startup_lag_s = 0.0                        # time from the command to the first real motion (static friction); the average speed of a short drive from rest is lower by lag / duration
        self.updates = 0
        self._seg = []                                  # (t, range, bearing, v, w) of the open segment

    def speed(self, v, scale=None):
        """Predicted forward speed (m/s, signed like v) for a normalised command."""
        a = abs(v)
        if a < self.v_min:
            return 0.0
        s = self.scale if scale is None else scale
        return math.copysign(s * self.slope * (a - self.v0), v)

    def observe(self, t, range_m, bearing_rad, v_cmd, w_cmd=0.0):
        """One marker sighting. -> the dict of new estimates when a segment just closed and updated them, else None."""
        if v_cmd >= self.v_min and abs(w_cmd) <= self.max_w:
            if self._seg and abs(self._seg[-1][3] - v_cmd) > 0.02:
                done = self._finish()
                self._seg = []
            else:
                done = None
            self._seg.append((t, range_m, bearing_rad, v_cmd, w_cmd))
            return done
        done = self._finish()
        self._seg = []
        return done

    def finish(self):
        """Close the open segment (e.g. when the marker is lost or the robot stops)."""
        done = self._finish()
        self._seg = []
        return done

    def _lag(self):
        """Seconds from the first command of the segment to the first sample whose range fell 4 cm below the standing range (None when the segment began with the robot already moving or never moved)."""
        seg = self._seg
        if len(seg) < 6:
            return None
        base = sorted(p[1] for p in seg[:3])[1]
        for i in range(len(seg) - 1):
            if seg[i][1] <= base - 0.04 and seg[i + 1][1] <= base - 0.04:
                return seg[i][0] - seg[0][0] if i >= 2 else None
        return None

    def _finish(self):
        if not self._seg:
            return None
        t0 = self._seg[0][0]
        pts = [p for p in self._seg if p[0] >= t0 + self.settle_s]
        if len(pts) < self.min_samples or pts[-1][0] - pts[0][0] < self.min_span_s:
            return None
        n = len(pts)
        mt = sum(p[0] for p in pts) / n
        mr = sum(p[1] for p in pts) / n
        sxx = sum((p[0] - mt) ** 2 for p in pts)
        slope = sum((p[0] - mt) * (p[1] - mr) for p in pts) / sxx                  # range slope (m/s), negative = approaching
        rms = math.sqrt(sum((p[1] - (mr + slope * (p[0] - mt))) ** 2 for p in pts) / n)
        measured = -slope
        v = sum(p[3] for p in pts) / n
        w = sum(p[4] for p in pts) / n
        prior = self.slope * (v - self.v0)
        if measured <= 0.02 or rms > self.max_rms_m or prior <= 0:
            return None
        ratio = measured / prior
        if not self.ratio_limits[0] <= ratio <= self.ratio_limits[1]:
            return None                                                             # not plausible: a bump, a lost track, a nudge
        lag = self._lag()
        b = sum(p[2] for p in pts) / n
        db = (sum(p[2] for p in pts[-3:]) / len(pts[-3:]) - sum(p[2] for p in pts[:3]) / len(pts[:3])) / max(
            sum(p[0] for p in pts[-3:]) / len(pts[-3:]) - sum(p[0] for p in pts[:3]) / len(pts[:3]), 1e-6)
        omega = -db + measured * math.sin(b) / max(mr, 0.3)                          # heading rate (rad/s, left +)
        drift = omega - self.w_gain * w                                              # the part the commands did not ask for
        beta = 1.0 if self.updates == 0 else self.beta
        self.scale = min(max((1 - beta) * self.scale + beta * ratio, self.scale_limits[0]), self.scale_limits[1])
        self.drift_rad_per_s = (1 - beta) * self.drift_rad_per_s + beta * drift
        if lag is not None:
            self.startup_lag_s = (1 - beta) * self.startup_lag_s + beta * lag if self.updates else lag
        self.updates += 1
        return {"startup_lag_s": lag, "scale": self.scale, "ratio": ratio, "speed": measured, "drift_rad_per_s": self.drift_rad_per_s, "drift_rad_per_m": drift / measured, "rms_m": rms, "samples": n}
