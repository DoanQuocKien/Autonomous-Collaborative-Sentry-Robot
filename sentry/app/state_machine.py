"""Phase 1–3 sentry state machine (pure CPU logic: events in, commands out).

Owner: kouun-rokku (KR).
Never touches sockets or neural models directly (`Implementation Plan.md` §3).
Consumes discrete events (`ENTRANCE_FOUND`, `ENTRANCE_LOST`, `VANTAGE_REACHED`,
`ESP32_VERIFIED`, `ESP32_LOST`, `STANDBY_REACHED`, `INTRUDER_QUEUED`,
`TARGET_STATIONARY`, `TARGET_MOVING`, `STRIKE`, `EVADE_COMPLETE`,
`TARGET_EXITED`, `TARGET_FOUND`, `SEARCH_EXHAUSTED`, plus search sub-events)
and time ticks (`tick(t)`), and emits structured `Command` objects.
Invalid events for the current state are ignored and logged.
"""
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
import logging
import math

from sentry.config import load

logger = logging.getLogger("sentry.state_machine")

_TIME_EPS = 1e-9  # float tolerance so decimal steps like 17.0 + 0.4 == 17.4 trigger 0.4 s durations


class Phase(str, Enum):
    SETUP = "setup"          # Phase 1: Explore, match entrance, sweet spot, HCI camera placement, retract
    MONITOR = "monitor"      # Phase 2: Standby while ESP32-CAM monitors incoming faces
    INTERCEPT = "intercept"  # Phase 3: Pursue, standoff hold, strike evasion, coverage search


class State(str, Enum):
    # Phase 1: Setup & Mapping
    EXPLORE = "EXPLORE"
    APPROACH_VANTAGE = "APPROACH_VANTAGE"
    WAIT_CAMERA = "WAIT_CAMERA"
    RETRACT = "RETRACT"
    # Phase 2: Access Control / Monitoring
    STANDBY = "STANDBY"
    # Phase 3: Physical Deterrence, Evasion & Handoff Search
    PURSUE = "PURSUE"
    HOLD = "HOLD"
    EVADE = "EVADE"
    SEARCH = "SEARCH"


# Convenient state aliases
State.SWEET_SPOT = State.APPROACH_VANTAGE
State.PROMPT_CAMERA = State.WAIT_CAMERA
State.VERIFY_CAMERA = State.WAIT_CAMERA

STATE_PHASE = {
    State.EXPLORE: Phase.SETUP,
    State.APPROACH_VANTAGE: Phase.SETUP,
    State.WAIT_CAMERA: Phase.SETUP,
    State.RETRACT: Phase.SETUP,
    State.STANDBY: Phase.MONITOR,
    State.PURSUE: Phase.INTERCEPT,
    State.HOLD: Phase.INTERCEPT,
    State.EVADE: Phase.INTERCEPT,
    State.SEARCH: Phase.INTERCEPT,
}

# Canonical event names and accepted aliases
EVENT_ALIASES = {
    "SWEET_SPOT_REACHED": "VANTAGE_REACHED",
    "CAMERA_VERIFIED": "ESP32_VERIFIED",
    "HANDSHAKE_OK": "ESP32_VERIFIED",
    "CAMERA_LOST": "ESP32_LOST",
    "HOLD": "TARGET_STATIONARY",
    "RESUME_PURSUIT": "TARGET_MOVING",
}

KNOWN_EVENTS = frozenset({
    "ENTRANCE_FOUND",
    "ENTRANCE_LOST",
    "VANTAGE_REACHED",
    "ESP32_VERIFIED",
    "ESP32_LOST",
    "STANDBY_REACHED",
    "INTRUDER_QUEUED",
    "TARGET_STATIONARY",
    "TARGET_MOVING",
    "STRIKE",
    "EVADE_COMPLETE",
    "TARGET_EXITED",
    "PLAN_READY",
    "VIEWPOINT_REACHED",
    "SCAN_DONE",
    "TARGET_FOUND",
    "SEARCH_EXHAUSTED",
})


