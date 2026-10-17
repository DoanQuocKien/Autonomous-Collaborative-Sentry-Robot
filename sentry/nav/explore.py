"""Phase 1 exploration policy: drive forward, steer away from obstacles, spin in place when blocked, stay inside a box.

Pure logic (no sockets, no clock, no models): the caller passes the detector result, the dead-reckoned pose and dt, and gets a
normalised (v, w) back (w positive turns left, the convention of the whole project). `tools/explore_live.py` wires it to the robot.

Safety rules baked in (tests/test_explore.py checks them):
* every command either stops, or keeps BOTH wheels above the motor dead zone (below it a wheel only whines and veers);
* an obstacle WITHOUT a distance (chair on a glossy floor, `reflection_unresolved`, issue #43; truncated boxes) is not ignored:
  it blocks the way when its box reaches low in the image (it is close) or touches the image border;
* no detector result (no frame, exception) -> stop; spinning for too long -> stop; run time and the box limit the run.
Not covered: walls and objects the detector does not know (the detector only knows furniture classes): the operator holds R1 and
the box keeps the run in a cleared area.
"""
from collections import namedtuple
from dataclasses import dataclass
import math
import random

from common.mixing import mix

Command = namedtuple("Command", "v w state reason")


@dataclass(frozen=True)
class ExploreSettings:
    v_forward: float = 0.55       # normalised; at the 0.3 speed cap v < 0.4 is a clean stop (dead zone), 0.55 is about 0.2 m/s measured
    w_spin: float = 0.45          # spin in place; each wheel 0.45 > the dead-zone value 0.4
    stop_m: float = 0.55          # a resolved obstacle nearer than this blocks the way (config obstacle_explore_m = 0.6 starts the steering)
    unresolved_bottom: float = 0.55   # an unresolved box reaching below this fraction of the image height is treated as near
    clear_frames: int = 6         # consecutive clear frames before a spin ends (hysteresis, about 0.3 s)
    box_half_m: float = 1.5       # stay within +/- this of the start position (dead reckoning, so soft)
    return_tol_deg: float = 25.0  # heading error to the box centre above which the robot spins instead of steering
    max_spin_s: float = 8.0       # spinning longer than this without a clear view = stuck: stop
    max_time_s: float = 180.0
    min_pwm: float = 0.12
    max_speed: float = 0.3

    @property
    def dead(self):
        return self.min_pwm / self.max_speed       # smallest normalised wheel value that turns the motor

    @property
    def w_forward_max(self):
        """Steering while driving: the slower wheel must stay above the dead zone."""
        return max(0.0, self.v_forward - self.dead - 0.01)


def wrap(a):
    return math.atan2(math.sin(a), math.cos(a))


def fresh_command(v, w, t_set, now, max_age=0.25):
    """The command to put on the wire: the last one while it is fresh, a stop once the control loop has stalled
    (the robot's own watchdog is 0.3 s, but a repeated stale command would keep it driving; this makes the sender stop first)."""
    return (v, w) if now - t_set <= max_age else (0.0, 0.0)


def legal(cmd, s):
    """True when the command stops, or every wheel it asks for turns (above the dead zone)."""
    if cmd.v == 0.0 and cmd.w == 0.0:
        return True
    left, right = mix(cmd.v, cmd.w)
    return abs(left) >= s.dead - 1e-9 and abs(right) >= s.dead - 1e-9 and abs(cmd.v) <= 1 and abs(cmd.w) <= 1


class Explorer:
    def __init__(self, settings=None, image_size=(640, 480), seed=0):
        self.s = settings or ExploreSettings()
        self.image_w, self.image_h = image_size
        self.rng = random.Random(seed)             # only breaks the tie when an obstacle is exactly centred
        self.state, self.spin_dir, self.clear, self.spin_t, self.t = "FORWARD", 0, 0, 0.0, 0.0

    # -- what is in the way ----------------------------------------------------------------------------------
    def blocking(self, obs):
        """-> (blocked, side) with side +1 when the nearest blocker is on the LEFT (so the robot turns right), -1 right, 0 centre."""
        best = None                                            # (rank, side): smaller rank = more urgent
        for o in obs.obstacles:
            if o.ground is not None:
                if o.ground.distance_m < self.s.stop_m:
                    side = 1 if o.ground.left_m > 0 else -1 if o.ground.left_m < 0 else 0
                    if best is None or o.ground.distance_m < best[0]:
                        best = (o.ground.distance_m, side)
                continue
            x0, y0, x1, y1 = o.detection.xyxy
            rejected_near = o.rejection in ("bottom_truncated", "border_truncated")
            if rejected_near or y1 >= self.s.unresolved_bottom * self.image_h:
                side = 1 if (x0 + x1) / 2 < self.image_w / 2 else -1
                rank = 0.0                                     # no distance: treat as the most urgent, it may be very close
                if best is None or rank < best[0]:
                    best = (rank, side)
        return (best is not None), (best[1] if best else 0)

    # -- one control step ----------------------------------------------------------------------------------
    def step(self, obs, pose, dt):
        """obs: ObstacleResult, or None when there is no usable detector result. pose: (x, y, yaw) from dead reckoning."""
        s = self.s
        self.t += dt
        if obs is None:
            return self._stop("no_frame")
        if self.t > s.max_time_s:
            return self._stop("time")
        blocked, side = self.blocking(obs)
        if blocked and self.state != "TURN":
            self.state = "TURN"
            self.spin_dir = -side if side else self.rng.choice((-1, 1))     # obstacle on the left -> spin right (w < 0)
            self.clear, self.spin_t = 0, 0.0
        if self.state == "TURN":
            self.spin_t += dt
            self.clear = 0 if blocked else self.clear + 1
            if self.clear >= s.clear_frames:
                self.state = "FORWARD"
            elif self.spin_t > s.max_spin_s:
                return self._stop("stuck")
            else:
                return Command(0.0, self.spin_dir * s.w_spin, "TURN", "blocked")
        x, y, yaw = pose
        if max(abs(x), abs(y)) > s.box_half_m:                  # outside the box: face the centre before driving on
            err = wrap(math.atan2(-y, -x) - yaw)
            if abs(err) > math.radians(s.return_tol_deg):
                return Command(0.0, (1 if err > 0 else -1) * s.w_spin, "RETURN", "outside_box")
            w = max(-s.w_forward_max, min(s.w_forward_max, 0.8 * err))
            return Command(s.v_forward, w, "RETURN", "outside_box")
        w = max(-s.w_forward_max, min(s.w_forward_max, obs.repulsive_w))   # repulsive_w: left obstacle -> negative (right turn)
        return Command(s.v_forward, w, "FORWARD", "clear" if w == 0 else "steer")

    def _stop(self, reason):
        return Command(0.0, 0.0, "STOP", reason)
