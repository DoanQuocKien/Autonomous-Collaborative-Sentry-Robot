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


def camera_frames(pipeline, open_capture=lambda p: cv2.VideoCapture(p, cv2.CAP_GSTREAMER), retries=5,
                  sleep=time.sleep):
    """Yield BGR frames. A failed read reopens the pipeline (nvargus hiccups happen) up to `retries` times in a row
    before giving up, instead of exiting on the first bad frame and leaving systemd's 5 s restart gap."""
    failures = 0
    while True:
        cap = open_capture(pipeline)
        try:
            if not cap.isOpened():
                failures += 1
            else:
                while True:
                    ok, frame = cap.read()
                    if not ok:
                        failures += 1
                        break
                    failures = 0
                    yield frame
        finally:
            cap.release()
        if failures > retries:
            raise SystemExit("camera failed %d times in a row: %s" % (failures, pipeline))
        print("camera read failed (%d of %d); reopening" % (failures, retries))
        sys.stdout.flush()
        sleep(min(2.0, 0.2 * failures))


def synthetic_frames(w, h, fps, sleep=time.sleep):
    """Yield a paced test pattern; tools can inject an interruptible sleep."""
    i = 0
    while True:
        frame = np.zeros((h, w, 3), np.uint8)
        x = (i * 8) % w
        cv2.rectangle(frame, (x, 0), (min(x + 40, w - 1), h - 1), (0, 255, 0), -1)
        cv2.putText(frame, "synthetic %d" % i, (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        yield frame
        i += 1
        sleep(1.0 / fps)


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


def _size(text):
    try:
        w, h = [int(s) for s in text.lower().split("x")]
    except ValueError:
        raise argparse.ArgumentTypeError("expected WxH, e.g. 1640x1232")
    if w <= 0 or h <= 0:
        raise argparse.ArgumentTypeError("sizes must be positive")
    return w, h


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["camera", "synthetic"], default="camera")
    ap.add_argument("--port", type=int, default=PORT_VIDEO)
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--fps", type=int, default=20)
    ap.add_argument("--quality", type=int, default=60)
    ap.add_argument("--sensor-mode", type=int, default=3)
    ap.add_argument("--capture-size", type=_size, default="1640x1232", help="sensor capture WxH (4:3 keeps the full fisheye FOV)")
    args = ap.parse_args()

    if args.source == "camera":
        cap_w, cap_h = args.capture_size
        frames = camera_frames(gst_pipeline(args.sensor_mode, cap_w, cap_h, args.fps, args.width, args.height))
    else:
        frames = synthetic_frames(args.width, args.height, args.fps)

    sock = zmq.Context().socket(zmq.PUB)
    sock.setsockopt(zmq.SNDHWM, 2)  # a slow laptop gets the newest frames, never a growing backlog
    sock.bind("tcp://*:%d" % args.port)
    serve(sock, frames, args.quality)


if __name__ == "__main__":
    main()
