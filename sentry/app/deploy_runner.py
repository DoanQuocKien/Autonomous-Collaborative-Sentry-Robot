"""Phase 1 deployment runner: drives the state machine from the robot's pose and the ESP32 handshake (plan: deployment behaviour, Week 3-4).

The state machine (state_machine.py) is event driven: ENTRANCE_FOUND -> APPROACH_VANTAGE -> VANTAGE_REACHED -> WAIT_CAMERA (prompt, face the room centre) ->
ESP32_VERIFIED -> RETRACT (back up for retract_duration_s) -> STANDBY. Nothing produced those events from motion and from the camera; this does:

  runner = DeployRunner(StateMachine(...), speaker, vantage_xy=(x, y), centre_xy=(x, y))   # speaker: AudioPromptPlayer(sender=LocalSpeaker()) or anything with play(clip)
  runner.start(t, bearing_rad)             # the entrance was found (sentry/perception/entrance.py)
  v, w = runner.step(t, pose, esp_in_view)   # every control tick (30 Hz): pose = (x, y, yaw) in the map frame, esp_in_view = the handshake detector's result for the newest ESP32 frame or None

Pure logic (no sockets, no clock): tools/deploy_live.py supplies the dead-reckoned pose and the handshake flags and sends (v, w) to the robot through the e-stop interlock.
MOTOR DEAD ZONE: every command either stops or keeps BOTH wheels at or above dead = min_pwm / max_speed = 0.4 (below it a wheel only whines and veers), exactly like
sentry/nav/explore.py: so there is no proportional speed and no slow turn: forward v 0.55 (about 0.2 m/s), steering limited to what the slower wheel allows, spins at 0.45
(about 2 rad/s, so the control loop must run at 30 Hz: one tick turns the robot about 0.07 rad, inside the facing tolerance). The state machine's own approach command (straight
ahead, steered by the entrance bearing) is replaced by a go-to controller on the vantage point; its timeouts still apply (approach 30 s -> back to EXPLORE, handshake 60 s -> prompt
again, retract by time). No obstacle avoidance here: the live tool stops the run when the detector sees a blocker, and the operator holds R1.
"""
from dataclasses import dataclass
import math

from sentry.app.state_machine import State


def wrap(a):
    return math.atan2(math.sin(a), math.cos(a))


@dataclass(frozen=True)
class DeploySettings:
    v_forward: float = 0.55        # normalised; about 0.2 m/s measured (explore.py)
    w_spin: float = 0.45           # spin in place; each wheel 0.45 > the dead-zone value 0.4
    min_pwm: float = 0.12
    max_speed: float = 0.3
    tol_m: float = 0.12            # arrived when this close to the vantage point (dead reckoning is only indicative: +-10 deg per metre)
    turn_only_rad: float = 0.5     # heading error above which the robot spins instead of driving (about 29 deg)
    face_tol_rad: float = 0.12     # facing the room centre: a spin tick turns about 0.07 rad at 30 Hz, so this cannot oscillate
    verify_frames: int = 3         # consecutive in-view frames of the handshake detector (EntranceConfig.enter_frames)

    @property
    def dead(self):
        return self.min_pwm / self.max_speed

    @property
    def w_forward_max(self):
        """Steering while driving: the slower wheel must stay above the dead zone."""
        return max(0.0, self.v_forward - self.dead - 0.01)


def goto_command(pose, goal_xy, s=None):
    """pose (x, y, yaw) -> (v, w, arrived). Spins while the heading error exceeds turn_only_rad, otherwise drives at v_forward and steers within what the dead zone allows."""
    s = s or DeploySettings()
    dx, dy = goal_xy[0] - pose[0], goal_xy[1] - pose[1]
    if math.hypot(dx, dy) <= s.tol_m:
        return 0.0, 0.0, True
    err = wrap(math.atan2(dy, dx) - pose[2])
    if abs(err) > s.turn_only_rad:
        return 0.0, (s.w_spin if err > 0 else -s.w_spin), False
    return s.v_forward, max(-s.w_forward_max, min(s.w_forward_max, err)), False


