#!/usr/bin/env python3
"""Jetson: camera -> JPEG -> ZeroMQ PUB (port 5555).  Python 3.6.

DRAFT: the GStreamer pipeline and sensor mode are NOT yet tested on the real robot;
tune --sensor-mode / --capture-size against `nvgstcapture-1.0` output (docs/JetBot Notes.md).
`--source synthetic` publishes a moving test pattern with the SAME wire format, so
the laptop receivers can be developed and tested without the robot.

Frame = 2 ZeroMQ parts: [header JSON (common.protocol), JPEG bytes].
t_cap is taken just after the frame is read, so it slightly UNDERestimates true capture latency.
"""
import argparse
import os
import sys
import time

import cv2
import numpy as np
import zmq

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.protocol import PORT_VIDEO, encode_video_header  # noqa: E402


def gst_pipeline(sensor_mode, cap_w, cap_h, fps, w, h):
    return ("nvarguscamerasrc sensor-mode=%d ! video/x-raw(memory:NVMM), width=%d, height=%d, "
            "format=(string)NV12, framerate=(fraction)%d/1 ! nvvidconv ! "
            "video/x-raw, width=(int)%d, height=(int)%d, format=(string)BGRx ! "
            "videoconvert ! video/x-raw, format=BGR ! appsink drop=1 max-buffers=1"
            % (sensor_mode, cap_w, cap_h, fps, w, h))


def camera_frames(pipeline):
    cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
    if not cap.isOpened():
        raise SystemExit("camera pipeline failed to open: " + pipeline)
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                raise SystemExit("camera read failed")
            yield frame
    finally:
        cap.release()


def synthetic_frames(w, h, fps):
    i = 0
    while True:
        frame = np.zeros((h, w, 3), np.uint8)
        x = (i * 8) % w
        cv2.rectangle(frame, (x, 0), (min(x + 40, w - 1), h - 1), (0, 255, 0), -1)
        cv2.putText(frame, "synthetic %d" % i, (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        yield frame
        i += 1
        time.sleep(1.0 / fps)


def serve(sock, frames, quality=60, max_frames=None, clock=time.monotonic):
    seq = 0
    for frame in frames:
        t_cap = clock()
        ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if ok:
            h, w = frame.shape[:2]
            sock.send_multipart([encode_video_header(seq, t_cap, w, h), jpg.tobytes()])
            seq += 1
        if max_frames is not None and seq >= max_frames:
            break


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["camera", "synthetic"], default="camera")
    ap.add_argument("--port", type=int, default=PORT_VIDEO)
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--fps", type=int, default=20)
    ap.add_argument("--quality", type=int, default=60)
    ap.add_argument("--sensor-mode", type=int, default=3)
    ap.add_argument("--capture-size", default="1640x1232", help="sensor capture WxH (4:3 keeps the full fisheye FOV)")
    args = ap.parse_args()

    if args.source == "camera":
        cap_w, cap_h = [int(s) for s in args.capture_size.split("x")]
        frames = camera_frames(gst_pipeline(args.sensor_mode, cap_w, cap_h, args.fps, args.width, args.height))
    else:
        frames = synthetic_frames(args.width, args.height, args.fps)

    sock = zmq.Context().socket(zmq.PUB)
    sock.setsockopt(zmq.SNDHWM, 2)  # a slow laptop gets the newest frames, never a growing backlog
    sock.bind("tcp://*:%d" % args.port)
    serve(sock, frames, args.quality)


if __name__ == "__main__":
    main()
