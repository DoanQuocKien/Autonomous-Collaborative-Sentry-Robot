# Phụ lục A — Bàn giao mã nguồn và hệ thống

**Bản thảo kouun-rokku (KR), 2026-11-02.** Ngân sách chương: 1,0 trang theo phân công tại [Mid-Term Report Plan](../../docs/Mid-Term%20Report%20Plan.md). Cung cấp danh mục các module mã nguồn, phân định quyền sở hữu, hướng dẫn thiết lập môi trường, tái hiện kiểm thử tự động, và danh mục các phân đoạn kịch bản video demo.

---

## A.1 Danh mục module mã nguồn và phân công tác giả

Mã nguồn dự án được tổ chức thành các gói chức năng chuẩn hóa, phân định rõ ràng giữa tầng chạy trên thiết bị biên (Jetson Nano/ESP32) và trạm xử lý trung tâm (Laptop):

| Thư mục / Tệp tin | Module chức năng | Tác giả chính | Tầng kiểm thử tương ứng |
| :-- | :-- | :-: | :-- |
| `sentry/nav/hold_detector.py` | Phát hiện kẻ xâm nhập dừng bước có bù trừ chuyển động robot; dải trễ hysteresis. | **KR** | `tests/test_hold_detector.py` (T0) |
| `sentry/nav/controllers.py` | Bộ điều khiển bám đuổi PD cự ly $1,2\text{ m}$, căn giữa bbox, né vật cản và Standoff Hold. | **DQK / KR** | `tests/test_controllers.py` (T0) |
| `third_party/bytetrack/` | Bản vendor bộ theo dõi ByteTrack thuần NumPy/SciPy tương thích Python 3.6 cho Jetson. | **KR** | `tests/test_bytetrack_vendored.py` (T0) |
| `sentry/app/state_machine.py` | Máy trạng thái hữu hạn Phase 1–3 điều phối toàn bộ chu trình đánh chặn. | **KR** | `tests/test_state_machine.py` (T0) |
| `sentry/app/target_queue.py` | Hàng đợi đa mục tiêu xâm nhập FIFO, bảo toàn vector re-ID và sector rẽ. | **KR** | `tests/test_target_queue.py` (T0) |
| `sentry/app/deploy_runner.py` | Quy trình tiếp cận điểm quan sát, bắt tay ESP32 và lùi xe về trạm chờ Phase 1. | **DQK** | `tests/test_deploy_runner.py` (T0/T2) |
| `sentry/perception/entrance.py`| Nhận diện cửa ra vào qua đặc trưng XFeat / DINOv2 và kiểm tra bắt tay ESP32. | **KR** | `tests/test_entrance.py` (T0/T1) |
| `sentry/perception/sector.py` | Phân loại sector rẽ rời cửa (Trái/Giữa/Phải) dựa trên độ trôi ngang bounding box. | **KR** | `tests/test_sector.py` (T0/T1) |
| `sentry/perception/tracker.py` | Bộ bám đối tượng YOLOv8 + ByteTrack kết hợp khóa mục tiêu vector ngoại hình OSNet. | **HNHL** | `tests/test_tracker.py` (T0/T1) |
| `sentry/perception/reid.py` | Trích xuất vector ngoại hình 512D từ mạng OSNet và so khớp độ tương đồng cosine. | **HNHL** | `tests/test_reid.py` (T0/T1) |
| `sentry/perception/face.py` | Trích xuất embedding khuôn mặt và đối soát whitelist qua SCRFD/MobileFaceNet. | **HNHL** | `tests/test_face.py` (T0/T1) |
| `sentry/perception/obstacle.py`| Phát hiện vật cản sàn nhà và ước lượng khoảng cách dựa trên hình học camera mắt cá. | **HNHL** | `tests/test_obstacle.py` (T0/T1) |
| `sentry/nav/localization.py` | Ước lượng vị trí xe dead-reckoning kết hợp hiệu chỉnh sai số tuyệt đối qua mốc ArUco. | **KR / DQK** | `tests/test_localization.py` (T0/T2) |
| `sentry/net/` | Giao thức truyền video ZMQ, stream HTTP MJPEG, đồng bộ xung nhịp UDP echo. | **HNHL / KR** | `tests/test_mjpeg_rx.py`, `test_clock_sync.py` |
| `jetson/` | Mã nguồn chạy trực tiếp trên robot Jetson Nano (Python 3.6, systemd units, e-stop). | **DQK** | `tests/test_estop.py`, `test_jetson_espcam.py` |

---

## A.2 Hướng dẫn cài đặt và tái hiện kiểm thử

