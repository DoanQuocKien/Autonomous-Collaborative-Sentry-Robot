# HNHL W8: lunge detector, D1 parity và bàn giao Stage A

Trước buổi D3/D4 26/11, HNHL cần bàn giao model YOLOv8n-320 và detector timestamped cùng yêu cầu thu D3. PR này hoàn thành ba prerequisite phần HNHL; buổi ghi dữ liệu và các phần KR/DQK tiếp tục theo #139.

Phần laptop Stage A bổ sung kiểm tra thực tế trên 200 D1 frames và công cụ để chấm engine sau khi DQK build. PyTorch/ONNX 320 có cosine tối thiểu 0,99999999999989, 919/919 bbox khớp IoU ≥0,9, count bằng nhau mọi frame. Laptop 640 cũng đã chạy trên cùng ảnh. Distance chưa đủ bằng chứng: ONNX 320 chỉ có estimate rời rạc cho 3/9 ID với median error khoảng 41,67%, laptop 640 không có estimate hợp lệ; delta với laptop và distance gate trả `null`.

- Xuất ONNX FP32 opset 11, fixed `[1,3,320,320]` → `[1,84,2100]`, không embedded NMS. Đóng gói model/JSON/README trong `team_data/HNHL_yolov8n_320_op11_2026-11-25.zip`, 11 MB, có hash/readback và ORT/PyTorch parity thật. Chưa build engine Nano hoặc claim G2.
- Sửa exporter để dùng output directory mới, không thay sibling ONNX cũ, kiểm tra graph/ORT và trả exit code khác 0 nếu export lỗi.
- `sentry.perception.pose`: `LungeDetector` dùng strict `dA/A > 0,40` trong 100 ms capture time, reset ở gap/epoch/ID/resize/missing; COCO ankle cue tùy chọn mặc định tắt, cùng `YOLOPoseEstimator`.
- `tools.detect_lunges` tạo raw pose/strike JSONL private từ `tools.record`, giữ `t_cap` cho detector và `t_local` cho onset labels; missing/ambiguous vẫn có dòng, không có motor transport. API `(t,sample)->bool` dùng được với plugin contract của harness KR #142, không cần merge code KR vào PR này.
- Bàn giao D3 cho DQK/KR: timestamp/calibration theo session, clip hai người ≥60 s, gallery/query tách nhau, reviewed identity/visibility/target events; ba người là pilot cho gate re-ID ≥5 identities.
- `tools.stage_a_parity`: prepare/compare có fingerprints của model/input/code/camera/pose; raw cosine, class-aware box matching/NMS và ID-first tape-forward errors với coverage/missing IDs. Không tạo PASS từ rỗng hoặc thiếu IDs. Gói 200 inputs và raw outputs giữ private trong `data/`; PR chỉ có code, metadata/hash và báo cáo tổng hợp.
- `jetson.stage_a_parity_run`: Python 3.6, fixed-shape raw inference; xuất engine/ONNX/input/output hashes và TensorRT version. Test doubles được đánh dấu riêng và comparator từ chối dùng làm TensorRT evidence. Chưa chạy engine mới, chưa xác minh ground/repulsion port của KR hoặc robot G2.

Validation sau bổ sung Stage A: **1045 passed, 3 skipped, 4 GPU deselected**, 70,29 s; gồm 20 test mới cho decoder/NMS, distance missing-ID policy, Nano runner, provenance và comparator end-to-end tổng hợp. AST Nano runner tương thích Python 3.6. CUDA pose runtime smoke và ONNX Runtime export parity đã chạy thật. Max abs diff export ≤0,000458, cosine >0,99999999999995 trên ba tensor synthetic. Smoke pose chưa có person detections, không thay D4 recall/false-trigger/latency-to-command. Chưa có hardware trial hoặc motor command.

[Báo cáo tuần 8](week-08.md), [hướng dẫn/nhận model và D3](W8-ISSUE-139-USAGE.md), [ONNX metadata](week-08/onnx_delivery.json).

[Stage A protocol và lệnh Nano/laptop](W8-STAGE-A-PARITY.md), [D1 comparison](week-08/stage_a_onnx_d1_release.json), [regression sau bổ sung](week-08/tests_stage_a_release.txt).

Refs #139 (không đóng issue chung). Reviewers DQK và KR.
