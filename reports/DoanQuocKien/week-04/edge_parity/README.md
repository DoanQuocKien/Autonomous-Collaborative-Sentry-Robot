# Edge conversion parity, TensorRT FP16 on the robot against ONNX Runtime FP32 (DQK, 2026-10-28)

The 'Edge conversion parity' row of plan section 4.3 and the second half of gate G1. Same inputs on both sides, so the only difference is the engine: the five engines the robot bench uses (`det` YOLOv8n 320, `pose` YOLOv8n-pose 320, `osnet` OSNet x0.25 256x128, `scrfd` SCRFD det_500m 320 with the Resize fix, `mbf` MobileFaceNet) built on the robot with `trtexec --fp16`, against ONNX Runtime FP32 (CPU) on the laptop using **the robot's own ONNX files** (the laptop's SCRFD copy differs by 12 bytes).

Inputs (`tools/edge_parity.py prep`): 200 D1 obstacle frames (no faces, `data/D1_obstacles_1015`, evenly spaced over 628) plus 8 public photos (ultralytics bus and zidane, insightface t1 and Tom Hanks, each also flipped) for the detectors and SCRFD; 200 256x128 crops of the D1 frames for OSNet; 66 aligned public faces (each also 0.7x and 1.3x brightness) for MobileFaceNet. Inputs travel as uint8 images and both sides run the same float conversion (`jetson/parity_run.py`, tested equal to the bench's `letterbox` and `scrfd_input` blobs). Run on the robot with `jetson/parity_run.py`, compare with `tools/edge_parity.py compare`. Raw files (`data/parity/`, 350 MB) stay local; `parity_results.json` is here.

| Plan criterion | Result | |
| :-- | :-- | :-- |
| Cosine >= 0.999 on every output | **13 of 13 outputs pass.** Lowest of any frame: MobileFaceNet 0.999972, OSNet 0.999982, SCRFD maps 0.999989 to 1.0, YOLOv8n 0.999996, YOLOv8n-pose 0.999999 | met |
| Detector boxes matched at IoU >= 0.9 for >= 95 % of detections | YOLOv8n 557 of 562 = **99.1 %**; pose 81 of 81 = 100 %; SCRFD 22 of 22 faces = 100 % (landmark error 0.03 px mean) | met |
| ... and the same count | pose and SCRFD: same count in 208 of 208 images. YOLOv8n: same count in **205 of 208** images, 562 detections in ONNX against 559 in TensorRT | **not exact** |

The YOLOv8n differences: five boxes of ONNX that TensorRT does not reproduce at IoU >= 0.9, all **chairs** (COCO class 56) with scores of 0.252 to 0.340 against the 0.25 threshold, in three frames (61, 125, 139): in FP16 the same chair gets a somewhat different box (IoU 0.30 to 0.70) or falls below the threshold. Read plainly: the conversion is faithful (cosines above 0.99999 on the detector), but the literal 'same count' is missed in 3 of 208 images by one borderline chair box each. Whether that counts as met is for the team (HNHL owns the thresholds); it is not rounded up here.

Robot time per image in the run (including the blob and the copy to the GPU, not a bench): pose 21.5 ms, OSNet 16.3 ms, SCRFD 12.6 ms, MobileFaceNet 16.0 ms (the YOLOv8n line was cut from the log).

What this does not cover: XFeat, DINOv2 and OSNet-AIN (not used by the robot bench; the 2026-10-16 public-photo check gave >= 0.9999), the detector on persons (the D1 frames are chairs and empty floor: the 81 pose boxes and 22 faces come mostly from the public photos), INT8 (out of scope), and the glossy-floor distance parity of the Stage A extra (HNHL, Week 4).
