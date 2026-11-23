"""Strike evasion override (Spec 4.5, Implementation Plan Week 8): the highest-priority command of the control path.

On a STRIKE the robot backs away and yaws away from the nearer obstacle side for a fixed time, then ignores new strikes for a cooldown.
The pulse is driven by the WALL CLOCK of the sender, not by the video: a stalled frame must neither stretch nor cut the 400 ms pulse.
v and w are the normalised commands of the control protocol (-1..1); the robot scales them by its own `max_speed` cap and the e-stop / dead-man
still apply, so -1.0 means "full reverse at the cap", not 1 m/s (decision C12, 2026-11-22). Values come from `[state_machine]` in config.toml
(the same ones the state machine uses), never hard-coded here. Pure logic, no sockets: tests/test_evasion.py.
"""


import math
import threading


class EvasionOverride:
    def __init__(self, v=-1.0, w=0.8, duration_s=0.4, cooldown_s=1.0):
        if not (math.isfinite(v) and -1.0 <= v < 0.0):
            raise ValueError("evade v must be a reverse command in [-1, 0), got %r" % (v,))
        if not (math.isfinite(w) and 0.0 < abs(w) <= 1.0):
            raise ValueError("evade |w| must be in (0, 1], got %r" % (w,))
        if not (math.isfinite(duration_s) and 0.0 < duration_s <= 1.0):
            raise ValueError("evade duration must be in (0, 1] s, got %r" % (duration_s,))
        if not (math.isfinite(cooldown_s) and cooldown_s >= 0.0):
            raise ValueError("cooldown must be finite and >= 0, got %r" % (cooldown_s,))
        self.v, self.w, self.duration_s, self.cooldown_s = float(v), abs(float(w)), float(duration_s), float(cooldown_s)
        self._lock = threading.RLock()
        self.start_t = None      # wall time of the running pulse
        self.sign = 1.0
        self.end_t = None        # when the last pulse ended (cooldown reference)
        self.count = 0
        self.rejected = 0

    @classmethod
    def from_toml(cls, config_path=None):
        from sentry.app.state_machine import StateMachineConfig
        from sentry.config import load
        c = StateMachineConfig.from_toml(load(config_path) if config_path else None)
        return cls(c.evade_v, c.evade_w, c.evade_duration_s, c.evade_cooldown_s)

    @staticmethod
    def turn_sign(obstacle_bearing_rad=None):
        """+1 = yaw left, -1 = yaw right, AWAY from the nearer obstacle (bearing > 0 is left, as in the pursuit controller); left when unknown."""
        if obstacle_bearing_rad is None:
            return 1.0
        return -1.0 if obstacle_bearing_rad > 0 else 1.0

    def active(self, now):
        with self._lock:
            return self.start_t is not None and now - self.start_t < self.duration_s

    def in_cooldown(self, now):
        with self._lock:
            return self.end_t is not None and now - self.end_t < self.cooldown_s

    def trigger(self, now, obstacle_bearing_rad=None):
        """STRIKE seen at wall time `now`. True if a pulse starts; False if one is running or the cooldown has not passed."""
        with self._lock:
            self._settle(now)
            if self.active(now) or self.in_cooldown(now):
                self.rejected += 1
                return False
            self.start_t, self.sign = now, self.turn_sign(obstacle_bearing_rad)
            self.count += 1
            return True

    def step(self, now):
        """(v, w) to send at wall time `now` instead of whatever the pursuit computed, or None when no pulse runs."""
        with self._lock:
            self._settle(now)
            if not self.active(now):
                return None
            return self.v, self.sign * self.w

    def _settle(self, now):
        if self.start_t is not None and now - self.start_t >= self.duration_s:
            self.end_t, self.start_t = self.start_t + self.duration_s, None
