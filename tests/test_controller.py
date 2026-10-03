from common.protocol import encode_control, encode_play
from jetson.robot_udp import Controller


def test_command_is_mixed_capped_and_deadzoned():
    c = Controller(k=1.0, min_pwm=0.0, max_speed=0.5)
    assert c.on_packet(encode_control(1, 1.0, 0.0), now=0.0) == ("motors", (0.5, 0.5))
    assert c.on_packet(encode_control(2, 0.0, 1.0), now=0.0) == ("motors", (-0.5, 0.5))
    # deadzone applies AFTER the cap: 0.5 * 0.4 = 0.2 < 0.25 -> wheel stays still
    c = Controller(min_pwm=0.25, max_speed=0.5)
    assert c.on_packet(encode_control(1, 0.4, 0.0), now=0.0) == ("motors", (0.0, 0.0))


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


def test_play_passthrough_does_not_move_motors():
    c = Controller()
    assert c.on_packet(encode_play(1, "guard_ready"), 0.0) == ("play", "guard_ready")
    assert c.on_tick(10.0) is None
