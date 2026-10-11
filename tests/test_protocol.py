import pytest

from common import protocol as p


def test_control_roundtrip_and_clamp():
    assert p.decode_control(p.encode_control(3, 0.5, -0.25)) == {"seq": 3, "v": 0.5, "w": -0.25}
    msg = p.decode_control(p.encode_control(1, 5, -9))
    assert (msg["v"], msg["w"]) == (1.0, -1.0)


def test_play_roundtrip():
    assert p.decode_control(p.encode_play(7, "guard_ready")) == {"seq": 7, "play": "guard_ready"}


@pytest.mark.parametrize("bad", [
    b"", b"\xff\xfe", b"[]", b"42", b'{"v": 0, "w": 0}',          # not JSON object / no seq
    b'{"seq": true, "v": 0, "w": 0}', b'{"seq": 1.5, "v": 0, "w": 0}',
    b'{"seq": 1, "v": NaN, "w": 0}', b'{"seq": 1, "v": Infinity, "w": 0}',
    b'{"seq": 1, "v": "1", "w": 0}', b'{"seq": 1, "v": 0}',
    b'{"seq": 1, "play": "../etc/passwd"}', b'{"seq": 1, "play": "a b"}',
    b'{"seq": 1, "play": "X"}', b'{"seq": 1, "play": 5}',
])
def test_decode_control_rejects(bad):
    with pytest.raises(ValueError):
        p.decode_control(bad)


def test_seq_filter():
    f = p.SeqFilter(quiet_s=1.0)
    assert f.accept(10, 0.0) and not f.accept(10, 0.1) and not f.accept(9, 0.2) and f.accept(11, 0.3)
    assert not f.accept(1, 0.4)        # stream is live: old seq is stale, not a restart


def test_seq_filter_accepts_restarted_sender_after_silence():
    f = p.SeqFilter(quiet_s=1.0)
    assert f.accept(500, 0.0)
    assert not f.accept(0, 0.9)        # within 1 s of the last packet: still stale
    assert f.accept(0, 2.5)            # silent > 1 s: sender restarted, seq starts over
    assert f.accept(1, 2.6) and not f.accept(1, 2.7)


def test_video_header_roundtrip_and_reject():
    h = p.decode_video_header(p.encode_video_header(4, 12.5, 640, 480))
    assert h == {"seq": 4, "t_cap": 12.5, "w": 640, "h": 480}
    with pytest.raises(ValueError):
        p.decode_video_header(b'{"seq": 1, "t_cap": NaN, "w": 640, "h": 480}')


def test_clock_roundtrip():
    assert p.decode_clock_request(p.encode_clock_request(1.25)) == 1.25
    assert p.decode_clock_reply(p.encode_clock_reply(1.25, 99.5)) == (1.25, 99.5)
    with pytest.raises(ValueError):
        p.decode_clock_request(b'{"t0": "x"}')


@pytest.mark.parametrize("decode,packet", [
    (p.decode_control, p.encode_control(1, 10 ** 400, 0)),
    (p.decode_video_header, p.encode_video_header(1, 10 ** 400, 640, 480)),
    (p.decode_clock_request, p.encode_clock_request(10 ** 400)),
    (p.decode_clock_reply, p.encode_clock_reply(0, 10 ** 400)),
], ids=["control", "video", "clock_request", "clock_reply"])
def test_oversized_numbers_are_invalid_packets(decode, packet):
    with pytest.raises(ValueError):
        decode(packet)
