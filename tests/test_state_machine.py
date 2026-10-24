"""T0 unit tests for sentry/app/state_machine.py: Phase 1–3 scripted event sequences, timeouts, and invalid events."""
import logging
import pytest

from sentry.app.state_machine import (
     KNOWN_EVENTS,
    Event,
    Phase,
    State,
    StateMachine,
    StateMachineConfig,
)


def test_config_from_toml_reads_spec_thresholds():
    cfg = StateMachineConfig.from_toml()
    assert cfg.standoff_m == 1.2
    assert (cfg.stationary_speed_mps, cfg.stationary_time_s, cfg.stationary_exit_speed_mps) == (0.1, 2.0, 0.2)
    assert (cfg.evade_v, cfg.evade_w, cfg.evade_duration_s) == (-1.0, 0.8, 0.4)


def test_phase1_scripted_setup_including_entrance_lost_and_handshake():
    sm = StateMachine()
    assert sm.state == State.EXPLORE and sm.phase == Phase.SETUP

    script = [
        (1.0, "ENTRANCE_FOUND", {"bearing_rad": 0.25}),
        (2.0, "ENTRANCE_LOST"),                            # lost door before reaching sweet spot -> back to EXPLORE
        (3.5, "ENTRANCE_FOUND", -0.15),                    # re-acquired door
        (6.0, "VANTAGE_REACHED"),                          # sweet spot reached -> audio prompt + wait for ESP32
        (7.0, "ESP32_LOST"),                               # camera not yet aimed -> stays in WAIT_CAMERA
        (9.0, "ESP32_VERIFIED"),                           # handshake passed -> confirmation audio + reverse to standby
        (10.5, "STANDBY_REACHED"),                         # parked -> Phase 2 STANDBY, map saved
    ]
    results = sm.run_script(script)
    states = [r.state for r in results]
    assert states == [
        State.APPROACH_VANTAGE,
        State.EXPLORE,
        State.APPROACH_VANTAGE,
        State.WAIT_CAMERA,
        State.WAIT_CAMERA,
        State.RETRACT,
        State.STANDBY,
    ]
    assert results[0].command.w == pytest.approx(0.25)
    assert results[3].command.play == "place_camera" and results[3].command.v == 0.0
    assert results[5].command.play == "camera_verified" and results[5].command.v < 0.0
    assert "save_map" in results[6].command.actions and results[6].phase == Phase.MONITOR
    assert not sm.ignored_events


def test_full_three_phase_two_intruder_script_with_hold_evade_and_search():
    sm = StateMachine()
    script = [
        # Phase 1: Setup
        (1.0, "ENTRANCE_FOUND", 0.1),
        (3.0, "SWEET_SPOT_REACHED"),
        (5.0, "CAMERA_VERIFIED"),
        (7.0, "TICK"),                                     # retract_duration_s=2.0 s completes -> STANDBY
        # Phase 2 -> Phase 3: T1 and T2 enter
        (10.0, "INTRUDER_QUEUED", {"id": "T1"}),           # engages T1 immediately -> PURSUE
        (11.0, "INTRUDER_QUEUED", {"id": "T2"}),           # queued while pursuing T1
        (12.0, "INTRUDER_QUEUED", {"id": "T3"}),           # queued second in FIFO
        # Phase 3: Pursuit, Hold, Strike Evasion
        (14.0, "TARGET_STATIONARY"),                       # T1 stops -> HOLD (v=0, recenter)
        (15.5, "TARGET_MOVING"),                           # T1 resumes walking -> PURSUE
        (16.0, "STRIKE", {"obstacle_side": "left"}),       # T1 lunges; obstacle on left -> yaw right (-0.8)
        (16.4, "TICK"),                                    # 400 ms evade pulse finishes -> PURSUE
        # T1 exits -> search for T2 (plan -> follow -> scan -> found)
        (20.0, "TARGET_EXITED"),
        (20.5, "PLAN_READY"),
        (22.0, "VIEWPOINT_REACHED"),
        (24.0, "SCAN_DONE"),
        (25.0, "TARGET_FOUND"),                            # T2 re-acquired -> PURSUE
        # T2 exits -> search for T3 -> not found -> drop T3 -> empty queue -> STANDBY
        (30.0, "TARGET_EXITED"),
        (35.0, "SEARCH_EXHAUSTED"),
    ]
    results = sm.run_script(script)
    assert [r.state for r in results] == [
        State.APPROACH_VANTAGE,
        State.WAIT_CAMERA,
        State.RETRACT,
        State.STANDBY,
        State.PURSUE,
        State.PURSUE,
        State.PURSUE,
        State.HOLD,
        State.PURSUE,
        State.EVADE,
        State.PURSUE,
        State.SEARCH,
        State.SEARCH,
        State.SEARCH,
        State.SEARCH,
        State.PURSUE,
        State.SEARCH,
        State.STANDBY,
    ]
    # Check key commands and queue handoffs
    assert results[4].command.target_id == "T1" and results[4].command.play == "intruder_detected"
    assert results[7].command.v == 0.0 and results[7].command.play == "hold_position"
    assert results[9].command.v == -1.0 and results[9].command.w == -0.8 and results[9].command.play == "alarm"
    assert results[11].command.target_id == "T2" and results[11].search_step == "PLAN"
    assert results[12].search_step == "FOLLOW"
    assert results[13].search_step == "SCAN" and results[13].command.v == 0.0 and results[13].command.w > 0
    assert results[14].search_step == "FOLLOW"
    assert results[15].command.target_id == "T2" and results[15].state == State.PURSUE
    assert results[16].command.target_id == "T3" and results[16].state == State.SEARCH
    assert results[17].state == State.STANDBY and "drop_target" in results[17].command.actions
    assert [t for _, t in sm.completed_targets] == ["T1", "T2"]
    assert [t for _, t in sm.dropped_targets] == ["T3"]
    assert not sm.ignored_events


