# HNHL tuần 8 chuẩn bị D3 và D4

Ngày **25/11/2026, Asia/Bangkok**, thực hiện ba prerequisite HNHL của [issue #139](https://github.com/DoanQuocKien/Autonomous-Collaborative-Sentry-Robot/issues/139) cho buổi lớp 26/11, 08:00–12:00. Base main `fbe9c53`, đã có evasion override #138. PR #134 của tuần 7 đã merge.

| Phần HNHL | Kết quả |
| :-- | :-- |
| YOLOv8n-320 ONNX opset 11 | Đã export cố định FP32, ONNX checker/ORT thật và ba PyTorch parity probes; archive sẵn để chia sẻ trong PR |
| Lunge detector và T0 | `perception/pose.py` có timestamp-window bbox cue, optional ankle cue, YOLO pose API; `tools.detect_lunges` xuất predictions offline với hai clock và giữ mọi frame |
| Đọc protocol, bàn giao D3 | Đã viết yêu cầu raw frames/timestamps, pose, gallery/query, identity/visibility và target events cho DQK/KR; phần checklist được đăng lại trong issue khi push |

Chi tiết nhận model và phối hợp: [W8-ISSUE-139-USAGE.md](W8-ISSUE-139-USAGE.md). [ONNX/hash](week-08/onnx_delivery.json), [runtime smoke pose](week-08/pose_runtime_smoke.json), [CPU regression](week-08/tests_cpu.txt).

Regression `.venv` Python 3.12 đạt **1025 passed, 3 skipped, 4 GPU deselected**, 66,50 s. Skip cần checkerboard, D1 classroom và ReportLab của môi trường pytest. Pose runtime thực chạy trên `cuda:0` với ảnh trống/ảnh D2 cũ, chưa có detection người trong hai ảnh smoke; phép chạy chỉ xác minh load/inference, không chứng minh D4 accuracy hoặc latency.

Ngưỡng default giữ `dA/A > 0,40` trong 100 ms từ `[thresholds]`; ankle threshold chưa hiệu chuẩn nên mặc định tắt. T0 phủ tăng diện tích/đúng biên ngưỡng, nhịp không đều, frame gap, duplicate/backward clock, epoch/target/resize, invalid/cut bbox, confidence và relative-hip ankle rise. Exporter dùng thư mục tạm, từ chối ghi đè output và trả failure exit code; test output/clock/private paths cho CLI offline.

Chưa có D4 hoặc D3 mới, nên recall ≥90%, false-trigger ≤1/5 phút, reaction frame-to-command ≤150 ms, re-ID và Stage A G2 chưa được nghiệm thu. ONNX package là stock COCO, không thay D5 model. TensorRT engine build và output parity/distance phía robot chờ DQK. Issue #139 là việc chung ba thành viên; hoàn thành prerequisite HNHL không đóng toàn bộ buổi ghi dữ liệu.
