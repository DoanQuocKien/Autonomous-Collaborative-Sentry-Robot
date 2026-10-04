import threading

import cv2
import numpy as np
import zmq

from common.protocol import decode_video_header
from jetson.camera_pub import gst_pipeline, serve, synthetic_frames


def test_gst_pipeline_mentions_requested_sizes():
    s = gst_pipeline(3, 1640, 1232, 20, 640, 480)
    assert "sensor-mode=3" in s and "width=1640" in s and "width=(int)640" in s and "framerate=(fraction)20/1" in s


def test_synthetic_stream_loopback():
    ctx = zmq.Context()
    pub = ctx.socket(zmq.PUB)
    port = pub.bind_to_random_port("tcp://127.0.0.1")
    sub = ctx.socket(zmq.SUB)
    sub.setsockopt(zmq.SUBSCRIBE, b"")
    sub.setsockopt(zmq.RCVTIMEO, 3000)
    sub.connect("tcp://127.0.0.1:%d" % port)
    # SUB connects asynchronously, so early frames can be lost: publish plenty
    t = threading.Thread(target=serve, args=(pub, synthetic_frames(640, 480, 100)), kwargs={"max_frames": 100})
    t.start()
    try:
        got = [sub.recv_multipart() for _ in range(3)]
    finally:
        t.join()
        sub.close(); pub.close(); ctx.term()
    heads = [decode_video_header(g[0]) for g in got]
    assert all((h["w"], h["h"]) == (640, 480) for h in heads)
    assert heads[0]["seq"] < heads[1]["seq"] < heads[2]["seq"]
    assert heads[0]["t_cap"] < heads[2]["t_cap"]
    img = cv2.imdecode(np.frombuffer(got[0][1], np.uint8), cv2.IMREAD_COLOR)
    assert img.shape == (480, 640, 3)