def test_evade_preempts_hold_and_enforces_cooldown(caplog):
    sm = StateMachine(initial_state=State.HOLD, t0=0.0)
    sm.active_target = "T1"

    # Strike from HOLD with nearer obstacle on the right -> yaw left (+0.8)
    r1 = sm.handle_event("STRIKE", {"right_obstacle_m": 0.4, "left_obstacle_m": 1.1}, t=1.0)
    assert r1.state == State.EVADE and r1.command.v == -1.0 and r1.command.w == 0.8

    # Finish evade at t=1.4
    r2 = sm.handle_event("EVADE_COMPLETE", t=1.4)
    assert r2.state == State.PURSUE

    # Second strike within 1.0 s cooldown (at t=1.9) is ignored and logged
    with caplog.at_level(logging.WARNING, logger="sentry.state_machine"):
        r3 = sm.handle_event("STRIKE", t=1.9)
    assert r3.ignored and r3.state == State.PURSUE
    assert "cooldown" in sm.ignored_events[-1].reason

    # Strike after cooldown expires (at t=2.5) succeeds
    r4 = sm.handle_event("STRIKE", t=2.5)
    assert r4.state == State.EVADE and not r4.ignored


def test_edge_cases_empty_queue_exit_and_intruder_leaving_during_evade_and_esp32_lost():
    # 1. Target exits during EVADE when queue is empty -> returns directly to STANDBY
    sm = StateMachine(initial_state=State.STANDBY, t0=0.0)
    sm.handle_event("INTRUDER_QUEUED", "T1", t=1.0)
    sm.handle_event("STRIKE", t=2.0)
    assert sm.state == State.EVADE
    r_exit = sm.handle_event("TARGET_EXITED", t=2.2)
    assert r_exit.state == State.STANDBY and sm.active_target is None

    # 2. Lost ESP32 stream while in STANDBY -> returns to WAIT_CAMERA and re-prompts user
    r_lost = sm.handle_event("ESP32_LOST", t=5.0)
    assert r_lost.state == State.WAIT_CAMERA and r_lost.command.play == "place_camera"

    # 3. Search exhausted when a third target is still waiting in the queue -> stays in SEARCH for T3
    sm2 = StateMachine(initial_state=State.SEARCH, t0=0.0, queued_targets=["T3"])
    sm2.active_target = "T2"
    r_next = sm2.handle_event("SEARCH_EXHAUSTED", t=10.0)
    assert r_next.state == State.SEARCH and sm2.active_target == "T3"
    assert [t for _, t in sm2.dropped_targets] == ["T2"]


