# HNHL — Tuần 4: re-ID, D5 corrected-label training và export

Kiểm chứng **2026-10-28**, Asia/Bangkok. Nhánh `HuynhNguyenHoaiLoc/w04-reid-obstacles`, base **`39b4e4c`**. Triển khai và kiểm thử local đã có; **chưa hoàn tất nghiệm thu T1/T2** do thiếu dữ liệu độc lập và Wire chưa đạt. Nội dung PR: [PR-W4-HNHL.md](PR-W4-HNHL.md), hướng dẫn: [W4-USAGE.md](W4-USAGE.md).

## Đồng bộ PR DQK trước khi triển khai

Theo yêu cầu HNHL, đã review và merge [#71](https://github.com/DoanQuocKien/Autonomous-Collaborative-Sentry-Robot/pull/71), [#72](https://github.com/DoanQuocKien/Autonomous-Collaborative-Sentry-Robot/pull/72), [#73](https://github.com/DoanQuocKien/Autonomous-Collaborative-Sentry-Robot/pull/73). Bổ sung sửa lỗi vào #73 trước merge: bounded MJPEG buffer, stale-frame rejection, read1 để không chờ đủ 4096 bytes, reconnect và worker join; kiểm thử fragment, oversized frame và lifecycle.

Checkout kết hợp các PR đạt 450 CPU tests (3 skip do data/weights trong checkout riêng), ESP/tile + MJPEG subset 22 passed và Jetson AST Python 3.6. Chưa build/flash firmware hoặc thử lại board/Nano; số đo hardware của DQK vẫn là bằng chứng của tác giả. [Merge/review metadata](week-04/dqk_pr_reviews.json).

## 1. Re-ID laptop implementation

- `sentry/perception/reid.py`: `PersonReID(frame_bgr,t) -> ReIDResult`; nhận raw live/replay frame, YOLO person class 0, clip/copy person crops, OSNet embedding 512D chuẩn hóa, giữ timestamp/model hash. Bbox invalid/nhỏ giữ rejection, không tạo vector giả.
- Hai weights **re-ID-trained**: OSNet-AIN x1.0 domain-generalised và OSNet x0.25 Market1501; `pretrained=False`, đọc local checkpoint, kiểm tra đủ backbone và shape. Bỏ classifier theo tập train. AIN checkpoint có NumPy metric scalar: loader dùng `weights_only=True` với allowlist scalar hạn chế, không chuyển sang unrestricted pickle.
- Preprocess 256×128 RGB, mean/std ImageNet trong `[reid]`. Max cosine trên các gallery references; thiếu gallery hoặc hòa giữa danh tính thì abstain. Không so embedding giữa hai model/hash khác nhau.
- `tools/evaluate_reid.py`: manifest có session, entry, camera, gallery/query và calibration/test. Chặn ảnh trùng byte, entry trùng qua roles/partitions, session calibration/test trùng. Chọn threshold và model trên calibration, chỉ đo test tại threshold cố định. Xuất rank-1, CMC theo identity, ROC/query-level max impostor, counts và gates; không xuất ảnh/vector/identity trong report.

Tham khảo weights/protocol: [Torchreid model zoo](https://kaiyangzhou.github.io/deep-person-reid/MODEL_ZOO), [source OSNet](https://github.com/KaiyangZhou/deep-person-reid/blob/master/torchreid/models/osnet.py). ImageNet pretraining khác weights được train cho re-ID.

Smoke **synthetic runtime**, không phải D2 accuracy: hai model chạy CUDA FP32, output 512D, norm=1, repeat max difference=0 trên cùng crop. p95 một crop: AIN **11,575 ms**, x0.25 **14,082 ms** trên RTX5060; 3 warmup/20 iterations. Không dùng phép đo ngắn này để chọn model hoặc suy ra FPS cả pipeline. Pipeline YOLO → OSNet cũng khởi tạo/chạy trên frame xám; không có person candidate trên frame này. [Smoke JSON](week-04/reid_smoke.json).

HNHL xác nhận chưa có D2/D3. Vì vậy **chưa có rank-1/ROC thật, chưa chọn được model thắng**, chưa có comparison FP16/FP32 hoặc re-ID handoff trên Nano. Default AIN và cosine 0,7 chỉ là provisional config, không phải threshold đã hiệu chuẩn. Gate rank-1 ≥85% với ≥5 gallery identities còn chờ dữ liệu; nếu chỉ có ba thành viên thì phải báo giới hạn hoặc thống nhất lại protocol, không tự đổi ngưỡng.

## 2. D5 training lại sau review #63/#66

DQK đã bổ sung 138 bbox chân người ở 137 frame nền. Đã export mới `data/D5_yolo_w04` từ annotations hiện tại, giữ bản cũ: **307 train / 90 dev-val**, session **1024** duy nhất, không trùng exact image bytes giữa splits. Đây vẫn là **same-session internal development**, chưa independent T1. Annotation nền là proposals đã được DQK sample-review, chưa khẳng định exhaustive ground truth.

Chạy lại cả 320/416/640 từ `data/models/yolov8n.pt`, 30 epochs, batch 8, workers 0, seed 42, AMP mặc định; RTX5060 Laptop. Kết quả dưới đây là lần **revalidation** các checkpoint best với nhãn sửa, không ghi đè bảng lịch sử tuần 3:

| Size | Precision (all) | Recall (all) | mAP50 | mAP50–95 | Leg recall | Wire recall |
| --: | --: | --: | --: | --: | --: | --: |
| 320 | 0,901 | 0,690 | 0,759 | 0,626 | 0,920 | **0,000** |
| 416 | 0,671 | 0,746 | 0,753 | 0,622 | 0,920 | **0,000** |
| 640 | 0,715 | 0,778 | **0,810** | **0,656** | 0,960 | **0,000** |

Metric khác nhẹ so với validation cuối training do batch/validation runtime; [training records](week-04/d5_train_640.json) và [revalidation từng class](week-04/d5_corrected_validation.json) được giữ riêng. Wire AP50 vẫn thấp (320/416/640 lần lượt 0,105/0,032/0,058); recall 0 tại operating point này **không** có nghĩa model tuyệt đối không sinh wire proposals ở mọi confidence. Chưa đạt yêu cầu Wire ≥80%; không ghép heuristic LSD vốn NO-GO vào detector để tạo số PASS.

## 3. Đóng gói candidate và ONNX

Chọn **640 cho development candidate** theo mAP50–95 cao nhất trên dev-val, không chọn cho robot. `tools.freeze_d5` khóa checkpoint, thứ tự tám class `[leg, footwear, backpack, bag, wire, chair, table, plant]`, input size, SHA256 image/label/split/checkpoint và manifest. Cấm ghi đè thư mục release. Model/ONNX ở `data/releases/d5_w04_640`, ngoài Git; chỉ metadata/metrics được commit.

ONNX batch1 fixed-shape FP32, opset 11 theo recipe TensorRT7. Smoke hai input tổng hợp cosine ≥0,999. Sau đó `tools.check_d5_onnx` so **90 ảnh dev-val thật** qua PyTorch CUDA FP32 và ONNX Runtime CPU với cùng blob/Jetson decoder: cosine min **0,9999999916**, số bbox bằng nhau **90/90 frames**, **294 reference boxes**, fraction ghép IoU≥0,9 đạt **100% mỗi frame**. Raw max absolute difference **1,777** (trên output tổng hợp tọa độ/scores); không khẳng định tensor giống tuyệt đối. [Parity JSON](week-04/d5_onnx_real_parity.json).

Đây là **conversion parity trên laptop**, không phải accuracy hoặc TensorRT parity. Engines phải build trên Nano. Manifest giữ `deployment_ready=false`, `independent_t1_passed=false`, `trt_parity_passed=false`; không đổi model mặc định trong live obstacle layer. Custom D5 class IDs không được diễn giải như COCO class IDs.

`tools.evaluate_d5_holdout` đã có để audit session/ảnh độc lập, đo class metrics theo glossy/matte và wire alarms trên empty controls. Thiếu distance tape/contact/HIL không tự tạo T1 PASS. HNHL xác nhận chưa có session D5 mới: **chưa chạy T1 độc lập, chưa có distance parity robot/laptop trên D1**. Wire masks 12 ảnh tuần 3 vẫn là annotation pilot; không được mô tả là model segmentation đã train/đạt nghiệm thu.

## Kiểm thử và bằng chứng

Python3.12.15, torch2.9.1+cu128, Ultralytics8.4.172, torchreid0.2.5, RTX5060 Laptop; không thay baseline RTX4050. [Environment](week-04/environment.json).

- [CPU regression](week-04/pytest_cpu.log): **476 passed**, 2 skipped (D1 checkerboard và entrance replay thiếu), 3 GPU deselected, **18,94 s**, bao gồm CMC và reject-all threshold tests.
- [GPU regression](week-04/pytest_gpu.log): **3 passed**, **9,22 s**. OSNet thật chạy CUDA/offline, cùng các GPU tests đã có.
- Tests mới bao gồm crop clipping, BGR→RGB/preprocess, malformed embeddings, tied identities, max cosine, batched person output/count, split leakage, frozen threshold, D5 independent-session/hash guard và one-to-one class-aware parity.
- Không có motor commands, dữ liệu sinh trắc, crops, ảnh riêng, weights hoặc engines trong PR.

## Trạng thái nghiệm thu và phần chờ

| Việc tuần 4 | Trạng thái |
| :-- | :-- |
| Person → OSNet API và unit/GPU tests | Có implementation và runtime evidence |
| D2/D3 rank-1, ROC, chọn AIN/x0.25 | **Chờ D2/D3**, không có kết quả thật |
| Retraining D5 với nhãn sửa | Đã chạy 3 size, internal dev-val |
| D5 held-out-session T1 | **Chờ capture độc lập**, Wire chưa đạt |
| Candidate/class freeze + ONNX export | Có artifact local/hash và parity laptop |
| Nano engine/FP16, distance parity D1, exploration T2 | **Chờ DQK/Nano và dữ liệu**, chưa PASS |
| Mid-term outline/owners | Kế hoạch nhóm đã có; HNHL chuẩn bị F10/F11/F13/F14 theo dữ liệu tương ứng, nhóm chốt trước 02/11 |

Ưu tiên tiếp theo là D2/D3 có identity/entry/session labels, D5 glossy+matte khác session và nhãn wire segmentation đủ để huấn luyện; phối hợp DQK kiểm chứng model/engine và robot. Không hạ target hoặc dùng cùng-session scores thay nghiệm thu độc lập. Không tự ghi timesheet cho thời gian người dùng chưa xác nhận.
