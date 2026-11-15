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
    """Turn in place by `target_deg` (left +) in pulses, measuring the bearing of a static board only AT REST (the camera is blind while the robot spins: motion blur,
    measured 2026-11-13: sharpness 200 -> 8-33 and no detection from 0.15 s after the start until 0.2 s after the stop).

    step(t, bearing_deg) -> (w, done); bearing_deg is None when there is no new observation. Each pulse is a spin at +/-w_spin (above the dead zone) of a length chosen from
    the learned gain `rate_deg_s` (degrees per second of pulse, including the start-up lag; updated from every pulse), followed by a rest of `settle_s` before the next
    observation is accepted. Ends when the error is below the pulse resolution, when a pulse did not help, after `max_pulses`, or when no observation arrives."""
    PULSE, SETTLE, DONE = "PULSE", "SETTLE", "DONE"

    def __init__(self, target_deg, w_spin=0.45, tol_deg=5.0, rate_deg_s=120.0, settle_s=0.35, min_pulse_s=0.12, max_pulse_s=0.30, aim=0.8, learn=0.5, max_pulses=6, lost_s=2.0, max_target_deg=70.0):
        if not 0.0 < abs(target_deg) <= max_target_deg:
            raise ValueError("target must be within (0, %.0f] deg: the board must stay in view" % max_target_deg)
        self.target, self.w_spin, self.tol, self.rate = float(target_deg), float(w_spin), float(tol_deg), float(rate_deg_s)
        self.settle_s, self.min_pulse_s, self.max_pulse_s, self.aim, self.learn = float(settle_s), float(min_pulse_s), float(max_pulse_s), float(aim), float(learn)
        self.max_pulses, self.lost_s = int(max_pulses), float(lost_s)
        self.b0, self.progress, self.error, self.reason = None, 0.0, self.target, None
        self.state, self.t_state, self.pulses, self.pulse_s, self._dir = self.SETTLE, None, 0, 0.0, 1.0
        self._prog_before, self._err_before, self._worse = 0.0, self.target, 0

    @property
    def resolution_deg(self):
        """Smallest error worth a correction: a minimum pulse turns rate*min_pulse_s, so a pulse at a smaller error would overshoot by more than it fixes."""
        return max(self.tol, 0.5 * self.rate * self.min_pulse_s)

    def _finish(self, t, reason):
        self.reason, self.state = reason, self.DONE
        return 0.0, True

    def step(self, t, bearing_deg):
        if self.state == self.DONE:
            return 0.0, True
        if self.t_state is None:
            self.t_state = t
        if self.state == self.PULSE:
            if t - self.t_state < self.pulse_s:
                return self._dir * self.w_spin, False
            self.state, self.t_state = self.SETTLE, t                       # blind until the blur has cleared
            return 0.0, False
        if bearing_deg is None or t - self.t_state < self.settle_s:
            if t - self.t_state > self.settle_s + self.lost_s:
                return self._finish(t, "board lost")
            return 0.0, False
        if self.b0 is None:
            self.b0 = bearing_deg
        self.progress = -wrap_deg(bearing_deg - self.b0)                     # a left turn lowers the left-positive bearing of a static board
        self.error = self.target - self.progress
        if self.pulses > 0:                                                  # learn the gain from the pulse just made
            moved = self.progress - self._prog_before
            if self.pulse_s > 0 and moved * self._dir > 0:
                self.rate = (1.0 - self.learn) * self.rate + self.learn * abs(moved) / self.pulse_s
            self._worse = self._worse + 1 if abs(self.error) >= abs(self._err_before) - 1.0 else 0
        if abs(self.error) <= self.resolution_deg:
            return self._finish(t, "ok")
        if self.pulses >= self.max_pulses or self._worse >= 2:
            return self._finish(t, "residual %.1f deg after %d pulses" % (self.error, self.pulses))
        self._prog_before, self._err_before = self.progress, self.error
        self._dir = 1.0 if self.error > 0 else -1.0
        self.pulse_s = min(self.max_pulse_s, max(self.min_pulse_s, self.aim * abs(self.error) / self.rate))
        self.pulses += 1
        self.state, self.t_state = self.PULSE, t
        return self._dir * self.w_spin, False
