"""Phase 1 chain: find the entrance, choose the sweet spot from the declared room, deploy (plan Week 4: 'Phase 1 end to end').

  runner = Phase1Runner(sm, speaker, grid, selector, door_xy, centre_xy)        # grid: sentry.nav.declared_room.declared_grid(...) (+ furniture the detector adds)
  runner.start(t)
  runner.observe_entrance(result, t)       # every robot frame: the EntranceDetector result (in_view, bearing_rad); thread-safe enough (one reference assignment)
  v, w = runner.step(t, pose, esp_in_view) # every control tick, same interface as DeployRunner; runner.failed is a reason string when the run must stop

FIND:   stop-and-look scan: spin a short pulse, hold still for the detector, repeat (a continuous spin at the dead-zone speed, about 2 rad/s, sweeps the door through the view too fast
        for the 3 consecutive in-view frames of EntranceFilter). ENTRANCE_FOUND -> select the best sweet spot that is reachable in a straight line (declared_room.select_reachable) ->
        DEPLOY (DeployRunner on that spot). No entrance within find_timeout_s, or no sweet spot in the declared room: `failed`, the robot stops, nothing is faked.
The door POSITION is declared (tape), the detector only says when the door is in view and in which direction; a bearing that disagrees with the declared door by more than
door_mismatch_deg is recorded in `notes` (the declaration or the detector is wrong) and the run goes on.
"""
from dataclasses import dataclass
import math

from sentry.app.deploy_runner import DeployRunner, DeploySettings, wrap
from sentry.nav.declared_room import select_reachable
from sentry.nav.gridmap import Pose2D
from sentry.perception.entrance import EntranceFilter


@dataclass(frozen=True)
class Phase1Settings:
    spin_s: float = 0.15            # one scan pulse turns the robot about 0.3 rad (20 deg) at the 0.45 spin
    hold_s: float = 0.5             # then hold still: about 10 frames for the detector
    find_timeout_s: float = 45.0    # about two full turns of scanning
    door_mismatch_deg: float = 30.0


class Phase1Runner(object):
    def __init__(self, sm, speaker, grid, selector, door_xy, centre_xy, deploy_settings=None, settings=None, entrance_filter=None):
        self.sm, self.speaker, self.grid, self.selector = sm, speaker, grid, selector
        self.door_xy, self.centre_xy = tuple(door_xy), tuple(centre_xy)
        self.ds = deploy_settings or DeploySettings()
        self.s = settings or Phase1Settings()
        self._ef = entrance_filter or EntranceFilter()
        self.phase = "FIND"
        self.deploy = None
        self.vantage = None
        self.failed = None
        self.notes = []
        self.door_bearing_error_deg = None
        self.found_pose = None
        self._latest, self._seen_t, self._t0 = None, None, 0.0

    # what the tools read (the same names as DeployRunner)
    @property
    def prompts(self):
        return self.deploy.prompts if self.deploy else []

    @property
    def events(self):
        return self.deploy.events if self.deploy else []

    @property
    def log(self):
        return self.deploy.log if self.deploy else []

    def observe_entrance(self, result, t):
        self._latest = (result, t)

    def start(self, t, bearing_rad=None):
        self._t0 = t

    def step(self, t, pose, esp_in_view=None):
        if self.failed:
            return 0.0, 0.0
        if self.phase == "FIND":
            return self._find(t, pose)
        return self.deploy.step(t, pose, esp_in_view)

    def _find(self, t, pose):
        obs = self._latest
        if obs is not None and obs[1] != self._seen_t:              # each robot frame once
            self._seen_t = obs[1]
            event = self._ef.update(obs[0])
            if event and event[0] == "ENTRANCE_FOUND":
                return self._found(t, pose, event[1])
        if t - self._t0 > self.s.find_timeout_s:
            self.failed = "entrance not found: scanned %.0f s without it in view" % self.s.find_timeout_s
            return 0.0, 0.0
        phase_t = (t - self._t0) % (self.s.spin_s + self.s.hold_s)
        return 0.0, (self.ds.w_spin if phase_t < self.s.spin_s else 0.0)

    def _found(self, t, pose, bearing):
        self.found_pose = tuple(pose)
        if bearing is not None:
            to_door = math.atan2(self.door_xy[1] - pose[1], self.door_xy[0] - pose[0])
            self.door_bearing_error_deg = abs(math.degrees(wrap(wrap(pose[2] + bearing) - to_door)))
            if self.door_bearing_error_deg > self.s.door_mismatch_deg:
                self.notes.append("the entrance was seen %.0f deg away from the declared door: check the declaration or the detector" % self.door_bearing_error_deg)
        vp = select_reachable(self.selector, self.grid, self.door_xy, Pose2D(*pose))
        if vp is None:
            self.failed = "no sweet spot in the declared room: none is 1.5-3.0 m (with margin) from the door, in line of sight, and reachable in a straight line"
            return 0.0, 0.0
        self.vantage = vp
        self.deploy = DeployRunner(self.sm, self.speaker, (vp.x_m, vp.y_m), self.centre_xy, self.ds)
        self.deploy.start(t, bearing)
        self.phase = "DEPLOY"
        return 0.0, 0.0
