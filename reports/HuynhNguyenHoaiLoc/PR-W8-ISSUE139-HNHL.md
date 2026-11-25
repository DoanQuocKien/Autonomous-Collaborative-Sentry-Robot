# HNHL chuẩn bị ONNX lunge detector và D3 cho issue 139

Trước buổi D3/D4 26/11, HNHL cần bàn giao model YOLOv8n-320 và detector timestamped cùng yêu cầu thu D3. PR này hoàn thành ba prerequisite phần HNHL; buổi ghi dữ liệu và các phần KR/DQK tiếp tục theo #139.

- Xuất ONNX FP32 opset 11, fixed `[1,3,320,320]` → `[1,84,2100]`, không embedded NMS. Đóng gói model/JSON/README trong `team_data/HNHL_yolov8n_320_op11_2026-11-25.zip`, 11 MB, có hash/readback và ORT/PyTorch parity thật. Chưa build engine Nano hoặc claim G2.
- Sửa exporter để dùng output directory mới, không thay sibling ONNX cũ, kiểm tra graph/ORT và trả exit code khác 0 nếu export lỗi.
- `sentry.perception.pose`: `LungeDetector` dùng strict `dA/A > 0,40` trong 100 ms capture time, reset ở gap/epoch/ID/resize/missing; COCO ankle cue tùy chọn mặc định tắt, cùng `YOLOPoseEstimator`.
- `tools.detect_lunges` tạo raw pose/strike JSONL private từ `tools.record`, giữ `t_cap` cho detector và `t_local` cho onset labels; missing/ambiguous vẫn có dòng, không có motor transport. API `(t,sample)->bool` dùng được với plugin contract của harness KR #142, không cần merge code KR vào PR này.
- Bàn giao D3 cho DQK/KR: timestamp/calibration theo session, clip hai người ≥60 s, gallery/query tách nhau, reviewed identity/visibility/target events; ba người là pilot cho gate re-ID ≥5 identities.

Validation: **1025 passed, 3 skipped, 4 GPU deselected**, 66,50 s. CUDA pose runtime smoke và ONNX Runtime export parity đã chạy thật. Max abs diff export ≤0,000458, cosine >0,99999999999995 trên ba tensor synthetic. Smoke pose chưa có person detections, không thay D4 recall/false-trigger/latency-to-command. Chưa có hardware trial hoặc motor command.

[Báo cáo tuần 8](week-08.md), [hướng dẫn/nhận model và D3](W8-ISSUE-139-USAGE.md), [CPU log](week-08/tests_cpu.txt), [ONNX metadata](week-08/onnx_delivery.json).

Refs #139 (không đóng issue chung). Reviewers DQK và KR.
