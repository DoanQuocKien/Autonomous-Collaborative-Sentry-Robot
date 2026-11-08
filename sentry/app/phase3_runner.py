"""Phase 3 Interception Runner: connects StateMachine with HoldDetector, Pursuit/Hold controllers, and TargetQueue.

Owner: kouun-rokku (KR).
Week 6 deliverable: wires PURSUE and HOLD states to the closed-loop controllers
and hold detector, managing the transition chain from Phase 2 monitoring
(INTRUDER_QUEUED) to Phase 3 deployment, target pursuit, standoff hold,
evasion pulse, and target queue handoff.

Pure CPU logic (no sockets or hardware dependencies).
Motor command output (v, w) strictly obeys JetBot physical motor dead-zone rules:
  dead = min_pwm / max_speed = 0.40 (below which wheels stall and whine).
In HOLD: translation is strictly zero (v = 0.0), yaw-only recentering (|w| >= 0.45 or (0, 0)).
In PURSUE: forward capped at 0.55, reverse capped at -0.45, obstacle repulsion applied.
"""
from dataclasses import dataclass, field
import logging
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from sentry.app.state_machine import Command, State, StateMachine, TransitionResult
from sentry.app.target_queue import IntruderRecord, TargetQueue
from sentry.nav.controllers import (
    ControllerOutput,
    HoldBehaviorConfig,
    HoldController,
    InterceptionController,
    PursuitConfig,
    PursuitController,
)
from sentry.nav.explore import Command as NavCommand, ExploreSettings, legal
from sentry.nav.hold_detector import HoldConfig, HoldDetector, HoldState

logger = logging.getLogger("sentry.phase3")


@dataclass(frozen=True)
class Phase3Settings:
    """Configuration settings for Phase 3 runner."""
    target_lost_timeout_s: float = 3.0
    evade_turn_sign_default: float = 1.0
    min_track_confidence: float = 0.30


@dataclass
class Phase3StepResult:
    """Output summary of a single Phase 3 control tick."""
    t: float
    v: float
    w: float
    state: State
    mode: str
    active_target: Optional[str] = None
    controller_output: Optional[ControllerOutput] = None
    state_machine_transition: Optional[TransitionResult] = None
    cmd_legal: bool = True
    event_dispatched: Optional[str] = None