@dataclass(frozen=True)
class StateMachineConfig:
    # Motion commands & thresholds from config.toml [thresholds]
    explore_v: float = 0.45
    explore_w: float = 0.0
    approach_v: float = 0.45
    retract_v: float = -0.45
    retract_duration_s: float = 2.0
    standoff_m: float = 1.2
    stationary_speed_mps: float = 0.1
    stationary_time_s: float = 2.0
    stationary_exit_speed_mps: float = 0.2
    strike_area_growth: float = 0.40
    strike_window_s: float = 0.1
    evade_v: float = -1.0
    evade_w: float = 0.8
    evade_duration_s: float = 0.4
    evade_cooldown_s: float = 1.0
    scan_w: float = 0.45
    # State timeouts (seconds)
    explore_timeout_s: float = 180.0
    approach_timeout_s: float = 30.0
    handshake_timeout_s: float = 60.0
    search_timeout_s: float = 120.0
    # Audio clip names (validated against common.protocol._CLIP)
    clip_place_camera: str = "place_camera"
    clip_camera_verified: str = "camera_verified"
    clip_intruder_detected: str = "intruder_detected"
    clip_hold_position: str = "hold_position"
    clip_alarm: str = "alarm"

    @classmethod
    def from_toml(cls, cfg=None):
        """Build StateMachineConfig from config.toml [thresholds] plus optional overrides."""
        raw = load() if cfg is None else cfg
        t = raw.get("thresholds", {})
        return cls(
            standoff_m=float(t.get("standoff_m", 1.2)),
            stationary_speed_mps=float(t.get("stationary_speed_mps", 0.1)),
            stationary_time_s=float(t.get("stationary_time_s", 2.0)),
            stationary_exit_speed_mps=float(t.get("stationary_exit_speed_mps", 0.2)),
            strike_area_growth=float(t.get("strike_area_growth", 0.40)),
            strike_window_s=float(t.get("strike_window_s", 0.1)),
            evade_v=float(t.get("evade_v", -1.0)),
            evade_w=float(t.get("evade_w", 0.8)),
            evade_duration_s=float(t.get("evade_duration_s", 0.4)),
        )


@dataclass(frozen=True)
class Event:
    name: str
    data: object = None
    t: float | None = None


@dataclass(frozen=True)
class Command:
    """Output emitted by the state machine on an event or tick.

    `v` and `w` are normalized motor commands in [-1, 1] (or None if the state delegates
    continuous closed-loop steering to the active controller). `play` is an optional audio
    clip name (`assets/audio/<play>.wav`), and `actions` lists symbolic orchestration actions
    (e.g. `'save_map'`, `'engage_target'`, `'plan_search'`, `'drop_target'`).
    """

    v: float = 0.0
    w: float = 0.0
    play: str | None = None
    actions: tuple = ()
    target_id: object = None


@dataclass(frozen=True)
class IgnoredEvent:
    t: float
    state: State
    event: str
    reason: str


@dataclass(frozen=True)
class TransitionResult:
    prev_state: State
    state: State
    phase: Phase
    event: str
    t: float
    command: Command
    transitioned: bool = False
    ignored: bool = False
    timed_out: bool = False
    search_step: str | None = None


def _normalize_event(event, data=None, t=None, fallback_t=0.0):
    if isinstance(event, Event):
        raw_name = event.name
        ev_data = event.data if data is None else data
        cand_t = event.t if t is None else t
        ev_t = fallback_t if cand_t is None else cand_t
    elif isinstance(event, tuple) and len(event) == 2:
        raw_name, ev_data = event
        ev_t = fallback_t if t is None else t
    elif isinstance(event, str):
        raw_name, ev_data = event, data
        ev_t = fallback_t if t is None else t
    else:
        raise TypeError("event must be an Event, (name, data) tuple, or str; got %r" % (event,))
    if not isinstance(raw_name, str) or not raw_name:
        raise ValueError("event name must be a non-empty string")
    canonical = EVENT_ALIASES.get(raw_name, raw_name)
    return canonical, ev_data, float(ev_t)


