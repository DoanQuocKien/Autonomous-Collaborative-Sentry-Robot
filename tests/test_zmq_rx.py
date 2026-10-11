import cv2
import numpy as np
import pytest

from common.protocol import encode_video_header
from sentry.net.zmq_rx import ZMQReceiver, decode_frame


def packet(seq=1, w=64, h=48):
    frame = np.full((h, w, 3), (10, 80, 200), np.uint8)
    ok, jpeg = cv2.imencode(".jpg", frame)
    assert ok
    return [encode_video_header(seq, 123.5, w, h), jpeg.tobytes()]


def test_decode_preserves_timestamps_jpeg_and_bgr():
    parts = packet()
    frame = decode_frame(parts, 50, clock=lambda: 50.001)
    assert (frame.seq, frame.t_cap, frame.t_rx, frame.t_decode) == (1, 123.5, 50, 50.001)
    assert (frame.w, frame.h) == (64, 48)
    assert frame.jpeg == parts[1]
    assert frame.frame_bgr.shape == (48, 64, 3)
    assert np.max(np.abs(frame.frame_bgr[0, 0].astype(int) - [10, 80, 200])) <= 3


@pytest.mark.parametrize("parts", [[], [b"header"], [b"{}", b"bad"],
                                   [encode_video_header(1, 0, 64, 48), b""],
                                   [encode_video_header(1, 0, 64, 48), b"not a jpeg"],
                                   [encode_video_header(1, 0, 1, 1), packet()[1]],
                                   [encode_video_header(-1, 0, 64, 48), packet()[1]]])
def test_invalid_frames(parts):
    with pytest.raises(ValueError):
        decode_frame(parts, 0)


@pytest.mark.parametrize("fail_at", ["context", "socket"])
def test_socket_creation_failure_wakes_readers_and_cleans_up(monkeypatch, fail_at):
    class ContextStub:
        terminated = False

        def socket(self, *args):
            raise OSError("socket creation failed")

        def term(self):
            self.terminated = True

    ctx = ContextStub()

    def make_context():
        if fail_at == "context":
            raise OSError("context creation failed")
        return ctx

    monkeypatch.setattr("sentry.net.zmq_rx.zmq.Context", make_context)
    rx = ZMQReceiver()
    try:
        with pytest.raises(RuntimeError, match="video receiver failed") as error:
            rx.start()
        assert isinstance(error.value.__cause__, OSError)
        with pytest.raises(RuntimeError, match="video receiver failed"):
            rx.read(0)
    finally:
        rx.close()
    assert not rx._thread.is_alive()
    assert fail_at == "context" or ctx.terminated