def servo_command(rng_m, bearing_rad, stop_m, s=None, kp=1.0):
    """Drive at a board that is in view: (v, w, arrived) from its range and bearing (left +). Spins while it is more than turn_only_rad off the heading, otherwise drives and steers by the bearing."""
    s = s or DeploySettings()
    if rng_m <= stop_m:
        return 0.0, 0.0, True
    if abs(bearing_rad) > 0.35:
        return 0.0, (s.w_spin if bearing_rad > 0 else -s.w_spin), False
    return s.v_forward, max(-s.w_forward_max, min(s.w_forward_max, kp * bearing_rad)), False


def face_command(pose, target_xy, s=None):
    """Spin in place toward target_xy. -> (w, done)."""
    s = s or DeploySettings()
    err = wrap(math.atan2(target_xy[1] - pose[1], target_xy[0] - pose[0]) - pose[2])
    if abs(err) <= s.face_tol_rad:
        return 0.0, True
    return (s.w_spin if err > 0 else -s.w_spin), False


class DeployRunner(object):
    def __init__(self, sm, speaker, vantage_xy, centre_xy, settings=None, servo=None, servo_stop_m=None):
        """servo: optional callable t -> (range_m, bearing_rad) of the target board when it is in view (fresh), else None: the approach then follows the board (stops at servo_stop_m) instead of dead reckoning."""
        self.sm, self.speaker = sm, speaker
        self.servo, self.servo_stop_m = servo, servo_stop_m
        self.vantage_xy, self.centre_xy = tuple(vantage_xy), tuple(centre_xy)
        self.s = settings or DeploySettings()
        self._ok = 0                          # consecutive in-view frames of the handshake detector
        self.prompts = []                     # every clip played, in order
        self.log = []                         # (t, state value) at every state change
        self.events = []                      # (t, name, pose) of the events this runner sent

    def _play(self, res):
        clip = res.command.play
        if clip:
            self.prompts.append(clip)
            try:
                self.speaker.play(clip)
            except Exception:                 # audio must never stop a deployment
                pass

    def _event(self, name, t, data=None, pose=None):
        before = self.sm.state
        res = self.sm.handle_event(name, data, t)
        self.events.append((t, name, pose))
        self._play(res)
        if self.sm.state != before:
            self.log.append((t, self.sm.state.value))
        return res

    def start(self, t, bearing_rad=None):
        return self._event("ENTRANCE_FOUND", t, {"bearing_rad": bearing_rad})

    def step(self, t, pose, esp_in_view=None):
        """One control tick -> (v, w), normalised and legal for the motors. Order: the state machine's timeouts first, then this state's behaviour."""
        before = self.sm.state
        res = self.sm.tick(t)
        self._play(res)
        if self.sm.state != before:
            self.log.append((t, self.sm.state.value))
        st = self.sm.state
        v = w = 0.0
        if st == State.APPROACH_VANTAGE:
            obs = self.servo(t) if self.servo is not None else None
            if obs is not None:
                v, w, arrived = servo_command(obs[0], obs[1], self.servo_stop_m, self.s)
            else:
                v, w, arrived = goto_command(pose, self.vantage_xy, self.s)
            if arrived:
                self._event("VANTAGE_REACHED", t, pose=pose)
                v = w = 0.0
        elif st == State.WAIT_CAMERA:
            w, _ = face_command(pose, self.centre_xy, self.s)
            self._ok = self._ok + 1 if esp_in_view else 0
            if self._ok >= self.s.verify_frames:
                self._event("ESP32_VERIFIED", t, pose=pose)
                self._ok = 0
        if self.sm.state == State.RETRACT:
            v, w = self.sm.cfg.retract_v, 0.0           # reverse to the standby position (the machine ends it by time)
        return v, w
