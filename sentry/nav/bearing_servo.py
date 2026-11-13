"""Closed-loop straightening on the bearing of a fixed ArUco board (pure logic, no sockets, no clock, no models).

Why: the open-loop veer of this robot is not constant (-16 .. +83 deg/m measured on 2026-11-11..13, sign included) and the marker's apparent
orientation is too noisy at 2 m (+/-10 deg), but the board's BEARING (its image position) is sub-degree. Three pieces:

* `TurnController`: turn in place by a target angle by watching a static board's bearing (a left turn of theta lowers its left-positive bearing by
  theta). Commands are only 0 or +/-w_spin (both wheels stay above the motor dead zone, as the rest of the project requires); it stops early by the
  distance the robot still turns during the video latency, waits for it to settle, then corrects with short pulses.
* `TrimEstimator`: a scalar Kalman filter for the steering trim (normalised w, added to a straight command) with a variance, updated once per drive
  from the steady value of the bearing PI integral (tools.follow_marker). The variance says how far the carried-over trim can be trusted.
* `heading_entropy_nats`: Gaussian differential entropy 0.5*ln(2*pi*e*sd^2) of bearing samples, a quality measure (lower = straighter). A textbook formula
  chosen here as the measure; no paper using it for odometry calibration was found.
Tested against simulated plants in tests/test_bearing_servo.py.
"""
import math


def wrap_deg(a):
    return (a + 180.0) % 360.0 - 180.0


def heading_entropy_nats(samples_deg, floor_deg=0.05):
    """0.5 ln(2 pi e sd^2) of the samples (degrees); sd is floored so a perfectly still signal does not give -inf."""
    n = len(samples_deg)
    if n < 2:
        raise ValueError("need at least 2 samples")
    mean = sum(samples_deg) / n
    sd = max(math.sqrt(sum((x - mean) ** 2 for x in samples_deg) / n), floor_deg)
    return 0.5 * math.log(2.0 * math.pi * math.e * sd * sd)


class TrimEstimator(object):
    """Kalman filter for the steering trim: x = trim (normalised w), random walk between drives, one noisy measurement per drive."""

    def __init__(self, trim0=0.0, std0=0.03, q_std=0.01, r_floor=0.003):
        if std0 <= 0 or q_std < 0 or r_floor <= 0:
            raise ValueError("std0 and r_floor must be positive, q_std non-negative")
        self.trim, self.var, self.q, self.r_floor = float(trim0), float(std0) ** 2, float(q_std) ** 2, float(r_floor)
        self.updates = 0

    @property
    def std(self):
        return math.sqrt(self.var)

    def predict(self):
        """The veer may have changed since the last drive."""
        self.var += self.q

    def update(self, z, r_std=0.0):
        """z: the trim measured over one drive (normalised w); r_std: the spread of that measurement (floored). -> the gain used."""
        if not math.isfinite(z):
            raise ValueError("measurement must be finite")
        r2 = max(float(r_std), self.r_floor) ** 2
        k = self.var / (self.var + r2)
        self.trim += k * (z - self.trim)
        self.var *= (1.0 - k)
        self.updates += 1
        return k


class TurnController(object):
    """Turn in place by `target_deg` (left +) watching a static board. step(t, bearing_deg) -> (w, done). bearing_deg is None when the board is not seen."""
    SPIN, SETTLE, PULSE, DONE = "SPIN", "SETTLE", "PULSE", "DONE"

    def __init__(self, target_deg, w_spin=0.45, tol_deg=5.0, rate_deg_s=120.0, latency_s=0.25, settle_s=0.4, min_pulse_s=0.12, max_pulses=3, lost_s=1.0, max_target_deg=70.0):
        if not 0.0 < abs(target_deg) <= max_target_deg:
            raise ValueError("target must be within (0, %.0f] deg: the board must stay in view" % max_target_deg)
        self.target, self.w_spin, self.tol, self.rate = float(target_deg), float(w_spin), float(tol_deg), float(rate_deg_s)
        self.latency, self.settle_s, self.min_pulse_s, self.max_pulses, self.lost_s = float(latency_s), float(settle_s), float(min_pulse_s), int(max_pulses), float(lost_s)
        self.state, self.b0, self.t_state, self.pulses, self.pulse_s = self.SPIN, None, None, 0, 0.0
        self.progress, self.error, self.reason, self._last_seen, self._err_before = 0.0, self.target, None, None, self.target

    @property
    def resolution_deg(self):
        """Smallest error worth correcting: a minimum pulse turns rate*min_pulse_s, so a pulse at a smaller error would overshoot by more than it fixes."""
        return max(self.tol, 0.5 * self.rate * self.min_pulse_s)

    def _enter(self, state, t):
        self.state, self.t_state = state, t

    def step(self, t, bearing_deg):
        if self.state == self.DONE:
            return 0.0, True
        if bearing_deg is not None:
            if self.b0 is None:
                self.b0, self._last_seen = bearing_deg, t
                self.t_state = t
            self._last_seen = t
            self.progress = -wrap_deg(bearing_deg - self.b0)       # a left turn lowers the left-positive bearing of a static board
            self.error = self.target - self.progress
        if self.b0 is None or t - self._last_seen > self.lost_s:
            if self.b0 is not None:
                self.reason = "board lost"
                self._enter(self.DONE, t)
            return 0.0, self.state == self.DONE
        sign = 1.0 if self.error >= 0 else -1.0
        if self.state == self.SPIN:
            if self.error * (1.0 if self.target > 0 else -1.0) <= self.rate * self.latency:       # the robot keeps turning for the video latency + command lag + coast (latency_s is the sum)
                self._enter(self.SETTLE, t)
                return 0.0, False
            return (1.0 if self.target > 0 else -1.0) * self.w_spin, False
        if self.state == self.SETTLE:
            if t - self.t_state < self.settle_s:
                return 0.0, False
            no_gain = self.pulses > 0 and abs(self.error) >= abs(self._err_before) - 1.0      # the last pulse did not help: it is bigger than the error left
            if abs(self.error) <= self.resolution_deg or self.pulses >= self.max_pulses or no_gain:
                self.reason = "ok" if abs(self.error) <= self.resolution_deg else "residual %.1f deg after %d pulses" % (self.error, self.pulses)
                self._enter(self.DONE, t)
                return 0.0, True
            self._err_before = self.error
            self.pulses += 1
            self.pulse_s = max(self.min_pulse_s, abs(self.error) / self.rate)
            self._pulse_sign = sign
            self._enter(self.PULSE, t)
        if self.state == self.PULSE:
            if t - self.t_state < self.pulse_s:
                return self._pulse_sign * self.w_spin, False
            self._enter(self.SETTLE, t)
        return 0.0, False
