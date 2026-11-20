"""Find the door anywhere, centre on it, optionally drive to a stand-off, then wait where the robot stands (no declared room, no typed coordinates, no dead-reckoning turn).

The loop is the closed one of tools/approach_door.py (2026-11-11/20: estimate 2.21 vs tape 2.25 m, 2.12 vs 2.11 m): HOLD still for `hold_s` and collect the entrance detector's results -> median bearing and
outline area -> act (a turn pulse, a drive burst, or nothing) -> HOLD again. It MEASURES BEFORE IT MOVES (the first version pulsed first and turned a centred door 23 deg away) and centres on the
DETECTED bearing, never on dead reckoning. The range is the stored enrolment scale (tools.approach_door.reference_scale, `ref_range_m` in entrance.json): range = ref_range * (ref_area / area)^(1/exponent).
`stand_off_m=None`: centre only, no driving. Door not seen in a hold: a short turn pulse (left), at most `search_pulses` of them.
When the door is centred (and the range is at or under the stand-off) the DeployRunner takes over at the current pose: prompt "place the entrance camera", wait for the flag (tower placed + handshake in
tools/deploy_live.py), reverse, STANDBY. Same interface as Phase1Runner / DeployRunner."""
import math
from statistics import median

from sentry.app.deploy_runner import DeployRunner
from sentry.app.phase1_runner import Phase1Runner, Phase1Settings


def polygon_area(quad):
    a = 0.0
    q = [tuple(p) for p in quad]
    for (x0, y0), (x1, y1) in zip(q, q[1:] + q[:1]):
        a += x0 * y1 - x1 * y0
    return abs(a) / 2.0


def decide(bearing_deg, range_m, stand_off_m, tol_deg, aim_deg=0.0):
    """-> 'turn_left' | 'turn_right' | 'drive' | 'done'. Bearing positive = door to the LEFT. Centre first; drive only while farther than the stand-off."""
    b = bearing_deg - aim_deg
    if b > tol_deg:
        return "turn_left"
    if b < -tol_deg:
        return "turn_right"
    if stand_off_m is not None and range_m is not None and range_m > stand_off_m:
        return "drive"
    return "done"