def test_all_state_timeouts():
    cfg = StateMachineConfig(
        explore_timeout_s=50.0,
        approach_timeout_s=10.0,
        handshake_timeout_s=15.0,
        retract_duration_s=2.0,
        evade_duration_s=0.4,
        search_timeout_s=20.0,
    )

    # 1. APPROACH_VANTAGE timeout -> back to EXPLORE
    sm = StateMachine(cfg, initial_state=State.APPROACH_VANTAGE, t0=0.0)
    assert sm.tick(9.9).state == State.APPROACH_VANTAGE
    r = sm.tick(10.0)
    assert r.timed_out and r.state == State.EXPLORE and "approach_timeout" in r.command.actions

    # 2. EXPLORE timeout -> STANDBY fallback
    r2 = sm.tick(60.0)
    assert r2.timed_out and r2.state == State.STANDBY and "explore_timeout" in r2.command.actions

    # 3. WAIT_CAMERA timeout -> stays in WAIT_CAMERA, re-plays prompt, resets timer
    sm_wait = StateMachine(cfg, initial_state=State.WAIT_CAMERA, t0=0.0)
    r3 = sm_wait.tick(15.0)
    assert r3.timed_out and r3.state == State.WAIT_CAMERA and r3.command.play == "place_camera"
    assert sm_wait.time_in_state(15.0) == 0.0

    # 4. SEARCH timeout -> drops target and returns to STANDBY when queue is empty
    sm_search = StateMachine(cfg, initial_state=State.SEARCH, t0=0.0)
    sm_search.active_target = "T2"
    r4 = sm_search.tick(20.0)
    assert r4.timed_out and r4.state == State.STANDBY
    assert "search_timeout" in r4.command.actions and "drop_target" in r4.command.actions
    assert [t for _, t in sm_search.dropped_targets] == ["T2"]


@pytest.mark.parametrize(
    "state,invalid_events",
    [
        (State.EXPLORE, ["VANTAGE_REACHED", "ESP32_VERIFIED", "STANDBY_REACHED", "TARGET_STATIONARY", "STRIKE", "TARGET_FOUND"]),
        (State.APPROACH_VANTAGE, ["ESP32_VERIFIED", "STANDBY_REACHED", "TARGET_STATIONARY", "STRIKE", "SEARCH_EXHAUSTED"]),
        (State.WAIT_CAMERA, ["ENTRANCE_FOUND", "VANTAGE_REACHED", "STANDBY_REACHED", "STRIKE", "TARGET_EXITED"]),
        (State.RETRACT, ["ENTRANCE_FOUND", "VANTAGE_REACHED", "ESP32_VERIFIED", "STRIKE", "TARGET_FOUND"]),
        (State.STANDBY, ["ENTRANCE_FOUND", "VANTAGE_REACHED", "STANDBY_REACHED", "TARGET_STATIONARY", "STRIKE", "TARGET_EXITED"]),
        (State.PURSUE, ["ENTRANCE_FOUND", "VANTAGE_REACHED", "ESP32_VERIFIED", "TARGET_MOVING", "TARGET_FOUND", "SEARCH_EXHAUSTED"]),
        (State.HOLD, ["ENTRANCE_FOUND", "VANTAGE_REACHED", "TARGET_STATIONARY", "TARGET_FOUND", "SEARCH_EXHAUSTED"]),
        (State.EVADE, ["ENTRANCE_FOUND", "TARGET_STATIONARY", "TARGET_MOVING", "STRIKE", "TARGET_FOUND"]),
        (State.SEARCH, ["ENTRANCE_FOUND", "VANTAGE_REACHED", "TARGET_STATIONARY", "TARGET_MOVING", "STRIKE", "TARGET_EXITED"]),
    ],
)
def test_invalid_events_are_ignored_and_logged_in_every_state(state, invalid_events, caplog):
    sm = StateMachine(initial_state=state, t0=1.0)
    t = 1.0
    for ev in invalid_events + ["COMPLETELY_UNKNOWN_EVENT"]:
        t += 0.5
        with caplog.at_level(logging.WARNING, logger="sentry.state_machine"):
            res = sm.handle_event(ev, t=t)
        assert res.ignored and not res.transitioned
        assert sm.state == state
        assert sm.ignored_events[-1].event == ev
        assert sm.ignored_events[-1].state == state
    assert len(sm.ignored_events) == len(invalid_events) + 1
    assert any("Ignoring event" in rec.message for rec in caplog.records)


def test_backwards_or_nonfinite_timestamps_rejected():
    sm = StateMachine(t0=5.0)
    with pytest.raises(ValueError):
        sm.tick(4.9)
    with pytest.raises(ValueError):
        sm.handle_event(Event("ENTRANCE_FOUND", t=float("nan")))
    with pytest.raises(ValueError):
        sm.handle_event(Event("ENTRANCE_FOUND", t=4.9))
