"""Tower keep-out manoeuvre (2026-11-18, DQK's design): the ESP32 tower carries one 50 mm ArUco marker (ids 10-13) on each face; when one is seen closer than `trigger_m`, the robot
turns until its heading is 90 deg to the line of sight to the tower (away from it), drives `side_m` sideways, turns back to the original heading, drives straight until the tower has been out
of view for `clear_m` of driving, and hands control back to the caller (pursuit). It is open loop between the turns: at 90 deg off the axis the tower is outside the 160 deg view.

    ta = TowerAvoid()
    out = ta.step(t, (range_m, bearing_deg) or None, obstacle_m)       # every frame
    if out is not None: v, w, phase = out                              # override: send it instead of the pursuit command
    # None: not avoiding, the caller's own command applies

Each phase advances by the time its command was really on the wire (the sender repeats a command at most `fresh_s`, a yaw-only one `yaw_pulse_s`, as tools.pursue_live), so a slow
video frame does not change the angle turned. `turn_scale` / `drive_scale` are the floor knobs: angle turned / angle asked, distance driven / distance asked, measured on the floor
(tools.tower_marker_trial avoid, tape and the start / end bearing of the tower); the wheel model gives the nominal rates. Bearing is left positive, like w.
Safety: an obstacle closer than `abort_obstacle_m` while driving forward, or no frame for `max_gap_s`, ends the manoeuvre with a stop (`aborted`, `done` set).
"""
import math
from dataclasses import dataclass

from sentry.config import load
from sentry.nav.wheel_model import WheelModel

IDLE, TURN_AWAY, SIDESTEP, TURN_BACK, CLEAR = "IDLE", "TURN_AWAY", "SIDESTEP", "TURN_BACK", "CLEAR"


@dataclass(frozen=True)
class TowerAvoidConfig:
    trigger_m: float = 0.9              # marker range that starts the manoeuvre (reliably seen out to about 1 m, 0.4 m above the 0.5 m pursuit keep-out)
    confirm_frames: int = 2             # consecutive frames inside trigger_m (one noisy PnP range must not start it)
    side_m: float = 0.8                 # sideways distance
    clear_m: float = 0.4                # driven after the last frame with a tower marker
    max_clear_s: float = 8.0
    turn_w: float = 0.5                 # |w| of the turns (0.45 is the smallest legal turn)
    drive_v: float = 0.5                # v of the sidestep and the clearing run
    turn_scale: float = 1.0
    drive_scale: float = 1.0
    abort_obstacle_m: float = 0.35      # = [pursuit] obstacle_critical_m
    default_side: int = -1              # tower dead ahead (|bearing| < ahead_deg): -1 = turn right, +1 = left
    ahead_deg: float = 3.0
    fresh_s: float = 0.25
    yaw_pulse_s: float = 0.08
    max_gap_s: float = 1.0

    @classmethod
    def from_toml(cls):
        raw = load().get("tower", {})
        return cls(**{k: type(getattr(cls, k))(v) for k, v in raw.items() if k in cls.__dataclass_fields__})


class TowerAvoid:
    def __init__(self, cfg=None, model=None):
        self.cfg = cfg or TowerAvoidConfig()
        self.model = model or WheelModel()
        self.v_m = self.model.body_speeds(self.cfg.drive_v, 0.0)[0]
        self.w_r = abs(self.model.body_speeds(0.0, self.cfg.turn_w)[1])
        if self.v_m <= 0 or self.w_r <= 0:
            raise ValueError("tower avoid: the drive or turn command is inside the motor dead zone")
        self.events = []                                  # dicts: t, event, ...
        self.count = 0
        self.aborted = False
        self.reset()

    def reset(self):
        self.phase, self.prog, self.t_prev, self.cmd = IDLE, 0.0, None, (0.0, 0.0)
        self._seen, self._since_seen = 0, 0.0
        self._angle, self._first = 0.0, None

    @property
    def active(self):
        return self.phase != IDLE

    def _applied(self, t):
        """Seconds the previous command was on the wire since the last step."""
        if self.t_prev is None:
            return 0.0
        v, w = self.cmd
        fresh = self.cfg.yaw_pulse_s if (v == 0.0 and w != 0.0) else self.cfg.fresh_s
        return max(0.0, min(t - self.t_prev, fresh))

    def _go(self, phase, t, **info):
        self.phase, self.prog = phase, 0.0
        self.events.append(dict(t=round(t, 3), event=phase, **info))

    def _finish(self, t, why):
        self.events.append(dict(t=round(t, 3), event="DONE" if why is None else "ABORT", why=why))
        if why is None:
            self.count += 1
        else:
            self.aborted = True
        self.reset()
        self.t_prev = t

    def step(self, t, tower, obstacle_m=None):
        """tower: (range_m, bearing_deg) of the nearest tower marker in this frame, or None. -> (v, w, phase) while avoiding, else None."""
        c = self.cfg
        gap = None if self.t_prev is None else t - self.t_prev
        dt = self._applied(t)
        self.t_prev = t
        if self.phase == IDLE:
            ok = tower is not None and tower[0] <= c.trigger_m
            self._seen = self._seen + 1 if ok else 0
            if self._seen < c.confirm_frames:
                return None
            b = tower[1]
            side = (-1 if b > 0 else 1) if abs(b) >= c.ahead_deg else c.default_side      # turn away from the tower
            turn = (90.0 - abs(b)) if abs(b) >= c.ahead_deg else 90.0                         # heading change that makes the heading 90 deg to the line of sight
            self._angle = side * math.radians(turn)
            self._seen = 0
            self.aborted = False
            self._go(TURN_AWAY, t, range_m=round(tower[0], 3), bearing_deg=round(b, 1), turn_deg=round(math.degrees(self._angle), 1))
            self.cmd = (0.0, math.copysign(c.turn_w, self._angle))
            return self.cmd + (self.phase,)
        if gap is not None and gap > c.max_gap_s:
            self.cmd = (0.0, 0.0)
            self._finish(t, "no frame for %.1f s" % gap)
            return 0.0, 0.0, "ABORT"
        self.prog += dt
        if self.phase == TURN_AWAY and self.prog >= abs(self._angle) / (self.w_r * c.turn_scale):
            self._go(SIDESTEP, t)
        elif self.phase == SIDESTEP and self.prog >= c.side_m / (self.v_m * c.drive_scale):
            self._go(TURN_BACK, t)
        elif self.phase == TURN_BACK and self.prog >= abs(self._angle) / (self.w_r * c.turn_scale):
            self._go(CLEAR, t)
            self._since_seen = 0.0
        elif self.phase == CLEAR:
            self._since_seen = 0.0 if tower is not None else self._since_seen + dt
            if self._since_seen >= c.clear_m / (self.v_m * c.drive_scale) or self.prog >= c.max_clear_s:
                self.cmd = (0.0, 0.0)
                self._finish(t, None)
                return None                                    # caller takes over this very frame
        if self.phase in (SIDESTEP, CLEAR) and obstacle_m is not None and obstacle_m < c.abort_obstacle_m:
            self.cmd = (0.0, 0.0)
            self._finish(t, "obstacle %.2f m" % obstacle_m)
            return 0.0, 0.0, "ABORT"
        if self.phase == TURN_AWAY:
            self.cmd = (0.0, math.copysign(c.turn_w, self._angle))
        elif self.phase == TURN_BACK:
            self.cmd = (0.0, -math.copysign(c.turn_w, self._angle))
        else:
            self.cmd = (c.drive_v, 0.0)
        return self.cmd + (self.phase,)