def _extract_target_id(data, fallback_seq):
    if isinstance(data, dict):
        for k in ("id", "target_id", "intruder_id"):
            if k in data and data[k] is not None:
                return data[k]
    elif hasattr(data, "id") and getattr(data, "id") is not None:
        return getattr(data, "id")
    elif hasattr(data, "target_id") and getattr(data, "target_id") is not None:
        return getattr(data, "target_id")
    elif isinstance(data, (str, int)):
        return data
    return "intruder_%d" % fallback_seq


def _evade_turn_sign(data):
    """Choose +1 (turn left) or -1 (turn right) away from the nearer obstacle side."""
    if isinstance(data, dict):
        if "turn_sign" in data:
            return 1.0 if float(data["turn_sign"]) >= 0 else -1.0
        side = data.get("nearer_obstacle_side") or data.get("obstacle_side")
        if side == "right":
            return 1.0   # obstacle on right -> yaw left (+w)
        if side == "left":
            return -1.0  # obstacle on left -> yaw right (-w)
        left_d = data.get("left_obstacle_m")
        right_d = data.get("right_obstacle_m")
        if left_d is not None and right_d is not None:
            return 1.0 if float(right_d) <= float(left_d) else -1.0
    return 1.0


class StateMachine:
    """Deterministic event-driven state machine covering Phases 1–3."""

    def __init__(
        self,
        config=None,
        *,
        initial_state=State.EXPLORE,
        t0=0.0,
        queued_targets=(),
    ):
        self.cfg = StateMachineConfig.from_toml() if config is None else config
        self.state = State(initial_state)
        self.t = float(t0)
        self.state_entered_t = float(t0)
        self.entrance_bearing_rad = None
        self.queue = deque(queued_targets)
        self.active_target = None
        self.dropped_targets = []
        self.completed_targets = []
        self.search_step = "PLAN" if self.state == State.SEARCH else None
        self.last_evade_end_t = None
        self._target_seq = len(self.queue)
        self.history = []
        self.ignored_events = []

    @property
    def phase(self):
        return STATE_PHASE[self.state]

    def time_in_state(self, now=None):
        now = self.t if now is None else float(now)
        return max(0.0, now - self.state_entered_t)

    def in_evade_cooldown(self, now=None):
        if self.last_evade_end_t is None:
            return False
        now = self.t if now is None else float(now)
        return (now - self.last_evade_end_t) + _TIME_EPS < self.cfg.evade_cooldown_s

    def _enter(self, new_state, now, *, search_step=None):
        self.state = State(new_state)
        self.state_entered_t = float(now)
        if self.state == State.SEARCH:
            self.search_step = search_step or "PLAN"
        else:
            self.search_step = None

    def _ignore(self, event_name, now, reason):
        rec = IgnoredEvent(t=now, state=self.state, event=event_name, reason=reason)
        self.ignored_events.append(rec)
        logger.warning(
            "Ignoring event %s in state %s at t=%.3f: %s",
            event_name,
            self.state.value,
            now,
            reason,
        )
        cmd = self._steady_command()
        res = TransitionResult(
            prev_state=self.state,
            state=self.state,
            phase=self.phase,
            event=event_name,
            t=now,
            command=cmd,
            transitioned=False,
            ignored=True,
            timed_out=False,
            search_step=self.search_step,
        )
        self.history.append(res)
        return res

    def _record(self, prev_state, event_name, now, command, *, timed_out=False):
        res = TransitionResult(
            prev_state=prev_state,
            state=self.state,
            phase=self.phase,
            event=event_name,
            t=now,
            command=command,
            transitioned=(self.state != prev_state),
            ignored=False,
            timed_out=timed_out,
            search_step=self.search_step,
        )
        self.history.append(res)
        return res

    def _steady_command(self):
        """Default command while dwelling in the current state."""
        if self.state == State.EXPLORE:
            return Command(v=self.cfg.explore_v, w=self.cfg.explore_w, actions=("explore",))
        if self.state == State.APPROACH_VANTAGE:
            w = 0.0 if self.entrance_bearing_rad is None else max(-1.0, min(1.0, float(self.entrance_bearing_rad)))
            return Command(v=self.cfg.approach_v, w=w, actions=("approach_vantage",))
        if self.state in (State.WAIT_CAMERA, State.STANDBY):
            return Command(v=0.0, w=0.0, actions=("hold_still",))
        if self.state == State.RETRACT:
            return Command(v=self.cfg.retract_v, w=0.0, actions=("retract",))
        if self.state == State.PURSUE:
            return Command(v=self.cfg.explore_v, w=0.0, actions=("pursue_target",), target_id=self.active_target)
        if self.state == State.HOLD:
            return Command(v=0.0, w=0.0, actions=("hold_recenter",), target_id=self.active_target)
        if self.state == State.EVADE:
            return Command(v=self.cfg.evade_v, w=self.cfg.evade_w, actions=("evade_pulse",), target_id=self.active_target)
        if self.state == State.SEARCH:
            if self.search_step == "SCAN":
                return Command(v=0.0, w=self.cfg.scan_w, actions=("scan_360",), target_id=self.active_target)
            if self.search_step == "FOLLOW":
                return Command(v=self.cfg.explore_v, w=0.0, actions=("follow_path",), target_id=self.active_target)
            return Command(v=0.0, w=0.0, actions=("plan_search",), target_id=self.active_target)
        return Command(v=0.0, w=0.0)

    def _advance_time(self, t):
        if t is None:
            return self.t
        t = float(t)
        if not math.isfinite(t):
            raise ValueError("timestamp must be finite, got %r" % (t,))
        if t < self.t:
            raise ValueError("timestamp cannot move backwards: %.3f < %.3f" % (t, self.t))
        self.t = t
        return self.t

    def handle_event(self, event, data=None, t=None):
        """Process one discrete event at timestamp `t` -> TransitionResult."""
        name, ev_data, ev_t = _normalize_event(event, data=data, t=t, fallback_t=self.t)
        now = self._advance_time(ev_t)
        prev = self.state

        if name not in KNOWN_EVENTS:
            return self._ignore(name, now, "unknown event %r" % name)

        # ---- Phase 1: Setup & Mapping ----------------------------------------
        if self.state == State.EXPLORE:
            if name == "ENTRANCE_FOUND":
                bearing = ev_data.get("bearing_rad") if isinstance(ev_data, dict) else ev_data
                self.entrance_bearing_rad = None if bearing is None else float(bearing)
                self._enter(State.APPROACH_VANTAGE, now)
                w = 0.0 if self.entrance_bearing_rad is None else max(-1.0, min(1.0, self.entrance_bearing_rad))
                cmd = Command(v=self.cfg.approach_v, w=w, actions=("select_vantage", "approach_vantage"))
                return self._record(prev, name, now, cmd)
            return self._ignore(name, now, "event %s not valid in EXPLORE" % name)

        if self.state == State.APPROACH_VANTAGE:
            if name == "ENTRANCE_LOST":
                self.entrance_bearing_rad = None
                self._enter(State.EXPLORE, now)
                cmd = Command(v=self.cfg.explore_v, w=self.cfg.explore_w, actions=("explore",))
                return self._record(prev, name, now, cmd)
            if name == "VANTAGE_REACHED":
                self._enter(State.WAIT_CAMERA, now)
                cmd = Command(
                    v=0.0,
                    w=0.0,
                    play=self.cfg.clip_place_camera,
                    actions=("face_room_center", "prompt_place_camera"),
                )
                return self._record(prev, name, now, cmd)
            return self._ignore(name, now, "event %s not valid in APPROACH_VANTAGE" % name)

        if self.state == State.WAIT_CAMERA:
            if name == "ESP32_VERIFIED":
                self._enter(State.RETRACT, now)
                cmd = Command(
                    v=self.cfg.retract_v,
                    w=0.0,
                    play=self.cfg.clip_camera_verified,
                    actions=("retract_to_standby",),
                )
                return self._record(prev, name, now, cmd)
            if name == "ESP32_LOST":
                # Still waiting for valid camera placement; keep waiting and log
                cmd = Command(v=0.0, w=0.0, actions=("wait_camera",))
                return self._record(prev, name, now, cmd)
            return self._ignore(name, now, "event %s not valid in WAIT_CAMERA" % name)

        if self.state == State.RETRACT:
            if name == "STANDBY_REACHED":
                self._enter(State.STANDBY, now)
                cmd = Command(v=0.0, w=0.0, actions=("save_map", "standby_ready"))
                return self._record(prev, name, now, cmd)
            return self._ignore(name, now, "event %s not valid in RETRACT" % name)

        # ---- Phase 2: Monitoring (STANDBY) -----------------------------------
        if self.state == State.STANDBY:
            if name == "INTRUDER_QUEUED":
                self._target_seq += 1
                tid = _extract_target_id(ev_data, self._target_seq)
                if self.queue:
                    self.queue.append(tid)
                    self.active_target = self.queue.popleft()
                else:
                    self.active_target = tid
                self._enter(State.PURSUE, now)
                cmd = Command(
                    v=self.cfg.explore_v,
                    w=0.0,
                    play=self.cfg.clip_intruder_detected,
                    actions=("engage_target", "pursue_target"),
                    target_id=self.active_target,
                )
                return self._record(prev, name, now, cmd)
            if name == "ESP32_LOST":
                # Entrance camera stream dropped or moved during monitoring: return to WAIT_CAMERA
                self._enter(State.WAIT_CAMERA, now)
                cmd = Command(
                    v=0.0,
                    w=0.0,
                    play=self.cfg.clip_place_camera,
                    actions=("stream_lost", "prompt_place_camera"),
                )
                return self._record(prev, name, now, cmd)
            return self._ignore(name, now, "event %s not valid in STANDBY" % name)

        # ---- Phase 3: Interception (PURSUE, HOLD, EVADE, SEARCH) -------------
        if name == "INTRUDER_QUEUED":
            # New entrant flagged while robot is already deployed in Phase 3: queue FIFO
            self._target_seq += 1
            tid = _extract_target_id(ev_data, self._target_seq)
            self.queue.append(tid)
            steady = self._steady_command()
            cmd = Command(
                v=steady.v,
                w=steady.w,
                play=None,
                actions=steady.actions + ("queue_target",),
                target_id=self.active_target,
            )
            return self._record(prev, name, now, cmd)

        if self.state == State.PURSUE:
            if name == "TARGET_STATIONARY":
                self._enter(State.HOLD, now)
                cmd = Command(
                    v=0.0,
                    w=0.0,
                    play=self.cfg.clip_hold_position,
                    actions=("hold_recenter",),
                    target_id=self.active_target,
                )
                return self._record(prev, name, now, cmd)
            if name == "STRIKE":
                return self._trigger_evade(prev, name, ev_data, now)
            if name == "TARGET_EXITED":
                return self._handle_target_exited(prev, name, ev_data, now)
            return self._ignore(name, now, "event %s not valid in PURSUE" % name)

        if self.state == State.HOLD:
            if name == "TARGET_MOVING":
                self._enter(State.PURSUE, now)
                cmd = Command(
                    v=self.cfg.explore_v,
                    w=0.0,
                    actions=("pursue_target",),
                    target_id=self.active_target,
                )
                return self._record(prev, name, now, cmd)
            if name == "STRIKE":
                return self._trigger_evade(prev, name, ev_data, now)
            if name == "TARGET_EXITED":
                return self._handle_target_exited(prev, name, ev_data, now)
            return self._ignore(name, now, "event %s not valid in HOLD" % name)

        if self.state == State.EVADE:
            if name == "EVADE_COMPLETE":
                self.last_evade_end_t = now
                self._enter(State.PURSUE, now)
                cmd = Command(
                    v=self.cfg.explore_v,
                    w=0.0,
                    actions=("pursue_target",),
                    target_id=self.active_target,
                )
                return self._record(prev, name, now, cmd)
            if name == "TARGET_EXITED":
                # Intruder left the room during the evasion pulse (Week 11 edge case)
                self.last_evade_end_t = now
                return self._handle_target_exited(prev, name, ev_data, now)
            return self._ignore(name, now, "event %s not valid in EVADE" % name)

        if self.state == State.SEARCH:
            if name == "PLAN_READY":
                self.search_step = "FOLLOW"
                cmd = Command(
                    v=self.cfg.explore_v,
                    w=0.0,
                    actions=("follow_path",),
                    target_id=self.active_target,
                )
                return self._record(prev, name, now, cmd)
            if name == "VIEWPOINT_REACHED":
                self.search_step = "SCAN"
                cmd = Command(
                    v=0.0,
                    w=self.cfg.scan_w,
                    actions=("scan_360",),
                    target_id=self.active_target,
                )
                return self._record(prev, name, now, cmd)
            if name == "SCAN_DONE":
                self.search_step = "FOLLOW"
                cmd = Command(
                    v=self.cfg.explore_v,
                    w=0.0,
                    actions=("follow_path",),
                    target_id=self.active_target,
                )
                return self._record(prev, name, now, cmd)
            if name == "TARGET_FOUND":
                if isinstance(ev_data, dict) and "target_id" in ev_data:
                    self.active_target = ev_data["target_id"]
                self._enter(State.PURSUE, now)
                cmd = Command(
                    v=self.cfg.explore_v,
                    w=0.0,
                    actions=("lock_target", "pursue_target"),
                    target_id=self.active_target,
                )
                return self._record(prev, name, now, cmd)
            if name == "SEARCH_EXHAUSTED":
                return self._handle_search_exhausted(prev, name, now, timed_out=False)
            return self._ignore(name, now, "event %s not valid in SEARCH" % name)

        return self._ignore(name, now, "unhandled state %s" % self.state)

    def _trigger_evade(self, prev, name, ev_data, now):
        if self.in_evade_cooldown(now):
            return self._ignore(name, now, "STRIKE within evade cooldown (%.2f s)" % self.cfg.evade_cooldown_s)
        sign = _evade_turn_sign(ev_data)
        self._enter(State.EVADE, now)
        cmd = Command(
            v=self.cfg.evade_v,
            w=sign * abs(self.cfg.evade_w),
            play=self.cfg.clip_alarm,
            actions=("evade_pulse",),
            target_id=self.active_target,
        )
        return self._record(prev, name, now, cmd)

    def _handle_target_exited(self, prev, name, ev_data, now):
        if self.active_target is not None:
            self.completed_targets.append((now, self.active_target))

        # Check if next target exists in queue or was explicitly indicated in event data
        explicit_next = None
        has_next = bool(self.queue)
        if isinstance(ev_data, dict):
            if "next_target" in ev_data and ev_data["next_target"] is not None:
                explicit_next = ev_data["next_target"]
                has_next = True
            elif "has_next" in ev_data:
                has_next = bool(ev_data["has_next"])

        if has_next:
            if explicit_next is not None:
                self.active_target = explicit_next
            elif self.queue:
                self.active_target = self.queue.popleft()
            else:
                self._target_seq += 1
                self.active_target = "intruder_%d" % self._target_seq
            self._enter(State.SEARCH, now, search_step="PLAN")
            cmd = Command(
                v=0.0,
                w=0.0,
                actions=("plan_search",),
                target_id=self.active_target,
            )
            return self._record(prev, name, now, cmd)

        self.active_target = None
        self._enter(State.STANDBY, now)
        cmd = Command(v=0.0, w=0.0, actions=("return_to_standby",))
        return self._record(prev, name, now, cmd)

    def _handle_search_exhausted(self, prev, name, now, *, timed_out=False):
        dropped = self.active_target
        if dropped is not None:
            self.dropped_targets.append((now, dropped))
            logger.info("Dropped unfound target %r at t=%.3f", dropped, now)

        if self.queue:
            self.active_target = self.queue.popleft()
            self._enter(State.SEARCH, now, search_step="PLAN")
            actions = ("search_timeout", "drop_target", "plan_search") if timed_out else ("drop_target", "plan_search")
            cmd = Command(
                v=0.0,
                w=0.0,
                actions=actions,
                target_id=self.active_target,
            )
            return self._record(prev, name, now, cmd, timed_out=timed_out)

        self.active_target = None
        self._enter(State.STANDBY, now)
        actions = ("search_timeout", "drop_target", "return_to_standby") if timed_out else ("drop_target", "return_to_standby")
        cmd = Command(v=0.0, w=0.0, actions=actions)
        return self._record(prev, name, now, cmd, timed_out=timed_out)

    def tick(self, t):
        """Advance clock to `t` and evaluate state durations / timeouts -> TransitionResult."""
        now = self._advance_time(t)
        elapsed = self.time_in_state(now)
        prev = self.state

        if self.state == State.EVADE and elapsed + _TIME_EPS >= self.cfg.evade_duration_s:
            self.last_evade_end_t = now
            self._enter(State.PURSUE, now)
            cmd = Command(
                v=self.cfg.explore_v,
                w=0.0,
                actions=("evade_complete", "pursue_target"),
                target_id=self.active_target,
            )
            return self._record(prev, "TIMEOUT", now, cmd, timed_out=True)

        if self.state == State.RETRACT and elapsed + _TIME_EPS >= self.cfg.retract_duration_s:
            self._enter(State.STANDBY, now)
            cmd = Command(v=0.0, w=0.0, actions=("save_map", "standby_ready"))
            return self._record(prev, "TIMEOUT", now, cmd, timed_out=True)

        if self.state == State.APPROACH_VANTAGE and elapsed + _TIME_EPS >= self.cfg.approach_timeout_s:
            self.entrance_bearing_rad = None
            self._enter(State.EXPLORE, now)
            cmd = Command(v=self.cfg.explore_v, w=self.cfg.explore_w, actions=("approach_timeout", "explore"))
            return self._record(prev, "TIMEOUT", now, cmd, timed_out=True)

        if self.state == State.WAIT_CAMERA and elapsed + _TIME_EPS >= self.cfg.handshake_timeout_s:
            self._enter(State.WAIT_CAMERA, now)
            cmd = Command(
                v=0.0,
                w=0.0,
                play=self.cfg.clip_place_camera,
                actions=("handshake_timeout", "prompt_place_camera"),
            )
            return self._record(prev, "TIMEOUT", now, cmd, timed_out=True)

        if self.state == State.EXPLORE and elapsed + _TIME_EPS >= self.cfg.explore_timeout_s:
            self._enter(State.STANDBY, now)
            cmd = Command(v=0.0, w=0.0, actions=("explore_timeout", "standby_fallback"))
            return self._record(prev, "TIMEOUT", now, cmd, timed_out=True)

        if self.state == State.SEARCH and elapsed + _TIME_EPS >= self.cfg.search_timeout_s:
            return self._handle_search_exhausted(prev, "TIMEOUT", now, timed_out=True)

        cmd = self._steady_command()
        return self._record(prev, "TICK", now, cmd, timed_out=False)

    # Alias for callers using on_event / on_tick naming
    on_event = handle_event
    on_tick = tick

    def run_script(self, script):
        """Run a sequence of `(t, event_name[, data])` or `(t, 'TICK')` steps -> list[TransitionResult]."""
        results = []
        for item in script:
            if isinstance(item, Event):
                results.append(self.handle_event(item))
                continue
            if len(item) == 2:
                t, ev = item
                data = None
            elif len(item) == 3:
                t, ev, data = item
            else:
                raise ValueError("script entry must be (t, event) or (t, event, data)")
            if ev in ("TICK", None):
                results.append(self.tick(t))
            else:
                results.append(self.handle_event(ev, data=data, t=t))
        return results
