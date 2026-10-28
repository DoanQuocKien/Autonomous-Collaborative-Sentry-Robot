# HNHL — Tuần 4: re-ID, D5 corrected-label training và export

Kiểm chứng bổ sung **2026-10-29**, Asia/Bangkok. Nhánh `HuynhNguyenHoaiLoc/w04-reid-obstacles`, PR [#74](https://github.com/DoanQuocKien/Autonomous-Collaborative-Sentry-Robot/pull/74). Đã merge `origin/main` **`6367935`** (PR #75–#87) vào nhánh, giữ kết quả 28/10 làm lịch sử. **Chưa hoàn tất nghiệm thu T1/T2**: D2 thật đã có nhưng chưa đủ body crops/protocol handoff; Wire chưa đạt. Nội dung PR: [PR-W4-HNHL.md](PR-W4-HNHL.md), hướng dẫn: [W4-USAGE.md](W4-USAGE.md).

## Cập nhật GitHub 29/10 và tích hợp KR

- PR #81/#82 cung cấp D2 cafe 28/10: giải nén AES ZIP bằng `tools.team_data` vào `data/D2/1028` (834 files). Không commit dữ liệu đã giải nén. [Metadata cập nhật](week-04/github_update.json).
- `OSNetAppearanceExtractor` của KR nay gọi chung `OSNetEncoder` của HNHL: cùng preprocessing, restricted checkpoint loader, kiểm tra backbone và model/hash. Không còn loader thứ hai có thể thất bại âm thầm trên checkpoint AIN với PyTorch mới.
- Phase 2 yêu cầu extractor tường minh. Thiếu model/crop thật báo lỗi trước khi enqueue hoặc đổi state; chỉ mô phỏng chọn `MockAppearanceExtractor` mới được tạo vector giả. Record giữ `appearance_model_id` và `appearance_simulated`. Tích hợp này chỉ tạo kết quả logic/queue; không gửi motor commands.
- Sửa import `Optional` còn thiếu trong `tools.replay_phase2` trên main mới, vốn làm pytest lỗi ngay khi collect.
- CLI replay tổng hợp yêu cầu `--simulated`, ghi `SIMULATION_PASS/FAIL` và `t1_accepted=false`; không còn JSON `PASS` không ghi rõ phạm vi. Evidence lịch sử của KR được giữ nguyên.
- PR #86 ghi nhận nhóm đã chốt outline/page budget/owners ngày 28/10. Không còn ghi việc này là đang chờ. Chưa tạo shared document hoặc tự ghi timesheet.

## D2 thật: pilot cùng session, chưa phải nghiệm thu

`tools.evaluate_d2_pilot` đọc toàn bộ **125 walker-face frames / 21 entries / 3 identities**. Số lượt theo người là 11/5/5, chưa đủ 10 lượt mỗi người. Giữ mọi frame, không lọc theo sharpness. Gallery cố định là entry đầu mỗi người; **18 entry còn lại** là query. Không chia frame của cùng entry qua gallery/query, không đặt tên session giả để vượt guard của evaluator độc lập.

YOLOv8n ghép bbox người với face annotation: **23/125 crops hợp lệ**, **99 frame không có person phù hợp**, **3 frame mơ hồ**. Các crop được chạy qua cả hai OSNet thật trên CUDA. Gallery đầu thiếu crop ở **2/3 người**, mỗi model thiếu **9 query entries**; do đó tool trả `scored=false`, **không có rank-1/CMC/ROC re-ID hợp lệ và không chọn model thắng**. Không thay crop toàn thân bằng crop mặt, không dời gallery sang entry thuận lợi hơn sau khi xem kết quả. Đây là nút thắt framing/detection của bộ hiện có; cần body boxes được review và gallery toàn thân đủ người trước khi đo handoff.

Face verification dùng embeddings `buffalo_s` do DQK cung cấp (không trích lại tại máy HNHL), leave-one-member-out, enrollment chỉ từ entry đầu của hai người được whitelist. Có **194 genuine / 125 impostor queries**; ở threshold config **0,45**, **TAR 82,99%, FAR 46,40%**. Không đạt; giữ nguyên threshold. Nhãn walker là largest-face tự động, entry dựa trên gap, có bystanders và motion blur; cần review nhãn trước khi kết luận accuracy. Các query liên tiếp tương quan, không phải thử độc lập ở mức quần thể.

[D2 pilot JSON](week-04/d2_pilot.json), [F13 ROC pilot](week-04/F13_d2_face_roc_pilot.png), script `tools.plot_d2_pilot`. ROC chỉ mô tả bộ này; không calibration trên cùng dữ liệu để tạo PASS. D2 này chỉ có một ESP32, một session, ba người; không thay D3/JetBot hoặc gate re-ID ≥5 gallery identities. Tool `evaluate_reid` với calibration/test sessions độc lập vẫn giữ nguyên guard.

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

D2 đã có từ GitHub ngày 29/10 và đã chạy pilot nêu trên; D3 chưa có. **Chưa có rank-1/ROC re-ID hợp lệ, chưa chọn được model thắng**, chưa có comparison FP16/FP32 trên person queries hoặc re-ID handoff trên Nano. Default AIN và cosine 0,7 chỉ là provisional config, không phải threshold đã hiệu chuẩn. Gate rank-1 ≥85% với ≥5 gallery identities còn chờ dữ liệu/protocol; không tự đổi ngưỡng.

## 2. D5 training lại sau review #63/#66

DQK đã bổ sung 138 bbox chân người ở 137 frame nền. Đã export mới `data/D5_yolo_w04` từ annotations hiện tại, giữ bản cũ: **307 train / 90 dev-val**, session **1024** duy nhất, không trùng exact image bytes giữa splits. Đây vẫn là **same-session internal development**, chưa independent T1. Annotation nền là proposals đã được DQK sample-review, chưa khẳng định exhaustive ground truth.

**Điều chỉnh theo quyết định DQK 28/10:** tuần này không có batch D5 matte mới; cho phép dùng nhóm khoảng cách/vị trí trong cùng buổi và công bố giới hạn. Split hiện có đã giữ nguyên nhóm: backpack/bag/shoe/wire_black/wire_white hold out **1,0 m**; chair/leg/plant/table hold out **1,2 m**; empty chỉ có một nhóm nên giữ **10 frame cuối liên tiếp**. [Split audit](week-04/d5_group_split.json) ghi counts/rule/hash. Không cần train lại cùng nhãn/split không đổi. Dev-val đã dùng chọn checkpoint/size, vì vậy đây không phải test set chưa từng xem và không đo khả năng tổng quát sang matte hoặc session khác.

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

**Sau tích hợp main, 29/10:** [CPU log](week-04/pytest_updated_cpu.log) **546 passed**, 2 D1 data skips, 3 GPU deselected, **26,72 s**; [GPU log](week-04/pytest_updated_gpu.log) **3 passed**, 548 deselected, **9,31 s**. GPU test khởi tạo adapter thật cho cả hai weights, chặn network và xác minh vector/queue/model provenance. So cùng batch shape bằng allclose; giữa batch 1/2 dùng cosine ≥0,999 do CUDA có thể chọn kernel khác. Tests mới bao gồm không enqueue khi thiếu extractor/crop, truyền lỗi checkpoint, face-person ambiguity, giữ entry split và tính missing queries là fail. CLI help, explicit simulation CLI, AST Python 3.6 common/jetson và `git diff --check` đạt. Cài bổ sung `pyzipper` từ requirements để đọc archive D2; [environment update](week-04/environment_updated.json).

**Bằng chứng lịch sử 28/10 trước tích hợp:**

- [CPU regression](week-04/pytest_cpu.log): **476 passed**, 2 skipped (D1 checkerboard và entrance replay thiếu), 3 GPU deselected, **18,94 s**, bao gồm CMC và reject-all threshold tests.
- [GPU regression](week-04/pytest_gpu.log): **3 passed**, **9,22 s**. OSNet thật chạy CUDA/offline, cùng các GPU tests đã có.
- Tests mới bao gồm crop clipping, BGR→RGB/preprocess, malformed embeddings, tied identities, max cosine, batched person output/count, split leakage, frozen threshold, D5 independent-session/hash guard và one-to-one class-aware parity.
- Không có motor commands, dữ liệu sinh trắc, crops, ảnh riêng, weights hoặc engines trong PR.

## Trạng thái nghiệm thu và phần chờ

| Việc tuần 4 | Trạng thái |
| :-- | :-- |
| Person → OSNet API và unit/GPU tests | Có implementation và runtime evidence |
| D2/D3 rank-1, ROC, chọn AIN/x0.25 | Đã chạy D2 pilot thật; thiếu gallery body crops, D3/cross-camera và đủ identities; chưa chọn model |
| Retraining D5 với nhãn sửa | Đã chạy 3 size, internal dev-val |
| D5 W4 fallback theo nhóm trong session | Đã có distance-group split theo quyết định mới; Wire chưa đạt; chưa independent-session T1 |
| Candidate/class freeze + ONNX export | Có artifact local/hash và parity laptop |
| Nano engine/FP16, distance parity D1, exploration T2 | **Chờ DQK/Nano và dữ liệu**, chưa PASS |
| Mid-term outline/owners | Đã chốt 28/10 theo PR #86; F13 có pilot thật với giới hạn, F14 chờ re-ID đủ gallery/protocol |

PR #79 đã cung cấp TensorRT parity của **stock edge models**: cosine ≥0,999, matched boxes đạt ngưỡng nhưng YOLOv8n chỉ cùng count **205/208 frames**. Theo tiêu chí nguyên văn, phần same-count chưa đạt; không tự cấp ngoại lệ cho nhóm. Đây không phải parity model D5 custom/OSNet-AIN và không phải ground-distance parity D1 glossy. Ghi riêng bằng chứng DQK với kết quả ONNX D5 của HNHL.

Ưu tiên tiếp theo là review walker/identity labels và body crops của D2, D3/cross-camera, dữ liệu wire đủ để huấn luyện; D5 matte/session khác để đánh giá tổng quát khi có thể. Không hạ target, không dùng cùng-session scores thay nghiệm thu độc lập, không tự ghi timesheet.
