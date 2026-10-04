"""Local transport integration; no robot, Wi-Fi, models, or motor commands."""
import socket
import threading
import time

import cv2
import numpy as np
import pytest
import zmq

from common.protocol import (decode_clock_request, decode_control, encode_clock_reply,
                             encode_video_header)
from sentry.net.clock_sync import synchronize
from sentry.net.udp_tx import UDPSender
from sentry.net.zmq_rx import ZMQReceiver

pytestmark = pytest.mark.loopback


def test_clock_echo_ignores_bad_and_stale_replies():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as echo:
        echo.bind(("127.0.0.1", 0))
        echo.settimeout(2)
        errors = []

        def run():
            try:
                for _ in range(20):
                    data, addr = echo.recvfrom(512)
                    t0 = decode_clock_request(data)
                    echo.sendto(b"bad json", addr)
                    echo.sendto(encode_clock_reply(t0 - 1, time.perf_counter()), addr)
                    echo.sendto(encode_clock_reply(t0, time.perf_counter() + 100), addr)
            except Exception as exc:
                errors.append(exc)

        worker = threading.Thread(target=run)
        worker.start()
        try:
            estimate = synchronize("127.0.0.1", echo.getsockname()[1], timeout_s=1)
        finally:
            worker.join(3)
        assert not worker.is_alive() and not errors
        assert estimate.samples == 20
        assert estimate.offset_s == pytest.approx(100, abs=estimate.rtt_s / 2 + 0.001)


def test_clock_timeout():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as silent:
        silent.bind(("127.0.0.1", 0))
        with pytest.raises(TimeoutError):
            synchronize("127.0.0.1", silent.getsockname()[1], samples=1, timeout_s=0.02)


def test_udp_packets_and_exit_stop():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sink:
        sink.bind(("127.0.0.1", 0))
        sink.settimeout(2)
        with UDPSender("127.0.0.1", sink.getsockname()[1]) as sender:
            sender.send(0.3, -0.2)
            command = decode_control(sink.recv(512))
        stop = decode_control(sink.recv(512))
    assert command == {"seq": 0, "v": 0.3, "w": -0.2}
    assert stop == {"seq": 1, "v": 0.0, "w": 0.0}


def test_multipart_latest_slot_bad_jpeg_restart_and_shutdown():
    ctx = zmq.Context()
    pub = ctx.socket(zmq.XPUB)
    pub.setsockopt(zmq.RCVTIMEO, 2000)
    pub.setsockopt(zmq.LINGER, 0)
    port = pub.bind_to_random_port("tcp://127.0.0.1")
    ok, jpeg = cv2.imencode(".jpg", np.zeros((48, 64, 3), np.uint8))
    assert ok
    rx = ZMQReceiver("127.0.0.1", port)
    try:
        rx.start()
        assert pub.recv() == b"\x01"  # actual SUB handshake; no arbitrary startup sleep

        def send_and_wait(seq):
            pub.send_multipart([encode_video_header(seq, time.monotonic(), 64, 48), jpeg.tobytes()])
            with rx._condition:
                assert rx._condition.wait_for(
                    lambda: rx._latest is not None and rx._latest.seq == seq, timeout=2)

        send_and_wait(10)
        send_and_wait(11)  # consumer intentionally did not read 10
        assert rx.read(0).seq == 11
        assert rx.read(0.01) is None
        pub.send_multipart([encode_video_header(12, 0, 64, 48), b"bad jpeg"])
        # Next valid frame must recover; sequence reset is preserved for telemetry.
        send_and_wait(0)
        assert rx.read(0).seq == 0
        assert rx.skipped >= 1
        send_and_wait(1)  # closing must discard a pending latest frame
        rx.close()
        assert rx.read(0) is None
        assert not rx._thread.is_alive()
    finally:
        rx.close()
        pub.close()
        ctx.term()


def test_close_wakes_reader_waiting_without_a_publisher():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as unused:
        unused.bind(("127.0.0.1", 0))
        port = unused.getsockname()[1]
        rx = ZMQReceiver("127.0.0.1", port).start()
        values = []
        reader = threading.Thread(target=lambda: values.append(rx.read()))
        reader.start()
        try:
            rx.close()
            reader.join(2)
            assert not reader.is_alive()
            assert values == [None]
        finally:
            rx.close()


def test_receiver_startup_error_is_visible_and_resources_close():
    rx = ZMQReceiver(endpoint="unsupported://missing")
    try:
        with pytest.raises(RuntimeError, match="video receiver failed"):
            rx.start()
    finally:
        rx.close()
    assert not rx._thread.is_alive()