### 1. Thiết lập môi trường (Laptop):
```bash
# Clone mã nguồn
git clone https://github.com/DoanQuocKien/Autonomous-Collaborative-Sentry-Robot.git
cd Autonomous-Collaborative-Sentry-Robot

# Khởi tạo virtual environment Python 3.12+ (hoặc 3.10+)
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Tái hiện toàn bộ bài kiểm tra Unit tầng T0 (thuần CPU, không cần GPU):
```bash
pytest -m "not gpu and not hil"
```
*Ghi nhận thực tế: Toàn bộ 580+ test cases T0 chạy hoàn tất trong chưa đầy $25\text{ s}$, bao gồm các module máy trạng thái, hàng đợi, bộ điều khiển và AST check Python 3.6.*

### 3. Tái hiện mô phỏng bám đuổi kín và Standoff Hold (Tuần 5):
```bash
python3 -m tools.sim_pursuit_hold --out reports/kouun-rokku/week-05/sim_pursuit_hold.json
```

---

## A.3 Danh mục kịch bản phân đoạn video demo (Shot List)

Video minh họa (thời lượng 2–4 phút) được biên tập theo các phân đoạn chức năng độc lập:

| Phân đoạn | Nội dung ghi hình | Thiết bị ghi / Thực hiện | Trạng thái |
| :-: | :-- | :-- | :-: |
| **Shot 1** | Giới thiệu phần cứng: Robot JetBot, cảm biến mắt cá, tay cầm điều khiển e-stop và cụm camera cửa ESP32-CAM. | Quay điện thoại chân máy (DQK, KR) | Đã chuẩn bị |
| **Shot 2** | Pha 1: Robot tự khám phá, nhận diện cửa bằng XFeat, di chuyển tới sweet-spot và phát âm thanh `"place_camera"`. | Robot chạy thực địa lớp học (DQK) | Đã có tư liệu |
| **Shot 3** | Bắt tay quang học: Đặt ESP32 tại cửa, robot thẩm định đúng góc nhìn, phát âm thanh `"camera_verified"` và lùi về Standby. | Phối hợp góc nhìn camera ngoài & màn hình OBS (DQK, KR) | Đã có tư liệu |
| **Shot 4** | Pha 2: Người hợp lệ đi qua cửa $\rightarrow$ Face verification khớp whitelist $\rightarrow$ Robot giữ nguyên trạm chờ. | Màn hình giao diện OBS + luồng ESP32 (HNHL, KR) | Sẵn sàng quay |
| **Shot 5** | Pha 2: Kẻ xâm nhập bước qua cửa $\rightarrow$ Báo động $\rightarrow$ Trích xuất OSNet re-ID và hướng rẽ $\rightarrow$ Đẩy vào hàng đợi. | Màn hình giao diện OBS (HNHL, KR) | Sẵn sàng quay |
| **Shot 6** | Pha 3: Robot xuất kích, truy bám theo sau ở cự ly $1,2\text{ m}$, tự động né ghế/vật cản sàn nhà. | Quay robot thực địa + khung bounding box (DQK, HNHL) | Lên lịch Tuần 6 |
| **Shot 7** | Pha 3: Kẻ xâm nhập dừng bước $\rightarrow$ Robot dừng tịnh tiến, xoay tại chỗ căn giữa (Standoff Hold, không bay orbit). | Robot thực địa + log góc quay (DQK, KR) | Lên lịch Tuần 6 |
| **Shot 8** | Chế độ nhúng trực tiếp: Bảng đo hiệu năng mô hình TensorRT FP16 chạy trực tiếp trên Jetson Nano (20 FPS). | Quay màn hình thiết bị và tegrastats (DQK) | Đã có số liệu |

*Đường dẫn video demo được tải lên Google Drive của nhóm và dẫn link trong văn bản nộp chính thức; không commit video nhị phân vào Git.*

---

## A.4 Cam kết bảo mật dữ liệu và kiểm soát phiên bản

- **Bảo mật sinh trắc học:** Toàn bộ ảnh khuôn mặt và video của các thành viên trong tập D2 được lưu trữ nội bộ trong thư mục `data/` (đã khai báo trong `.gitignore`), tuyệt đối không đẩy lên kho mã nguồn công khai. Mọi hình ảnh trích dẫn minh họa trong báo cáo đều được xử lý làm mờ khuôn mặt tự động qua công cụ `tools/mask_faces.py`.
- **Kiểm soát phiên bản:** Bản nộp giữa kỳ chính thức sẽ được đóng băng mã nguồn và gắn thẻ (tag) cố định `midterm` trên nhánh `main` vào ngày 21/11/2026.