class Phase3Runner:
    """Coordinates StateMachine, InterceptionController, and TargetQueue in Phase 3."""

    def __init__(
        self,
        sm: Optional[StateMachine] = None,
        controller: Optional[InterceptionController] = None,
        queue: Optional[TargetQueue] = None,
        speaker: Optional[Any] = None,
        explore_settings: Optional[ExploreSettings] = None,
        settings: Optional[Phase3Settings] = None,
    ):
        self.sm = sm if sm is not None else StateMachine(initial_state=State.STANDBY)
        self.controller = controller if controller is not None else InterceptionController()
        self.queue = queue if queue is not None else TargetQueue()
        self.speaker = speaker
        self.explore_settings = explore_settings if explore_settings is not None else ExploreSettings()
        self.s = settings if settings is not None else Phase3Settings()

        # Telemetry and logging
        self.prompts: List[str] = []
        self.log: List[Tuple[float, str]] = []
        self.events: List[Tuple[float, str, Any]] = []

        # Internal tracking caches
        self._last_target_obs: Optional[Tuple[float, float]] = None
        self._last_target_t: Optional[float] = None
        self._last_obs_dist: Optional[float] = None
        self._last_obs_bearing: float = 0.0
        self._evade_w: float = self.sm.cfg.evade_w

    @property
    def state(self) -> State:
        return self.sm.state

    @property
    def active_target(self) -> Optional[str]:
        return self.sm.active_target

    @property
    def mode(self) -> str:
        return self.controller.mode

    def _play(self, clip: Optional[str]) -> None:
        if clip:
            self.prompts.append(clip)
            if self.speaker is not None:
                try:
                    self.speaker.play(clip)
                except Exception as e:
                    logger.warning("Failed playing audio clip %r: %s", clip, e)

    def _dispatch_event(self, name: str, t: float, data: Any = None) -> TransitionResult:
        prev = self.sm.state
        res = self.sm.handle_event(name, data=data, t=t)
        self.events.append((t, name, data))
        if res.command and res.command.play:
            self._play(res.command.play)
        if self.sm.state != prev:
            self.log.append((t, self.sm.state.value))
            logger.info("Phase 3 transition at t=%.3f: %s -> %s (event: %s)", t, prev.value, self.sm.state.value, name)
        return res

    def start(self, t: float = 0.0, target_id: Optional[str] = None) -> None:
        """Initialize runner and optionally start pursuing a given target."""
        if target_id is not None:
            self.enqueue_intruder(target_id, t=t)

    def enqueue_intruder(self, record_or_id: Union[IntruderRecord, Dict[str, Any], str], t: Optional[float] = None) -> TransitionResult:
        """Push a newly detected intruder from Phase 2 monitoring into TargetQueue and notify StateMachine."""
        now = self.sm.t if t is None else float(t)

        if isinstance(record_or_id, IntruderRecord):
            record = record_or_id
            self.queue.push(record, t=now)
            data = record.to_dict()
        elif isinstance(record_or_id, dict):
            rec_id = record_or_id.get("id", "intruder_1")
            app_vec = record_or_id.get("appearance_vector")
            record = IntruderRecord(
                id=rec_id,
                appearance_vector=app_vec,
                sector=record_or_id.get("sector", "unknown"),
                timestamp=now,
                enqueued_at=now,
                metadata=record_or_id,
            )
            self.queue.push(record, t=now)
            data = record_or_id
        else:
            rec_id = str(record_or_id)
            record = IntruderRecord(
                id=rec_id,
                appearance_vector=None,
                sector="unknown",
                timestamp=now,
                enqueued_at=now,
            )
            self.queue.push(record, t=now)
            data = {"id": rec_id}

        prev = self.sm.state
        res = self._dispatch_event("INTRUDER_QUEUED", now, data=data)

        # If StateMachine transitioned from STANDBY to PURSUE, pop intruder from queue to activate
        if prev == State.STANDBY and res.state == State.PURSUE:
            self.queue.pop(t=now)

        return res

    def observe_target(self, target_obs: Union[Tuple[float, float], Any], t: float) -> None:
        """Cache fresh target position in local robot coordinates (forward_m, left_m)."""
        if target_obs is None:
            self._last_target_obs = None
            return

        if hasattr(target_obs, "forward_m") and hasattr(target_obs, "left_m"):
            self._last_target_obs = (float(target_obs.forward_m), float(target_obs.left_m))
        elif hasattr(target_obs, "distance_m") and hasattr(target_obs, "bearing_rad"):
            d = float(target_obs.distance_m)
            b = float(target_obs.bearing_rad)
            self._last_target_obs = (d * math.cos(b), d * math.sin(b))
        elif isinstance(target_obs, (tuple, list)) and len(target_obs) == 2:
            self._last_target_obs = (float(target_obs[0]), float(target_obs[1]))
        else:
            raise ValueError(f"Unrecognized target observation format: {target_obs!r}")

        self._last_target_t = float(t)

    def observe_obstacle(self, dist_m: Optional[float], bearing_rad: float = 0.0, t: Optional[float] = None) -> None:
        """Cache nearest obstacle detection."""
        self._last_obs_dist = dist_m
        self._last_obs_bearing = bearing_rad

    def trigger_strike(self, t: float, obstacle_side: Optional[str] = None, turn_sign: Optional[float] = None) -> TransitionResult:
        """Dispatch preemptive STRIKE event triggering evasive reverse and yaw away from obstacle."""
        data = {}
        if obstacle_side is not None:
            data["obstacle_side"] = obstacle_side
        if turn_sign is not None:
            data["turn_sign"] = turn_sign
        res = self._dispatch_event("STRIKE", t, data=data)
        if res.command and abs(res.command.w) > 1e-3:
            self._evade_w = res.command.w
        return res

    def notify_target_exited(self, t: float, target_id: Optional[str] = None) -> TransitionResult:
        """Dispatch TARGET_EXITED event. If FIFO queue has more intruders, resumes pursuit; else searches."""
        data = {"id": target_id or self.sm.active_target}
        res = self._dispatch_event("TARGET_EXITED", t, data=data)

        # Synchronize TargetQueue
        self.queue.complete_active(reason="target_exited", t=t)
        if self.sm.active_target and len(self.queue) > 0:
            if self.queue.active_target is None or self.queue.active_target.id != self.sm.active_target:
                self.queue.pop(t=t)

        return res

    def step(
        self,
        t: float,
        robot_pose: Tuple[float, float, float],
        target_pos: Optional[Union[Tuple[float, float], Any]] = None,
        obstacle_dist_m: Optional[float] = None,
        obstacle_bearing_rad: float = 0.0,
    ) -> Tuple[float, float]:
        """Execute one control step at timestamp t -> (v, w) legal motor command."""
        # 1. Update StateMachine timer ticks and evaluate timeouts
        prev_sm_state = self.sm.state
        tick_res = self.sm.tick(t)
        if tick_res.command and tick_res.command.play:
            self._play(tick_res.command.play)
        if self.sm.state != prev_sm_state:
            self.log.append((t, self.sm.state.value))

        curr_state = self.sm.state

        # 2. Update observations
        if target_pos is not None:
            self.observe_target(target_pos, t)
        if obstacle_dist_m is not None:
            self.observe_obstacle(obstacle_dist_m, obstacle_bearing_rad, t)

        obs_dist = obstacle_dist_m if obstacle_dist_m is not None else self._last_obs_dist
        obs_bearing = obstacle_bearing_rad if obstacle_dist_m is not None else self._last_obs_bearing

        # 3. State-specific motor execution
        v, w = 0.0, 0.0

        if curr_state == State.STANDBY:
            # Standby mode: stationary monitoring
            v, w = 0.0, 0.0

        elif curr_state == State.EVADE:
            # Evasion pulse: reverse at max speed and yaw away from obstacle
            v = self.sm.cfg.evade_v
            w = self._evade_w

        elif curr_state in (State.PURSUE, State.HOLD):
            target_obs = self._last_target_obs
            target_is_fresh = (
                target_obs is not None
                and self._last_target_t is not None
                and (t - self._last_target_t) <= self.s.target_lost_timeout_s
            )

            if target_is_fresh and target_obs is not None:
                fwd_m, left_m = target_obs
                yaw_err = math.atan2(left_m, max(1e-6, fwd_m))

                # Step the closed-loop InterceptionController
                ctrl_out = self.controller.step(
                    t=t,
                    robot_pose=robot_pose,
                    target_local_pos=(fwd_m, left_m),
                    yaw_err=yaw_err,
                    obstacle_dist_m=obs_dist,
                    obstacle_bearing_rad=obs_bearing,
                )

                # Check if hold detector triggered mode changes
                if ctrl_out.event == "TARGET_STATIONARY" and curr_state == State.PURSUE:
                    self._dispatch_event("TARGET_STATIONARY", t)
                    curr_state = self.sm.state

                elif ctrl_out.event == "TARGET_MOVING" and curr_state == State.HOLD:
                    self._dispatch_event("TARGET_MOVING", t)
                    curr_state = self.sm.state

                # Emitted command depending on resolved state:
                if curr_state == State.HOLD:
                    # In HOLD: translation strictly v = 0.0
                    v = 0.0
                    w = ctrl_out.w
                else:
                    # In PURSUE: forward distance PD + yaw centering PD + obstacle repulsion
                    v = ctrl_out.v
                    w = ctrl_out.w
            else:
                # Target is not currently observed: hold position
                v, w = 0.0, 0.0

        elif curr_state == State.SEARCH:
            steady = self.sm._steady_command()
            v, w = steady.v, steady.w

        # 4. Enforce JetBot motor dead-zone legality
        cmd_candidate = NavCommand(v, w, "", "")
        if not legal(cmd_candidate, self.explore_settings):
            # If command violates dead-zone rules, project to legal safe state:
            if abs(v) < self.explore_settings.dead:
                v = 0.0
                if abs(w) < self.explore_settings.dead:
                    w = 0.0
                else:
                    w = math.copysign(max(abs(w), self.explore_settings.w_spin), w)
            else:
                # Active translation: keep inner wheel at or above dead zone after mix normalization
                dead = self.explore_settings.dead
                max_w_allowed = ((1.0 - dead) / (1.0 + dead)) * abs(v)
                w = math.copysign(min(abs(w), max_w_allowed), w)

        return v, w
