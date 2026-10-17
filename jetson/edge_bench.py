"""On-robot bench for the edge-deployment study (Python 3.6, run INSIDE the JetBot container; does not touch the motors).

    docker exec -w /workspace/sentry jetbot_jupyter python3 jetson/edge_bench.py --mode stageB --seconds 60

Reads the live frames camera_pub.py publishes on tcp://127.0.0.1:5555 (JPEG), always takes the NEWEST frame, and runs:
  decode  JPEG decode only (the CPU floor)
  det     YOLOv8n detector every frame
  stageC  stageB + the door pipeline at 5 Hz on a still image: SCRFD faces -> 5-point align -> MobileFaceNet -> whitelist cosine
  stageB  YOLOv8n-pose every frame + YOLOv8n detector every 3rd frame (obstacles at one third of the rate)
          + OSNet-x0.25 on the largest person every 15th frame (stands in for 'a new track')
Reports per-stage ms (mean / p50 / p95), frames per second, skipped frames and the capture-to-result time
(t_cap is time.monotonic() on this machine, so no clock offset). Engines come from `trtexec --onnx ... --fp16`, built ON the robot.
"""
import argparse
import json
import os
import sys
import threading
import time

import cv2
import numpy as np
import zmq

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common.protocol import decode_video_header  # noqa: E402
import face_post  # noqa: E402
import trt_runtime  # noqa: E402
import yolo_post  # noqa: E402

ENGINES = {"det": "y320_fp16.engine", "pose": "yolov8n-pose_320_op11_fp16.engine", "reid": "osnet_x0_25_256x128_fp16.engine",
           "scrfd": "det_500m_deconv_fp16.engine", "scrfd_fp32": "det_500m_deconv_fp32.engine", "mbf": "w600k_mbf_fp16.engine"}
MEAN, STD = np.array([0.485, 0.456, 0.406], np.float32), np.array([0.229, 0.224, 0.225], np.float32)


def reid_blob(frame, box):
    h, w = frame.shape[:2]
    x0, y0, x1, y1 = [int(v) for v in box]
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
    if x1 - x0 < 8 or y1 - y0 < 8:
        return None
    crop = cv2.resize(frame[y0:y1, x0:x1], (128, 256))[:, :, ::-1].astype(np.float32) / 255.0
    return np.ascontiguousarray(((crop - MEAN) / STD).transpose(2, 0, 1)[None])


def newest(sock, timeout_ms=3000):
    if not sock.poll(timeout_ms):
        return None
    parts = sock.recv_multipart()
    while sock.poll(0):                      # drop older frames: a controller only wants the latest
        parts = sock.recv_multipart()
    return parts


def stats(v):
    a = np.asarray(v, np.float64) * 1000.0
    return {"n": int(a.size), "mean": round(float(a.mean()), 2), "p50": round(float(np.percentile(a, 50)), 2), "p95": round(float(np.percentile(a, 95)), 2)} if a.size else {"n": 0}


def door_once(eng, img, ref):
    """Door pipeline on one frame: SCRFD faces -> 5-point align -> MobileFaceNet -> whitelist cosine. -> (times dict, n_faces, ref embedding)."""
    d0 = time.monotonic()
    fb, fs = face_post.scrfd_input(img, 320)
    d1 = time.monotonic()
    souts = eng["scrfd"].infer(fb)
    d2 = time.monotonic()
    _, _, kps = face_post.decode_scrfd(souts, fs, 320, 0.5)
    d3 = time.monotonic()
    mbf = []
    for kp5 in kps:
        m0 = time.monotonic()
        e = face_post.unit(eng["mbf"].infer(face_post.embed_blob(face_post.align(img, kp5)))[0])
        if ref is None:
            ref = e
        _ = float(e @ ref)                                          # whitelist cosine (one enrolled face)
        mbf.append(time.monotonic() - m0)
    return {"door_pre": d1 - d0, "door_scrfd": d2 - d1, "door_post": d3 - d2, "door_mbf": mbf, "door": time.monotonic() - d0}, len(kps), ref


