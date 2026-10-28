"""Phase 1 deployment runner: drives the state machine from the robot's pose and the ESP32 handshake (plan: deployment behaviour, Week 3-4).

The state machine (state_machine.py) is event driven: ENTRANCE_FOUND -> APPROACH_VANTAGE -> VANTAGE_REACHED -> WAIT_CAMERA (prompt, face the room centre) ->
ESP32_VERIFIED -> RETRACT (back up for retract_duration_s) -> STANDBY. Nothing produced those events from motion and from the camera; this does:

  runner = DeployRunner(StateMachine(...), speaker, vantage_xy=(x, y), centre_xy=(x, y))   # speaker: AudioPromptPlayer(sender=LocalSpeaker()) or anything with play(clip)
  runner.start(t, bearing_rad)            # the entrance was found (sentry/perception/entrance.py)
  v, w = runner.step(t, pose, esp_in_view)   # every control tick: pose = (x, y, yaw) in the map frame, esp_in_view = the handshake detector's per-frame result or None

Pure logic (no sockets, no clock): the live wrapper supplies the dead-reckoned pose and the handshake flags and sends (v, w) to the robot through the e-stop interlock; the
simulator tests drive it with tools/sim_robot.SimRobot. Commands are normalised in [-1, 1] like the state machine's. The state machine's own approach command (straight ahead,
steered by the entrance bearing) is replaced here by a go-to controller on the chosen vantage point; its timeouts still apply (approach 30 s -> back to EXPLORE, handshake 60 s
-> prompt again, retract by time).
"""
import math

from sentry.app.state_machine import State


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def goto_command(pose, goal_xy, v_max=0.4, w_max=0.6, k_w=1.2, turn_only_rad=0.35, tol_m=0.15):
    """pose (x, y, yaw) -> (v, w, arrived). Turns in place while the heading error exceeds turn_only_rad, otherwise drives and steers; stops within tol_m of the goal."""
    dx, dy = goal_xy[0] - pose[0], goal_xy[1] - pose[1]
    dist = math.hypot(dx, dy)
    if dist <= tol_m:
        return 0.0, 0.0, True
    err = wrap(math.atan2(dy, dx) - pose[2])
    w = max(-w_max, min(w_max, k_w * err))
    if abs(err) > turn_only_rad:
        return 0.0, w, False
    return min(v_max, max(0.15, 0.6 * dist)), w, False       # slows down near the goal, never below 0.15 until inside the tolerance


def face_command(pose, target_xy, w_max=0.5, k_w=1.2, tol_rad=0.12):
    """Turn in place toward target_xy. -> (w, done)."""
    err = wrap(math.atan2(target_xy[1] - pose[1], target_xy[0] - pose[0]) - pose[2])
    if abs(err) <= tol_rad:
        return 0.0, True
    return max(-w_max, min(w_max, k_w * err)), False


class DeployRunner(object):
    def __init__(self, sm, speaker, vantage_xy, centre_xy, tol_m=0.15, verify_frames=3, v_max=0.4, w_max=0.6):
        self.sm, self.speaker = sm, speaker
        self.vantage_xy, self.centre_xy = tuple(vantage_xy), tuple(centre_xy)
        self.tol_m, self.verify_frames, self.v_max, self.w_max = tol_m, verify_frames, v_max, w_max
        self._ok = 0                          # consecutive in-view frames of the handshake detector
        self.prompts = []                     # every clip played, in order
        self.log = []                         # (t, state value) at every state change

    def _play(self, res):
        clip = res.command.play
        if clip:
            self.prompts.append(clip)
            self.speaker.play(clip)

    def _event(self, name, t, data=None):
        before = self.sm.state
        res = self.sm.handle_event(name, data, t)
        self._play(res)
        if self.sm.state != before:
            self.log.append((t, self.sm.state.value))
        return res

    def start(self, t, bearing_rad=None):
        return self._event("ENTRANCE_FOUND", t, {"bearing_rad": bearing_rad})

    def step(self, t, pose, esp_in_view=None):
        """One control tick -> (v, w), normalised. Order: the state machine's timeouts first, then this state's behaviour."""
        before = self.sm.state
        res = self.sm.tick(t)
        self._play(res)
        if self.sm.state != before:
            self.log.append((t, self.sm.state.value))
        st = self.sm.state
        v = w = 0.0
        if st == State.APPROACH_VANTAGE:
            v, w, arrived = goto_command(pose, self.vantage_xy, self.v_max, self.w_max, tol_m=self.tol_m)
            if arrived:
                self._event("VANTAGE_REACHED", t)
                v = w = 0.0
        elif st == State.WAIT_CAMERA:
            w, _ = face_command(pose, self.centre_xy)
            self._ok = self._ok + 1 if esp_in_view else 0
            if self._ok >= self.verify_frames:
                self._event("ESP32_VERIFIED", t)
                self._ok = 0
        if self.sm.state == State.RETRACT:
            v, w = self.sm.cfg.retract_v, 0.0           # reverse to the standby position (the machine ends it by time)
        return v, w
