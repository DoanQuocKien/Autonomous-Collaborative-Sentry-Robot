"""JetBot multipart recording and the shared offline VideoFrame contract."""
import json
import threading
import time

import cv2
import numpy as np
import pytest
import zmq

from common.protocol import encode_video_header
from sentry.net.frame import VideoFrame
from tools.record import record_jetbot, split_jpegs, watch
from tools.replay import ReplayStream, frame_gaps


@pytest.mark.loopback
def test_record_and_replay_preserve_jpegs_clocks_and_source_resets(tmp_path):
    ctx = zmq.Context()
    pub = ctx.socket(zmq.XPUB)
    pub.setsockopt(zmq.LINGER, 0)
    pub.setsockopt(zmq.RCVTIMEO, 3000)
    port = pub.bind_to_random_port("tcp://127.0.0.1")
    stop = threading.Event()
    errors = []

    def run():
        try:
            record_jetbot("127.0.0.1", port, tmp_path, stop)
        except Exception as exc:
            errors.append(exc)

    worker = threading.Thread(target=run)
    worker.start()
    meta_path = tmp_path / "jetbot_meta.jsonl"
    expected = []
    try:
        assert pub.recv() == b"\x01"
        for index, seq in enumerate([10, 0, 0]):
            image = np.full((24, 32, 3), index * 70, dtype=np.uint8)
            ok, encoded = cv2.imencode(".jpg", image)
            assert ok
            jpeg = encoded.tobytes()
            captured = time.perf_counter() + 100
            pub.send_multipart([encode_video_header(seq, captured, 32, 24), jpeg])
            expected.append((seq, captured, jpeg))
            deadline = time.perf_counter() + 3
            while time.perf_counter() < deadline:
                if meta_path.exists():
                    rows = meta_path.read_text(encoding="utf-8").splitlines()
                    if len(rows) == len(expected):
                        break
                assert not errors, errors
                time.sleep(0.01)
            else:
                pytest.fail("recorder failed to save a complete multipart frame")
    finally:
        stop.set()
        worker.join(3)
        pub.close()
        ctx.term()
    assert not worker.is_alive() and not errors
    metadata = [json.loads(line) for line in meta_path.read_text(encoding="utf-8").splitlines()]
    assert len({item["file"] for item in metadata}) == 3
    stream = ReplayStream(tmp_path)
    for item, (seq, captured, jpeg) in zip(metadata, expected):
        frame = stream.read(timeout=0)
        assert isinstance(frame, VideoFrame)
        assert (frame.seq, frame.t_cap, frame.jpeg) == (seq, captured, jpeg)
        assert (frame.t_rx, frame.t_decode) == (item["t_rx"], item["t_decode"])
        assert frame.t_decode >= frame.t_rx
        assert item["laptop_clock"] == "perf_counter"
        assert np.array_equal(frame.frame_bgr, cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR))
    assert stream.read() is None
    assert stream.read(0) is None
    legacy = list(ReplayStream(tmp_path))
    assert [timestamp for _, timestamp in legacy] == [item[1] for item in expected]


def test_legacy_jetbot_metadata_preserves_capture_time(tmp_path):
    (tmp_path / "jetbot").mkdir()
    ok, jpeg = cv2.imencode(".jpg", np.zeros((24, 32, 3), np.uint8))
    assert ok
    (tmp_path / "jetbot" / "old.jpg").write_bytes(jpeg.tobytes())
    meta = {"seq": 42, "t_cap": 123.5, "w": 32, "h": 24, "file": "old.jpg", "t_local": 1700000000}
    (tmp_path / "jetbot_meta.jsonl").write_text(json.dumps(meta) + "\n", encoding="utf-8")
    before = time.perf_counter()
    frame = ReplayStream(tmp_path).read()
    assert (frame.seq, frame.t_cap) == (42, 123.5)
    assert before <= frame.t_rx <= frame.t_decode <= time.perf_counter()


def test_corrupted_recorded_jpeg_is_rejected(tmp_path):
    (tmp_path / "jetbot").mkdir()
    (tmp_path / "jetbot" / "bad.jpg").write_bytes(b"invalid jpeg")
    meta = {"seq": 1, "t_cap": 1, "w": 32, "h": 24, "file": "bad.jpg"}
    (tmp_path / "jetbot_meta.jsonl").write_text(json.dumps(meta) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JPEG"):
        ReplayStream(tmp_path).read()


def test_a_dead_recorder_stops_the_session_loudly():
    errors = []

    def recorder():
        try:
            raise RuntimeError("video receiver failed")
        except RuntimeError as exc:
            errors.append(exc)

    t = threading.Thread(target=recorder)
    t.start()
    t.join()
    with pytest.raises(SystemExit, match="video receiver failed"):
        watch(t, errors, sleep=lambda s: None)


def test_mjpeg_split_survives_a_stray_end_marker_and_partial_frames():
    a, b = b"\xff\xd8AAA\xff\xd9", b"\xff\xd8BBB\xff\xd9"
    frames, rest = split_jpegs(b"tail of an old picture \xff\xd9 --frame\r\n" + a + b"\r\n--frame\r\n" + b + b"\xff\xd8CC")
    assert frames == [a, b] and rest == b"\xff\xd8CC"   # the old parser stalled on the EOI before the first SOI
    frames, rest = split_jpegs(rest + b"C\xff\xd9")
    assert frames == [b"\xff\xd8CCC\xff\xd9"] and rest == b""
    assert split_jpegs(b"no picture here") == ([], b"")


def test_replay_paces_by_recorded_time():
    frames = [{"t_cap": 10.0}, {"t_cap": 10.05}, {"t_cap": 2.0}, {"t_cap": 2.1}]   # 3rd: the source restarted
    gaps = frame_gaps(frames, 20.0)
    assert gaps[0] == pytest.approx(0.05) and gaps[1] == 0.05 and gaps[2] == pytest.approx(0.1)
    assert gaps[3] == 0.05                     # loop wrap (2.1 -> 10.0 is a pause): default rate
    assert frame_gaps([{"t_local": 1.0}, {"t_local": 1.2}], 15.0)[0] == pytest.approx(0.2)
