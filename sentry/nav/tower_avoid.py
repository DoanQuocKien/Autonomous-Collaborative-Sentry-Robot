"""Tower keep-out manoeuvre (2026-11-18, DQK's design): the ESP32 tower carries one 50 mm ArUco marker (ids 10-13) on each face; when one is seen closer than `trigger_m`, the robot
turns until its heading is 90 deg to the line of sight to the tower (away from it), drives `side_m` sideways, turns back to the original heading, drives straight until the tower has been out
of view for `clear_m` of driving AND it has driven past the tower (the distance ahead of it at the trigger plus `clear_m`; the markers are only seen out to about 1 m, so "not seen" alone does not mean "passed"), and hands control back to the caller (pursuit). It is open loop between the turns: at 90 deg off the axis the tower is outside the 160 deg view.

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
from collections import deque
from dataclasses import dataclass

from sentry.config import load
from sentry.nav.wheel_model import WheelModel

IDLE, TURN_AWAY, SIDESTEP, TURN_BACK, CLEAR = "IDLE", "TURN_AWAY", "SIDESTEP", "TURN_BACK", "CLEAR"


@dataclass(frozen=True)
class TowerAvoidConfig:
    trigger_m: float = 0.9              # marker range that starts the manoeuvre (reliably seen out to about 1 m, 0.4 m above the 0.5 m pursuit keep-out)
    confirm_frames: int = 2             # frames inside trigger_m, within the last `window` frames (one noisy PnP range must not start it; a marker at the image edge is only seen every few frames)
    window: int = 6
    side_m: float = 0.8                 # sideways distance
    clear_m: float = 0.4                # driven after the last frame with a tower marker
    max_clear_s: float = 10.0
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
    strategy: str = "steer"            # 'steer' (TowerSteer, closed loop) or 'turn' (TowerAvoid, timed manoeuvre)
    # TowerSteer (closed loop on the marker bearing, below)
    clearance_m: float = 0.35           # keep-out radius round the tower centre: robot half width 0.10 + tower 0.05-0.08 + margin (the tower is 5 x 8 cm)
    margin_deg: float = 10.0            # the tower bearing is steered to asin(clearance / range) + this, on the side away from the robot's path
    steer_v: float = 0.6                # forward command while steering (inner wheel 0.6 - 0.18 = 0.42 stays above the 0.4 dead-zone limit)
    steer_w_max: float = 0.18
    steer_gain: float = 0.6             # w per rad of bearing deficit
    stop_m: float = 0.30                # tower this close and still inside the cone: no forward motion, pivot away
    pivot_w: float = 0.5
    lost_s: float = 0.5                 # marker unseen this long: the run past the tower may end
    pass_clear_m: float = 0.25          # driven beyond the tower's estimated position
    max_total_s: float = 12.0

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
        self._hits, self._since_seen = deque(maxlen=self.cfg.window), 0.0
        self._angle, self._ahead = 0.0, 0.0

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
            self._hits.append(ok)
            if sum(self._hits) < c.confirm_frames or not ok:
                return None
            b = tower[1]
            side = (-1 if b > 0 else 1) if abs(b) >= c.ahead_deg else c.default_side      # turn away from the tower
            turn = (90.0 - abs(b)) if abs(b) >= c.ahead_deg else 90.0                         # heading change that makes the heading 90 deg to the line of sight
            self._angle = side * math.radians(turn)
            self._ahead = max(0.0, tower[0] * math.cos(math.radians(b)))        # how far ahead of the robot the tower is, along the original heading
            self._hits.clear()
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
            passed = self.prog * self.v_m * c.drive_scale >= self._ahead + c.clear_m
            if (passed and self._since_seen >= c.clear_m / (self.v_m * c.drive_scale)) or self.prog >= c.max_clear_s:
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


class TowerSteer:
    """Closed-loop keep-out (2026-11-18, after the timed manoeuvre of TowerAvoid ended 30 deg off its heading and 1.2 m off the line on this floor, whose drift is 40-70 deg per 1.3 m):
    no timed turns and no dead-reckoned angles. While a tower marker is in view the robot keeps driving and steers so that the tower's bearing b stays outside the keep-out cone:
        deficit = (asin(clearance / range) + margin) - sigma * b        sigma = +1 tower on the left (pass it on the right), -1 tower on the right
        w = -sigma * gain * deficit    when deficit > 0, else straight on
    (the idea of VFH's steering sector and Tangent Bug's tangent direction, for one point obstacle). Only the range and bearing of each frame are used, so the floor's drift is corrected by the next frame.
    A dropout (the marker flickers at large bearings) continues the last steering until the bearing deficit of the last sighting is turned (a few degrees), then goes straight. The run ends when the marker has been
    unseen for `lost_s` and the robot has driven the tower's last estimated distance ahead (range * cos(bearing)) plus `pass_clear_m`. Same interface as TowerAvoid:
    step(t, (range_m, bearing_deg) or None, obstacle_m) -> (v, w, phase) while active (STEER / CLEAR), else None."""

    def __init__(self, cfg=None, model=None):
        self.cfg = cfg or TowerAvoidConfig()
        self.model = model or WheelModel()
        c = self.cfg
        for w in (c.steer_w_max, -c.steer_w_max):
            if self.model.body_speeds(c.steer_v, w)[0] <= 0:
                raise ValueError("tower steer: steer_v / steer_w_max put a wheel inside the dead zone")
        if abs(self.model.body_speeds(0.0, c.pivot_w)[1]) <= 0:
            raise ValueError("tower steer: the pivot command is inside the motor dead zone")
        self.events, self.count, self.aborted = [], 0, False
        self.reset()

    def reset(self):
        self.phase, self.t_prev, self.cmd = IDLE, None, (0.0, 0.0)
        self._hits = deque(maxlen=self.cfg.window)
        self._sigma, self._t0, self._t_seen, self._last = 1, 0.0, 0.0, None
        self._w_last, self._to_go, self._deficit_left, self._min_range = 0.0, 0.0, 0.0, None

    @property
    def active(self):
        return self.phase != IDLE

    def _applied(self, t):
        if self.t_prev is None:
            return 0.0
        v, w = self.cmd
        fresh = self.cfg.yaw_pulse_s if (v == 0.0 and w != 0.0) else self.cfg.fresh_s
        return max(0.0, min(t - self.t_prev, fresh))

    def _end(self, t, why):
        self.events.append(dict(t=round(t, 3), event="DONE" if why is None else "ABORT", why=why, seconds=round(t - self._t0, 2),
                                min_range_m=None if self._min_range is None else round(self._min_range, 3)))
        if why is None:
            self.count += 1
        else:
            self.aborted = True
        self.reset()
        self.t_prev = t

    def _steer(self, r, b):
        c = self.cfg
        cone = math.degrees(math.asin(min(1.0, c.clearance_m / max(r, c.clearance_m)))) + c.margin_deg
        deficit = max(0.0, cone - self._sigma * b)
        self._deficit_left = math.radians(deficit)
        self._w_last = -self._sigma * min(c.steer_w_max, c.steer_gain * math.radians(deficit))
        if deficit > 0.0 and r < c.stop_m:
            return 0.0, -self._sigma * c.pivot_w                         # too close and still inside the cone: pivot away, no forward motion
        return c.steer_v, self._w_last

    def step(self, t, tower, obstacle_m=None):
        c = self.cfg
        gap = None if self.t_prev is None else t - self.t_prev
        dt = self._applied(t)
        driven = dt * self.model.body_speeds(*self.cmd)[0]               # metres the previous command moved the robot forward
        turned = dt * abs(self.model.body_speeds(*self.cmd)[1])
        self.t_prev = t
        if self.phase == IDLE:
            ok = tower is not None and tower[0] <= c.trigger_m
            self._hits.append(ok)
            if sum(self._hits) < c.confirm_frames or not ok:
                return None
            r, b = tower
            self._sigma = (1 if b > 0 else -1) if abs(b) >= c.ahead_deg else -c.default_side     # the tower stays on the side it is on; dead ahead: pass on the default side
            self._hits.clear()
            self.aborted = False
            self._t0, self._t_seen, self._last, self._min_range = t, t, (r, b), r
            self._to_go = max(0.0, r * math.cos(math.radians(b))) + c.pass_clear_m
            self.events.append(dict(t=round(t, 3), event="TRIGGER", range_m=round(r, 3), bearing_deg=round(b, 1), tower_side="left" if self._sigma > 0 else "right"))
            self.phase = "STEER"
            self.cmd = self._steer(r, b)
            return self.cmd + (self.phase,)
        if gap is not None and gap > c.max_gap_s:
            self.cmd = (0.0, 0.0)
            self._end(t, "no frame for %.1f s" % gap)
            return 0.0, 0.0, "ABORT"
        if obstacle_m is not None and obstacle_m < c.abort_obstacle_m:
            self.cmd = (0.0, 0.0)
            self._end(t, "obstacle %.2f m" % obstacle_m)
            return 0.0, 0.0, "ABORT"
        if t - self._t0 >= c.max_total_s:
            self.cmd = (0.0, 0.0)
            self._end(t, "time cap %.0f s" % c.max_total_s)
            return 0.0, 0.0, "ABORT"
        if tower is not None:
            r, b = tower
            self._t_seen, self._last, self.phase = t, (r, b), "STEER"
            self._min_range = min(self._min_range, r)
            self._to_go = max(0.0, r * math.cos(math.radians(b))) + c.pass_clear_m
            self.cmd = self._steer(r, b)
            return self.cmd + (self.phase,)
        self._to_go -= driven                                            # no marker this frame
        self._deficit_left -= turned
        unseen = t - self._t_seen
        self.phase = "STEER" if unseen < c.lost_s else "CLEAR"
        if unseen >= c.lost_s and self._to_go <= 0.0:
            self.cmd = (0.0, 0.0)
            self._end(t, None)
            return None                                                  # the caller takes over this very frame
        self.cmd = (c.steer_v, self._w_last if self._deficit_left > 0.0 else 0.0)
        return self.cmd + (self.phase,)


def make_tower_avoid(cfg=None, model=None):
    """'steer' (closed loop on the marker bearing, default) or 'turn' (the timed open-loop manoeuvre)."""
    cfg = cfg or TowerAvoidConfig.from_toml()
    return (TowerSteer if cfg.strategy == "steer" else TowerAvoid)(cfg, model)
