# HNHL — xử lý issue #43, ngày 2026-10-17

Issue: [glossy-floor chairs / small and low objects](https://github.com/DoanQuocKien/Autonomous-Collaborative-Sentry-Robot/issues/43).
Base `b7d19be`, branch `HuynhNguyenHoaiLoc/w02-issue43-obstacles`. Đã triển khai và kiểm chứng các phương án bổ sung; **chưa đủ bằng chứng để đóng toàn bộ issue**. HNHL đã yêu cầu commit/push nhánh này sau khi xem kết quả local. Không đăng comment hoặc đóng issue GitHub.

## Đã thay đổi

- Backend tùy chọn SegFormer-B0/ADE20K nhận diện floor/rug, cung cấp non-floor proposals ngoài các class COCO. Không dùng ngưỡng màu toàn cảnh và không tự chuyển segmentation thành FREE trong map.
- Contact cho sàn glossy dùng semantic object seed và mép chuyển tiếp ảnh sang sàn có hỗ trợ nhiều cột, giúp xử lý chân ghế thưa mà median cả bbox làm mất. Thiếu evidence giữ unresolved; bbox cắt mép vẫn bị từ chối. Reflection symmetry cũ vẫn là một nguồn contact.
- Backend YOLO-World-small tùy chọn: vocabulary vật nhỏ, full frame + floor crops phóng lớn, NMS giữa các crop và giữa nguồn YOLO/World. Box cắt biên crop nhân tạo bị bỏ để tránh lấy biên crop làm chân vật.
- `Detection.source`, `semantic_label` ADE và `label` phân biệt rõ nguồn với COCO class ID. Single-image/replay CLI xuất các field này.
- Downloader pin revision/SHA256; model và vocabulary chuẩn bị trước. Inference chỉ đọc local, không tải model/text encoder. Mặc định hai backend mới **tắt**, bật explicit cho thử nghiệm offline vì chưa đạt latency/accuracy triển khai robot.

Tham khảo kỹ thuật: [SegFormer model card](https://huggingface.co/nvidia/segformer-b0-finetuned-ade-512-512), [Transformers SegFormer](https://huggingface.co/docs/transformers/model_doc/segformer), [Ultralytics YOLO-World và offline vocabulary](https://docs.ultralytics.com/models/yolo-world/). Weights SegFormer theo [license nguồn NVIDIA](https://github.com/NVlabs/SegFormer/blob/master/LICENSE); YOLO-World/Ultralytics theo license của upstream. Không commit weights.

## Dữ liệu và protocol

Đã đọc issue và comment mới: glossy tile và đơn vị tape `chairs_c` đã được operator xác nhận. Các ảnh 15/10 dùng H=0,1089 m, pitch=−12,2°, roll=0 từ JSON session; không dùng pose 12/10. Pose có độ bất định khoảng ±1° và có thể drift, chưa có marker cuối session để kiểm tra.

`chairs_a`/`chairs_b` dùng phát triển; `chairs_c` chỉ dùng đánh giá sau khi chọn threshold. Có 86 ảnh public được lấy mỗi frame thứ 3 trong clip gốc: 30/28/28 ảnh. Chín ID là chín vị trí đặt ghế, không phải chín mẫu camera độc lập. Annotation [chair_boxes.json](week-02/issue-43/chair_boxes.json) được gán thủ công theo ảnh rectified, cố định cho từng clip robot đứng yên.

ZIP 15/10 đã giải nén ở `data/dqk-obstacles-2026-10-15`; raw/private frames và annotation riêng `data/issue43/mixed_boxes.json` giữ trong Git ignore. Dùng toàn bộ 259 frames set2/set3/set4 (86/90/83), 15 ID theo CSV DQK. Box riêng được gán để chấm thử, **cần DQK review**; chưa phải ground-truth detection benchmark đã nghiệm thu.

Ghép prediction/annotation **one-to-one bằng image IoU ≥0,30**, không ghép bằng tape/forward gần nhất. Class-agnostic obstacle matching, chưa chấm độ đúng tên class. Có detection/estimate ít nhất một frame được báo riêng với ổn định ≥50% số frame; không giấu missed IDs. Sai số lấy median theo ID rồi median/p90 giữa các ID có estimate; số ID và tỷ lệ frame thiếu vẫn phải đọc cùng metric.

Tape manifest gọi field `tape_distance_m` nhưng README xác nhận đây là **forward Z từ điểm dưới lens**. Benchmark đọc đúng semantics này; generic evaluator W2 vẫn yêu cầu `tape_forward_m`, không đổi thành planar range.

## Kết quả ghế

| Phương án | Có distance ít nhất một frame | Có distance ≥50% frames | Coverage distance theo frame |
| :-- | --: | --: | --: |
| Baseline reflection | 0/9 | 0/9 | 0% |
| Semantic + contact edge | **8/9** | **8/9** | **86,82%** |

Baseline và bản mới đều detect 9/9 ID. ID 21 gần bên phải bị cắt biên, không tạo ground distance. Trên 8 ID có estimate, median/p90 relative error là **5,34% / 20,91%**; tổng thể chưa qua p90 ≤20%.

Riêng **chairs_c held out**: cả 3 ID có distance; median/p90 theo ID **5,37% / 17,11%**. ID 29 có estimate 24/28 frames; 4 frames vẫn unresolved/out of range. Đây là kết quả subset ba vị trí, không phải T1 PASS đầy đủ ≥20 IDs và đủ floor sets.

Bằng chứng: [baseline](week-02/issue-43/chairs_baseline.json), [semantic](week-02/issue-43/chairs_semantic.json).

## Kết quả 15 vật set2–set4

| Phương án | Detect ≥1 frame | Detect ≥50% frames | Distance ≥1 frame | Distance ≥50% frames | Detection frame coverage |
| :-- | --: | --: | --: | --: | --: |
| YOLOv8n, đủ 80 COCO classes | 7/15 | 2/15 | 2/15 | 1/15 | 16,14% |
| Furniture YOLO + semantic floor | 6/15 | 4/15 | 5/15 | 2/15 | 24,63% |
| Furniture + semantic + tiled World | **12/15** | **10/15** | **10/15** | **6/15** | **60,31%** |

Distance frame coverage của hybrid là **35,60%**. Trên 10 ID có estimate, median/p90 error **11,27% / 27,80%**, chưa đạt giới hạn 10%/20%. Không so trực tiếp sai số này với subset 2 ID dễ của all80 để kết luận accuracy toàn bộ tốt hơn.

**Chưa detect:** ID 10 laptop charger, ID 13 laptop stand, ID 15 phone. ID 9 chair và ID 17 keychains được detect nhưng chưa có distance; cup, sleeve, book và laptop có estimate chưa ổn định. Đây là các mục còn phải cải thiện, không thể đánh dấu issue hoàn tất.

Protocol toàn clip/rectified matching khác phép xem một frame trong issue, nên all80 có một số detections mà quan sát một frame ban đầu không thấy. Không suy ra recall/precision tổng quát: các ảnh còn có ghế nền/người chưa được gán nhãn đầy đủ; unmatched boxes chưa được phân loại true/false positive.

Bằng chứng: [all80](week-02/issue-43/mixed_all80.json), [semantic](week-02/issue-43/mixed_semantic.json), [hybrid](week-02/issue-43/mixed_hybrid.json). JSON chỉ chứa metrics/hashes, không chứa ảnh riêng hoặc bbox riêng.

## Runtime và kiểm thử

Máy HNHL RTX 5060 Laptop, torch 2.9.1+cu128, FP32, CUDA; không thay baseline RTX 4050. Có 3 warmup mỗi clip, loại image read khỏi timer. Timer gồm undistort, các model được bật, contact/postprocessing; chưa gồm transport/map/vantage/motor.

| Chế độ | FPS ảnh inference | p95 (ms) | Torch peak allocated / reserved (MiB) |
| :-- | --: | --: | --: |
| Ghế semantic | 11,45 | 113,05 | 423,83 / 602 |
| Vật nhỏ hybrid | 7,80 | 159,89 | 472,71 / 650 |

Chưa đạt 20 FPS. Bộ nhớ là PyTorch allocator, không phải tổng VRAM hoặc pipeline nhiều model. Timing có thể chịu background load, chưa là benchmark nguồn điện/clock chuẩn hóa.

- [CPU/regression log](week-02/issue-43/tests_cpu.txt): **360 passed**, 2 skipped, 2 GPU tests deselected; 15,48 s.
- [GPU log](week-02/issue-43/tests_gpu.txt): **2 passed**, 5,24 s; real SegFormer + YOLO-World CUDA FP32, network bị chặn trong test inference.
- [Môi trường](week-02/issue-43/check_env.txt): **ALL GOOD**, ONNX Relu thực thi đúng trên CUDA.
- `pip check` còn báo requirement tên `onnxruntime` của InsightFace: môi trường dùng `onnxruntime-gpu` theo Setup, không cài thêm bản CPU; runtime đã kiểm chứng riêng.

## Chạy lại

```powershell
$env:YOLO_CONFIG_DIR = Join-Path (Get-Location) 'data/ultralytics'
.venv/Scripts/python.exe -m pip install -r requirements-floor.txt
.venv/Scripts/python.exe -m pip install -r requirements-world.txt
.venv/Scripts/python.exe -m tools.fetch_floor_model --world
.venv/Scripts/python.exe -m tools.obstacle_image --image data/dqk-obstacles-2026-10-15/set4/000030.jpg --camera-pose assets/d1/obstacles_2026-10-15/camera_pose_classroom_1015.json --floor-type glossy --semantic-floor --open-vocabulary --out data/issue43/example
.venv/Scripts/python.exe -m tools.bench_obstacles --annotations reports/HuynhNguyenHoaiLoc/week-02/issue-43/chair_boxes.json --mode semantic --out data/issue43/chairs.json
.venv/Scripts/python.exe -m tools.bench_obstacles --annotations data/issue43/mixed_boxes.json --private-root data/dqk-obstacles-2026-10-15 --mode hybrid --out data/issue43/mixed.json
```

Replay có cùng flags `--semantic-floor --open-vocabulary`; vẫn bắt buộc pose robot từng frame để map. Không dùng pose giả hoặc semantic floor làm bằng chứng FREE tự động.

## Phần còn cần để đóng issue

1. DQK review box annotations và contact visibility; thêm nhãn/background đầy đủ để đo false positives. Đặc biệt charger/stand/phone cần dữ liệu gán nhãn phù hợp để thích nghi/fine-tune, không chỉ nới confidence.
2. Có matte control và ảnh rugged-floor thật cho generalization. Branch w02-log hiện có số đo/CSV rugged nhưng không có ảnh trong thư mục đó để chấm semantic floor.
3. Kiểm chứng pitch bằng marker đầu/cuối session và đánh giá sai số pose; không chỉnh pitch bằng tape của chính vật đang chấm.
4. Tối ưu và đo trên RTX 4050/full pipeline trước khi bật mặc định; sau đó T1 map và T2 robot DQK. Phiên này không gửi motor commands.

Nội dung PR bổ sung: [PR-I43-HNHL.md](PR-I43-HNHL.md). Đề xuất review dưới dạng **Refs #43**, giữ issue mở cho các tiêu chí còn thiếu.
