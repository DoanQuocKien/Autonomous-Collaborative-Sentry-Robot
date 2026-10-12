import pytest

from common.protocol import encode_control, encode_play
from jetson.robot_udp import Controller, play_clip


def test_command_is_mixed_capped_and_deadzoned():
    c = Controller(k=1.0, min_pwm=0.0, max_speed=0.5)
    assert c.on_packet(encode_control(1, 1.0, 0.0), now=0.0) == ("motors", (0.5, 0.5))
    assert c.on_packet(encode_control(2, 0.0, 1.0), now=0.0) == ("motors", (-0.5, 0.5))
    # a wheel value below min_pwm AFTER the cap is a clean stop: 0.5 * 0.4 = 0.2 < 0.25
    c = Controller(min_pwm=0.25, max_speed=0.5)
    assert c.on_packet(encode_control(1, 0.4, 0.0), now=0.0) == ("motors", (0.0, 0.0))
    assert c.on_packet(encode_control(2, 0.6, 0.0), now=0.0) == ("motors", (0.3, 0.3))


def test_the_robots_settings_need_v_of_about_0_4_to_move():
    # cap 0.3, min_pwm 0.12 (measured 2026-10-11: 0.09 veers, 0.12 and above runs straight): v < 0.4 is a stop
    c = Controller(min_pwm=0.12, max_speed=0.3)
    assert c.on_packet(encode_control(1, 0.3, 0.0), now=0.0) == ("motors", (0.0, 0.0))
    left, right = c.on_packet(encode_control(2, 0.5, 0.0), now=0.0)[1]
    assert left == right and abs(left - 0.15) < 1e-9


@pytest.mark.parametrize("kwargs", [
    {"max_speed": -0.3}, {"max_speed": 2.0}, {"k": float("nan")}, {"min_pwm": 0.6, "max_speed": 0.5},
    {"watchdog_s": 0}, {"watchdog_s": 300},
])
def test_unsafe_settings_refuse_to_start(kwargs):
    with pytest.raises(ValueError):
        Controller(**kwargs)


def test_watchdog_stops_once_after_silence():
    c = Controller(watchdog_s=0.3)
    assert c.on_tick(0.0) is None                       # nothing commanded yet: do nothing
    c.on_packet(encode_control(1, 1.0, 0.0), now=1.0)
    assert c.on_tick(1.2) is None                       # within 0.3 s
    assert c.on_tick(1.31) == ("motors", (0.0, 0.0))    # silence too long: stop
    assert c.on_tick(5.0) is None                       # only once


def test_new_command_rearms_watchdog():
    c = Controller(watchdog_s=0.3)
    c.on_packet(encode_control(1, 1.0, 0.0), now=0.0)
    c.on_tick(1.0)
    c.on_packet(encode_control(2, 1.0, 0.0), now=2.0)
    assert c.on_tick(2.1) is None and c.on_tick(2.4) == ("motors", (0.0, 0.0))


def test_garbage_and_stale_packets_ignored():
    c = Controller()
    assert c.on_packet(b"garbage", 0.0) is None
    assert c.on_packet(b'{"seq": 1, "v": NaN, "w": 0}', 0.0) is None
    assert c.on_packet(encode_control(5, 1.0, 0.0), 0.0) is not None
    assert c.on_packet(encode_control(5, -1.0, 0.0), 0.0) is None   # duplicate
    assert c.on_packet(encode_control(4, -1.0, 0.0), 0.0) is None   # out of order


def test_restarted_laptop_is_obeyed_again():
    c = Controller(watchdog_s=0.3)
    for i in range(50):
        c.on_packet(encode_control(i, 1.0, 0.0), now=i * 0.03)
    c.on_tick(2.0)                                       # stream went quiet: watchdog stopped the motors
    assert c.on_packet(encode_control(0, 1.0, 0.0), now=5.0) == ("motors", (0.5, 0.5))  # sender restarted at seq 0


def test_rejected_packet_does_not_feed_watchdog():
    c = Controller(watchdog_s=0.3)
    c.on_packet(encode_control(1, 1.0, 0.0), now=0.0)
    c.on_packet(b"garbage", now=0.25)
    assert c.on_tick(0.31) == ("motors", (0.0, 0.0))