class FindDoorRunner(Phase1Runner):
    def __init__(self, sm, speaker, ref=None, stand_off_m=None, exponent=2.0, deploy_settings=None, settings=None, hold_s=1.5, settle_s=0.5, spin_s=0.2, small_spin_s=0.12,
                 burst_s=0.6, tol_deg=8.0, min_frames=2, search_pulses=15, max_steps=80, aim_deg=0.0, max_start_m=3.5, bound_margin_m=1.0):
        Phase1Runner.__init__(self, sm, speaker, None, None, (0.0, 0.0), (0.0, 0.0), deploy_settings, settings or Phase1Settings(), None)
        if stand_off_m is not None and ref is None:
            raise ValueError("a stand-off needs the enrolment scale (ref = (area_px2, range_m))")
        if not (math.isfinite(exponent) and exponent > 0) or (stand_off_m is not None and not (math.isfinite(stand_off_m) and stand_off_m > 0)):
            raise ValueError("exponent and stand-off must be positive finite numbers")
        if ref is not None and not (ref[0] > 0 and ref[1] > 0):
            raise ValueError("the enrolment scale needs a positive area and range")
        self.ref, self.stand_off_m, self.exponent = ref, stand_off_m, exponent
        self.hold_s, self.settle_s, self.spin_s, self.small_spin_s, self.burst_s = hold_s, settle_s, spin_s, small_spin_s, burst_s
        self.tol_deg, self.min_frames, self.search_pulses, self.max_steps, self.aim_deg = tol_deg, min_frames, search_pulses, max_steps, aim_deg
        self.max_start_m, self.bound_margin_m = max_start_m, bound_margin_m
        self._obs, self._act, self._hold_from, self._now = [], None, None, 0.0     # _now: the control clock; observations arrive from the frames thread and are stamped with it
        self.steps, self.searched, self.measures = 0, 0, []
        self.driven_m, self._start_m, self._last_bearing = 0.0, None, 0.0

    def observe_entrance(self, result, t):
        if result.in_view and result.bearing_rad is not None and getattr(result, "quad", None):
            area = polygon_area(result.quad)
            floor = 0.05 * self.ref[0] if self.ref else 1.0                         # a degenerate or self-intersecting outline has a tiny area: a huge range estimate
            if math.isfinite(area) and area > floor and math.isfinite(result.bearing_rad):
                self._obs.append((self._now, math.degrees(result.bearing_rad), area))

    def range_from_area(self, area):
        return None if self.ref is None else self.ref[1] * (self.ref[0] / area) ** (1.0 / self.exponent)

    def step(self, t, pose, esp_in_view=None):
        self._now = t
        if self.failed:
            return 0.0, 0.0
        if self.phase == "DEPLOY":
            return self.deploy.step(t, pose, esp_in_view)
        if self._act is not None:
            until, v, w = self._act
            if t < until:
                return v, w
            self._act, self._hold_from, self._obs = None, t, []
        if self._hold_from is None:                              # measure BEFORE the first move
            self._hold_from, self._obs = t, []
        if t - self._hold_from < self.hold_s:
            return 0.0, 0.0
        obs = [o for o in self._obs if o[0] >= self._hold_from + self.settle_s]     # frames of the move itself (the detector takes ~0.25 s) are not the door's new bearing
        self._obs, self._hold_from = [], t
        if len(obs) < self.min_frames:                           # door not seen (or too briefly): look toward the side it was last seen
            self.searched += 1
            if self.searched > self.search_pulses:
                self.failed = "door not found: %d search pulses without it in view" % self.search_pulses
                return 0.0, 0.0
            return self._pulse(t, 0.0, -self.ds.w_spin if self._last_bearing < 0 else self.ds.w_spin, self.spin_s)
        bearing, area = median(o[1] for o in obs), median(o[2] for o in obs)
        self._last_bearing = bearing
        rng = self.range_from_area(area)
        act = decide(bearing, rng, self.stand_off_m, self.tol_deg, self.aim_deg)
        self.measures.append((round(t, 2), round(bearing, 1), None if rng is None else round(rng, 2), act))
        self.steps += 1
        if act == "done":
            return self._found(t, pose, math.radians(bearing), rng)
        if self.steps >= self.max_steps:
            self.failed = "stand-off not reached in %d steps (last range %s)" % (self.max_steps, None if rng is None else "%.2f m" % rng)
            return 0.0, 0.0
        if act == "drive":
            from tools.drive_model import drive_distance_m                 # the same worst-case speed model as tools/approach_door.py
            if self._start_m is None:
                self._start_m = min(rng, self.max_start_m)                 # the first CENTRED estimate, capped: an overestimate must not loosen the bound
            self.driven_m += drive_distance_m(self.ds.v_forward, self.burst_s)
            if self.driven_m >= self._start_m - self.stand_off_m + self.bound_margin_m:
                self.failed = "distance bound: about %.1f m driven at the worst-case speed, range estimate still %.2f m" % (self.driven_m, rng)
                return 0.0, 0.0
            return self._pulse(t, self.ds.v_forward, 0.0, self.burst_s)
        w = self.ds.w_spin if act == "turn_left" else -self.ds.w_spin
        return self._pulse(t, 0.0, w, self.spin_s if abs(bearing - self.aim_deg) > 16 else self.small_spin_s)

    def _pulse(self, t, v, w, seconds):
        self._act = (t + seconds, v, w)
        return v, w

    def _found(self, t, pose, bearing, rng):
        self.found_pose = tuple(pose)
        here = (pose[0], pose[1])
        self.deploy = DeployRunner(self.sm, self.speaker, here, (here[0] + math.cos(pose[2]), here[1] + math.sin(pose[2])), self.ds)   # centred on the detected door: it "arrives" at once and the facing turn is ~0
        self.deploy.start(t, bearing)
        self.notes.append("door centred at bearing %.1f deg after %d measurements; range estimate %s" % (math.degrees(bearing), self.steps, "none" if rng is None else "%.2f m" % rng))
        self.phase = "DEPLOY"
        return 0.0, 0.0
