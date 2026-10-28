"""Edge conversion parity, robot side and shared input code (Python 3.6, numpy + cv2; tensorrt/pycuda only when engines run).

  docker exec -w /workspace/sentry jetbot_jupyter python3 jetson/parity_run.py /workspace/trt/parity/parity_in.npz /workspace/trt/parity/parity_trt.npz

The laptop (tools/edge_parity.py prep) sends the inputs as uint8 images; BOTH sides turn them into float blobs with the functions below, so the only difference between
the two runs is the engine (TensorRT FP16) against ONNX Runtime FP32. Output arrays are stacked per frame and named like the laptop's (see tools/edge_parity.py).
"""
import sys
import time

import cv2
import numpy as np

MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)
ENGINES = {"det": ("y320_fp16.engine", None), "pose": ("yolov8n-pose_320_op11_fp16.engine", None), "osnet": ("osnet_x0_25_256x128_fp16.engine", None),
           "scrfd": ("det_500m_deconv_fp16.engine", (1, 3, 320, 320)), "mbf": ("w600k_mbf_fp16.engine", (1, 3, 112, 112))}


def yolo_canvas(frame, size=320):
    """Same resize and grey padding as yolo_post.letterbox, before the blob: -> (uint8 canvas, scale, px, py)."""
    h, w = frame.shape[:2]
    scale = min(size / float(w), size / float(h))
    nw, nh = int(round(w * scale)), int(round(h * scale))
    img = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LINEAR)
    px, py = (size - nw) // 2, (size - nh) // 2
    canvas = np.full((size, size, 3), 114, np.uint8)
    canvas[py:py + nh, px:px + nw] = img
    return canvas, scale, px, py


def yolo_blob(canvas):
    return cv2.dnn.blobFromImage(canvas, 1.0 / 255.0, swapRB=True)


def scrfd_canvas(frame, size=320):
    """Same as face_post.scrfd_input before the blob: -> (uint8 canvas, scale)."""
    h, w = frame.shape[:2]
    scale = min(size / float(w), size / float(h))
    nw, nh = int(round(w * scale)), int(round(h * scale))
    canvas = np.zeros((size, size, 3), np.uint8)
    canvas[:nh, :nw] = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LINEAR)
    return canvas, scale


def scrfd_blob(canvas, size=320):
    return cv2.dnn.blobFromImage(canvas, 1.0 / 128.0, (size, size), (127.5, 127.5, 127.5), swapRB=True)


def osnet_blob(crop_bgr):
    """crop_bgr: uint8 (256,128,3) -> (1,3,256,128), as edge_bench.reid_blob."""
    c = crop_bgr[:, :, ::-1].astype(np.float32) / 255.0
    return np.ascontiguousarray(((c - MEAN) / STD).transpose(2, 0, 1)[None])


def mbf_blob(face112):
    return cv2.dnn.blobFromImage(face112, 1.0 / 127.5, (112, 112), (127.5, 127.5, 127.5), swapRB=True)


def stack_outputs(prefix, per_frame, sort_by_shape=False):
    """list (frames) of lists (outputs) -> {name: stacked array}. SCRFD outputs come in another order from TensorRT: they are named by their shape."""
    res = {}
    for k in range(len(per_frame[0])):
        name = "%s_%d_%d" % (prefix, per_frame[0][k].shape[0], per_frame[0][k].shape[1]) if sort_by_shape else "%s_%d" % (prefix, k)
        res[name] = np.stack([np.asarray(o[k], np.float32).reshape(o[k].shape[1:] if not sort_by_shape else o[k].shape) for o in per_frame])
    return res


def run_engines(inp, trt_dir="/workspace/trt/"):
    import trt_runtime
    out = {}
    plan = [("det", inp["yolo_canvas"], yolo_blob, False), ("pose", inp["yolo_canvas"], yolo_blob, False), ("osnet", inp["osnet_crop"], osnet_blob, False),
            ("scrfd", inp["scrfd_canvas"], scrfd_blob, True), ("mbf", inp["mbf_face"], mbf_blob, False)]
    for name, imgs, blob_fn, by_shape in plan:
        eng_file, shape = ENGINES[name]
        eng = trt_runtime.TrtEngine(trt_dir + eng_file, input_shape=shape)
        t0 = time.time()
        per = [eng.infer(blob_fn(im)) for im in imgs]
        print("%-6s %4d inputs, %.1f ms each, outputs %s" % (name, len(imgs), 1000 * (time.time() - t0) / len(imgs), [tuple(o.shape) for o in per[0]]), flush=True)
        out.update(stack_outputs(name, per, sort_by_shape=by_shape))
        del eng
    return out


def main():
    inp = dict(np.load(sys.argv[1]))
    out = run_engines(inp)
    np.savez_compressed(sys.argv[2], **out)
    print("saved", sys.argv[2], sorted(out))


if __name__ == "__main__":
    main()
