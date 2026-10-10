# W1 HNHL: triển khai networking, telemetry và GPU baseline

Base: `main`

Compare: `HuynhNguyenHoaiLoc/w01-network-telemetry`

Reviewer đề nghị: `DoanQuocKien`

## Mục tiêu

Hoàn thành phần triển khai trên laptop của HNHL trong tuần 1: nhận video mới
nhất từ JetBot, gửi lệnh UDP có giới hạn tần suất, đồng bộ clock, đo latency
và lập GPU baseline có thể tái lập. Bổ sung kiểm thử và bằng chứng để DQK
review, tích hợp với JetBot và giao diện record/replay của KR.

## Thay đổi

- `ZMQReceiver` nhận multipart `[header_json, jpeg_bytes]` trong luồng sở hữu
  socket, giải mã JPEG và cung cấp một slot frame mới nhất. Queue/drain có
  giới hạn; timeout, lỗi worker và shutdown có giao diện rõ ràng. Dùng
  `VideoFrame` chung cho live/replay. Không dùng `CONFLATE` với multipart.
- `UDPSender` gửi nonblocking `seq/v/w`, giới hạn mặc định 30 Hz, không tích
  lũy backlog hoặc lặp lại lệnh chuyển động bằng heartbeat. `stop()` và context
  exit gửi zero ngay, bỏ qua rate limit; watchdog phía robot vẫn cần thiết.
- Cristian clock sync lấy 20 echo hợp lệ, chọn minimum RTT và dùng
  `offset = t_jetson - (t0 + t1)/2`. Telemetry hiệu chỉnh capture timestamp,
  ghi CSV raw timestamps, xuất p50/p95, FPS và các cờ clock/sequence.
- `tools.log_latency` đo stream mà không gửi lệnh motor; `tools.check_net`
  chạy publisher và clock echo tổng hợp trên localhost với offset 100 giây.
- `tools.gpu_baseline` đo YOLOv8n/s ở 640, batch 1, FP32; kiểm tra torch CUDA,
  ONNX inference, InsightFace và ghi phiên bản, hash weights, GPU runtime,
  FPS/latency cùng peak memory của PyTorch allocator.
- Sửa lỗi decoder khi JSON chứa số vượt finite float range; chuẩn hóa thành
  `ValueError` để caller loại packet. Sửa truyền lỗi và cleanup khi tạo ZMQ
  context/socket thất bại. Thêm kiểm thử hồi quy cho các trường hợp này.
- Loại offset NaN/Inf trước khi khởi động smoke test; cho publisher FPS thấp
  dừng kịp thời. `check_env.py` xác minh kết quả Relu và CUDA provider thực
  thi. Thống nhất tài liệu với Python 3.12, `.venv` và GPU thực tế của HNHL.
- Tích hợp `main` tại `7d34e46`, giữ e-stop, ESP32 relay, cấu hình HOLD/search
  và simulator của DQK/KR. Giải quyết ba xung đột ở ignore, dependencies và plan.
- Nối recorder JetBot với `ZMQReceiver` thay cho `CONFLATE` multipart; lưu JPEG
  gốc cùng timestamp nguồn/local. Filename độc lập với seq để không ghi đè
  sau restart. `ReplayStream.read()` trả `VideoFrame`; iterator tuple cũ vẫn
  hoạt động. Thêm kiểm thử round-trip JetBot và giữ kiểm thử ESP32 của main.

## Kiểm chứng

Chạy lại sau tích hợp main ngày 2026-10-10 bằng `.venv\Scripts\python.exe`:

```powershell
.venv\Scripts\python.exe -m pytest -m "not gpu and not hil" --basetemp=data/pytest-w1-postpush-final -p no:cacheprovider -q
.venv\Scripts\python.exe tools/check_env.py
.venv\Scripts\python.exe -m tools.check_net --fps 30 --seconds 5 --out reports/HuynhNguyenHoaiLoc/week-01/integration_loopback_latency.csv
```

| Kiểm tra | Kết quả |
| :-- | :-- |
| T0 + transport localhost, JetBot/ESP32 record/replay | **121 passed**, 12.44 s |
| Môi trường CUDA | **ALL GOOD**, Relu chạy thực tế trên CUDA và trả đúng output |
| Synthetic localhost telemetry | **144 frames**, run **28.749 FPS**, decoded p95 **3.189 ms**, pass |
| Cú pháp `common/`, `jetson/` | Tương thích Python 3.6 qua AST check |

Log và CSV/JSON mới nằm tại `reports/HuynhNguyenHoaiLoc/week-01/integration_*`.
Môi trường bổ sung `paramiko`/`pyserial` theo requirements mới; phiên bản của
80 distributions được lưu tại `integration_environment_versions.json`.
Báo cáo đầy đủ: `reports/HuynhNguyenHoaiLoc/week-01.md`.

GPU baseline ngày 2026-10-04 được giữ lại, chưa đo lại trong lần review này:

| Model | FPS | p95 (ms) | Peak allocated / reserved (MiB) |
| :-- | --: | --: | :-- |
| YOLOv8n | 49.179 | 27.025 | 33.545 / 58 |
| YOLOv8s | 26.060 | 40.740 | 78.616 / 94 |

Điều kiện: RTX 5060 Laptop 8 GB, enforced power limit ghi nhận 20 W, nguồn
AC/battery chưa xác nhận; ảnh BGR tổng hợp 640x640, batch 1, FP32, 10 warmup
và 100 lần đo. FPS bao gồm preprocessing/postprocessing của `predict()`.
Memory là PyTorch allocator, chưa phải tổng VRAM của toàn pipeline.

## Phần tích hợp còn chờ

- DQK review PR và team xác nhận giao diện video/live/replay tuần 1.
- DQK đã có bằng chứng 20 FPS/p95 53 ms, control loss 0%, watchdog 305-315 ms
  và e-stop với bánh nâng khỏi sàn trong `reports/DoanQuocKien/week-01.md`.
  Cần đo lại video với receiver/logger tích hợp để đạt p95 < 50 ms và ghi D1.
- Team xác nhận đề xuất GC2145 UDP-tile/HTTP-relay; tích hợp code chưa thay
  cho phê duyệt giao diện hoặc flash/đo lại firmware thật.
- Đo GPU baseline trên RTX 4050 6 GB theo target của dự án.

Các số đo localhost chỉ chứng minh logic/transport tổng hợp. Timestamp camera
hiện bắt đầu sau `camera.read()`, nên latency chưa bao gồm exposure/read time.
Sequence gaps có cả frame bị bỏ chủ động và chưa thể dùng làm packet loss.
Kết quả RTX 5060 và phép đo riêng từng model chưa thay thế RTX 4050 hoặc
ngân sách FPS/VRAM của toàn pipeline. Đồng bộ lại clock sau Jetson restart.