def door_worker(eng, img, period, stop, out):
    """Runs door_once at 1/period Hz in its own thread (own engines, own CUDA stream; the CUDA context is shared)."""
    import pycuda.autoinit
    pycuda.autoinit.context.push()
    ref, nxt = None, time.monotonic()
    try:
        while not stop.is_set():
            t, n, ref = door_once(eng, img, ref)
            out.append((t, n))
            nxt += period
            delay = nxt - time.monotonic()
            if delay > 0:
                stop.wait(delay)
            else:
                nxt = time.monotonic()
    finally:
        pycuda.autoinit.context.pop()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["decode", "det", "stageB", "stageC"], default="stageB")
    ap.add_argument("--seconds", type=float, default=60)
    ap.add_argument("--trt-dir", default="/workspace/trt")
    ap.add_argument("--url", default="tcp://127.0.0.1:5555")
    ap.add_argument("--door-every", type=int, default=4, help="frames between door-pipeline runs (4 at 20 fps = 5 Hz)")
    ap.add_argument("--door-thread", action="store_true", help="run the door pipeline in its own thread at 5 Hz instead of inside the frame loop")
    ap.add_argument("--door-image", default="/workspace/trt/demo/zidane.jpg", help="still image with faces standing in for the ESP32-CAM frame")
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--det-every", type=int, default=3)
    ap.add_argument("--reid-every", type=int, default=15)
    a = ap.parse_args()

    eng = {}
    if a.mode in ("det", "stageB", "stageC"):
        eng["det"] = trt_runtime.TrtEngine(os.path.join(a.trt_dir, ENGINES["det"]))
    if a.mode in ("stageB", "stageC"):
        eng["pose"] = trt_runtime.TrtEngine(os.path.join(a.trt_dir, ENGINES["pose"]))
        eng["reid"] = trt_runtime.TrtEngine(os.path.join(a.trt_dir, ENGINES["reid"]))
    door_img, door_ref = None, None
    if a.mode == "stageC":
        sc_path = os.path.join(a.trt_dir, ENGINES["scrfd"])          # built from det_500m_deconv320.onnx (tools.export_edge_onnx --only scrfd)
        if not os.path.exists(sc_path):
            sc_path = os.path.join(a.trt_dir, ENGINES["scrfd_fp32"])
        eng["scrfd"] = trt_runtime.TrtEngine(sc_path, input_shape=(1, 3, 320, 320))
        eng["mbf"] = trt_runtime.TrtEngine(os.path.join(a.trt_dir, ENGINES["mbf"]), input_shape=(1, 3, 112, 112))
        door_img = cv2.imread(a.door_image)
        if door_img is None:
            sys.exit("cannot read %s" % a.door_image)
    size = eng["det"].input_shape[-1] if "det" in eng else 320
    for e in eng.values():                   # warm-up: first calls include lazy CUDA init
        e.infer(np.zeros(e.input_shape, np.float32))

    sock = zmq.Context().socket(zmq.SUB)
    sock.setsockopt(zmq.SUBSCRIBE, b"")
    sock.setsockopt(zmq.RCVHWM, 2)
    sock.connect(a.url)

    T = {k: [] for k in ("decode", "pre", "pose", "pose_post", "det", "det_post", "reid", "door_pre", "door_scrfd", "door_post", "door_mbf", "door", "compute", "e2e")}
    n_faces, n_door = 0, 0
    n_people, n_boxes, skipped, last_seq, frames, i = 0, 0, 0, None, 0, 0
    t_start = None
    stop, door_out, worker = threading.Event(), [], None
    if a.mode == "stageC" and a.door_thread:
        worker = threading.Thread(target=door_worker, args=(eng, door_img, a.door_every / 20.0, stop, door_out))
        worker.daemon = True
        worker.start()
    while True:
        parts = newest(sock)
        if parts is None:
            print("no frame for 3 s: is camera_pub running?")
            break
        t0 = time.monotonic()
        if t_start is None:
            t_start = t0
        if t0 - t_start > a.seconds:
            break
        hdr = decode_video_header(parts[0])
        if last_seq is not None and hdr["seq"] > last_seq + 1:
            skipped += hdr["seq"] - last_seq - 1
        last_seq = hdr["seq"]
        frame = cv2.imdecode(np.frombuffer(parts[1], np.uint8), cv2.IMREAD_COLOR)
        t1 = time.monotonic(); T["decode"].append(t1 - t0)
        if a.mode != "decode":
            blob, scale, px, py = yolo_post.letterbox(frame, size)
            t2 = time.monotonic(); T["pre"].append(t2 - t1)
            people = []
            if a.mode in ("stageB", "stageC"):
                out = eng["pose"].infer(blob)[0]
                t3 = time.monotonic(); T["pose"].append(t3 - t2)
                boxes, scores, cls, kp = yolo_post.decode(out, scale, px, py, a.conf, n_kpt=17)
                t4 = time.monotonic(); T["pose_post"].append(t4 - t3)
                people = boxes
                n_people += len(boxes)
                if i % a.det_every == 0:
                    out = eng["det"].infer(blob)[0]
                    t5 = time.monotonic(); T["det"].append(t5 - t4)
                    n_boxes += len(yolo_post.decode(out, scale, px, py, a.conf)[0])
                    T["det_post"].append(time.monotonic() - t5)
                if len(people) and i % a.reid_every == 0:
                    t6 = time.monotonic()
                    big = people[np.argmax((people[:, 2] - people[:, 0]) * (people[:, 3] - people[:, 1]))]
                    rb = reid_blob(frame, big)
                    if rb is not None:
                        eng["reid"].infer(rb)
                    T["reid"].append(time.monotonic() - t6)
                if a.mode == "stageC" and not a.door_thread and i % a.door_every == 0:
                    t, nf, door_ref = door_once(eng, door_img, door_ref)
                    for k in ("door_pre", "door_scrfd", "door_post", "door"):
                        T[k].append(t[k])
                    T["door_mbf"].extend(t["door_mbf"])
                    n_faces += nf; n_door += 1
            else:
                out = eng["det"].infer(blob)[0]
                t3 = time.monotonic(); T["det"].append(t3 - t2)
                n_boxes += len(yolo_post.decode(out, scale, px, py, a.conf)[0])
                T["det_post"].append(time.monotonic() - t3)
        t_end = time.monotonic()
        T["compute"].append(t_end - t0)
        T["e2e"].append(t_end - hdr["t_cap"])
        frames += 1
        i += 1

    stop.set()
    if worker is not None:
        worker.join(5)
        for t, nf in list(door_out):
            for k in ("door_pre", "door_scrfd", "door_post", "door"):
                T[k].append(t[k])
            T["door_mbf"].extend(t["door_mbf"])
            n_faces += nf; n_door += 1
    wall = (time.monotonic() - t_start) if t_start else 0
    res = {"mode": a.mode, "seconds": round(wall, 1), "frames": frames, "fps": round(frames / wall, 2) if wall else 0,
           "skipped_by_newest_only": skipped, "avg_people": round(n_people / max(frames, 1), 2), "door_thread": bool(a.door_thread), "door_runs": n_door, "avg_faces_per_door_run": round(n_faces / max(n_door, 1), 2), "avg_obstacle_boxes_on_det_frames": None,
           "stage_ms": {k: stats(v) for k, v in T.items() if v}}
    print(json.dumps(res, indent=1))
    with open(os.path.join(a.trt_dir, "bench_%s.json" % a.mode), "w") as f:
        json.dump(res, f)


if __name__ == "__main__":
    main()