def test_estop_blocks_motor_commands_and_keeps_sending_stop():
    c = Controller(max_speed=0.5)
    assert c.on_packet(encode_control(1, 1.0, 0.0), now=0.0, estop=True) is None   # command ignored while engaged
    assert c.on_tick(0.0, estop=True) == ("motors", (0.0, 0.0))                      # stop right away
    assert c.on_tick(0.1, estop=True) is None                                        # not spammed
    assert c.on_tick(0.26, estop=True) == ("motors", (0.0, 0.0))                     # repeated every 0.25 s
    assert c.on_packet(encode_control(2, 1.0, 0.0), now=0.3, estop=True) is None


def test_commands_resume_only_after_estop_is_released_and_a_new_command_arrives():
    c = Controller(max_speed=0.5, watchdog_s=0.3)
    c.on_packet(encode_control(1, 1.0, 0.0), now=0.0)
    c.on_tick(0.1, estop=True)                                                       # e-stop engages mid-run
    assert c.on_tick(0.2, estop=False) is None                                       # released: no stale motion resumes
    assert c.on_tick(5.0, estop=False) is None                                       # and no leftover command trips the watchdog later
    assert c.on_packet(encode_control(2, 1.0, 0.0), now=0.3) == ("motors", (0.5, 0.5))


def test_estop_does_not_block_audio_clips():
    c = Controller()
    assert c.on_packet(encode_play(1, "guard_ready"), 0.0, estop=True) == ("play", "guard_ready")


def test_play_passthrough_does_not_move_motors():
    c = Controller()
    assert c.on_packet(encode_play(1, "guard_ready"), 0.0) == ("play", "guard_ready")
    assert c.on_tick(10.0) is None


def test_play_clip_never_raises_and_reaps_finished_players(tmp_path):
    (tmp_path / "guard_ready.wav").write_bytes(b"RIFF")

    def no_aplay(cmd):
        raise FileNotFoundError("aplay")

    players = []
    assert "aplay failed" in play_clip(str(tmp_path), "guard_ready", players, popen=no_aplay)   # used to crash the loop
    assert "missing clip" in play_clip(str(tmp_path), "absent", players)

    class Done(object):
        def poll(self):
            return 0

    players.append(Done())
    started = []
    assert play_clip(str(tmp_path), "guard_ready", players, popen=lambda cmd: started.append(cmd) or Done()) is None
    assert started == [["aplay", "-q", str(tmp_path / "guard_ready.wav")]] and len(players) == 1   # the finished one was reaped


def test_locks_onto_one_sender_until_it_goes_quiet():
    c = Controller(max_speed=0.5)
    laptop, other = ("10.0.0.2", 40000), ("10.0.0.66", 5000)
    assert c.on_packet(encode_control(1, 1.0, 0.0), 0.0, src=laptop) is not None
    assert c.on_packet(encode_control(2, -1.0, 0.0), 0.1, src=other) is None      # a second sender is ignored
    assert c.on_packet(encode_control(2, 1.0, 0.0), 0.2, src=laptop) is not None
    assert c.on_packet(encode_control(0, 0.0, 0.0), 1.5, src=other) is not None   # laptop quiet > 1 s: new sender obeyed
    assert c.stats == {"received": 4, "malformed": 0, "stale": 0, "foreign": 1, "accepted": 3}


def test_play_clip_caps_concurrent_players(tmp_path):
    (tmp_path / "alarm.wav").write_bytes(b"RIFF")

    class Playing(object):
        def poll(self):
            return None

    players = [Playing(), Playing()]
    assert play_clip(str(tmp_path), "alarm", players, popen=lambda cmd: Playing()).startswith("busy")
    assert len(players) == 2


def test_trim_changes_the_wheel_ratio_of_a_straight_command():
    def run(trim):
        c = Controller(min_pwm=0.12, max_speed=0.3, trim=trim)
        return c.on_packet(encode_control(1, 1.0, 0.0), now=0.0)[1]
    assert run(0.0) == (0.3, 0.3)
    left, right = run(0.02)
    assert left < 0.3 and abs(left - 0.3 * 0.98 / 1.02) < 1e-9 and right == 0.3          # right wheel stays at the cap: both rescaled, cap holds
    try:
        Controller(trim=0.5)
        assert False, "a trim of 0.5 must be refused"
    except ValueError:
        pass
