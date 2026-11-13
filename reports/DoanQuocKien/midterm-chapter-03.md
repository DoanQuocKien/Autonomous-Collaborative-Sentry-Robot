# Chương 3 — Kiến trúc hệ thống

**Bản thảo DQK (2026-11-13), ngân sách 2 trang theo [Mid-Term Report Plan](../../docs/Mid-Term%20Report%20Plan.md).** Số liệu lấy từ `config.toml`, `jetson/`, `docs/Edge Deployment.md` và `reports/DoanQuocKien/week-06/classroom_1111_pm/README.md`; mọi con số là một buổi đo, chưa phải nghiệm thu T1/T2. Hình: F1, F2 (sơ đồ), F7, F8.

---

## 3.1 Phân chia ba thiết bị

Hệ thống gồm ba thiết bị với vai trò tách biệt (Hình F1):

- **Laptop (RTX 4050 6 GB, Windows 11)** chạy **toàn bộ mô hình** và máy trạng thái: YOLOv8n (vật cản, người), YOLOv8n-pose (điểm khớp thân để đo khoảng cách), InsightFace (SCRFD + MobileFaceNet, xác minh khuôn mặt), OSNet (nhận dạng lại người), XFeat và DINOv2 (nhận diện cửa vào). Laptop cũng phát các lời nhắc âm thanh đã sinh sẵn (TTS ngoại tuyến) qua loa của chính nó, vì robot không có loa (bỏ ngày 26/10 để giảm chi phí).
- **JetBot (Jetson Nano 4 GB, Ubuntu 18.04, Python 3.6)** chỉ **thu hình và điều khiển động cơ**; mã của nó nằm riêng trong `jetson/` với yêu cầu tối thiểu, không dùng chung môi trường với laptop. Một chế độ mở rộng tùy chọn chạy suy luận ngay trên robot bằng TensorRT FP16 (mục 5.x).
- **ESP32-CAM (2,4 GHz)** là camera cố định tại cửa; laptop xử lý khuôn mặt từ luồng của nó. Có hai biến thể phần cứng: module OV2640 (JPEG phần cứng, luồng HTTP MJPEG) và module GC2145 của nhóm (không có JPEG phần cứng, dùng luồng ô ảnh UDP, `docs/ESP32-CAM.md`).

Giả định đơn giản hóa: mỗi phòng một cửa vào; nhận diện cửa được đăng ký theo từng phòng.

## 3.2 Liên kết mạng và giao diện (Hình F2)

| Liên kết | Giao thức, cổng | Nội dung | Ghi chú |
| :-- | :-- | :-- | :-- |
| JetBot → laptop | ZeroMQ, 5555 | JPEG q60 640×480, khoảng 20 fps | chỉ lấy khung hình mới nhất |
| Laptop → JetBot | UDP, 5556, 30 Hz | (v, ω) trong [−1, 1] | không chặn; khi dừng gửi, watchdog 300 ms trên robot dừng động cơ |
| Đồng bộ đồng hồ | UDP, 5557 | 20 gói echo, lọc RTT nhỏ nhất | độ bất định ước lượng khoảng 1,7 ms (theo Cristian, 1989) |
| ESP32 → laptop | HTTP MJPEG cổng 81 (VGA) hoặc luồng ô ảnh UDP | khung hình cửa | một người đọc mỗi lần |

Thiết kế dự kiến dùng 5 GHz cho laptop–JetBot và 2,4 GHz cho ESP32; trong các buổi thử gần đây cả hai đều qua hotspot điện thoại 2,4 GHz (kênh 1), nên kết quả bên dưới là của điều kiện đó.

**Độ trễ video đo ngày 12/11 (F7):** hai lần 120 s, robot đứng yên cạnh laptop (−31 dBm), `tools.log_latency` sau đồng bộ đồng hồ: trễ giải mã **trung vị 46 ms, p95 128 ms, p99 192–199 ms, lớn nhất 317 và 411 ms**; 0 khung hình trên 500 ms; tốc độ nhận **19,6 và 19,4 fps**. So với ngưỡng trong `config.toml` (≥ 20 fps, p95 ≤ 50 ms) cả hai lần **chưa đạt**, trong điều kiện thuận lợi nhất (đứng yên, tín hiệu mạnh).

## 3.3 Thiết kế an toàn

Robot là tài sản của trường nên an toàn được thiết kế nhiều lớp, không phụ thuộc vào laptop:
- **Dead-man + e-stop trên robot** (`jetson/estop.py`): giữ Start 1,5 s để vũ trang, phải **giữ R1** để chạy; thả R1 hoặc nhấn **bất kỳ nút nào khác** thì dừng ngay. `jetson/robot_udp.py` từ chối lệnh khi e-stop chưa chạy, chưa vũ trang hoặc mất nhịp tim.
- **Giới hạn lệnh:** tốc độ tối đa 0,3 (cấu hình trên robot); lệnh phải hợp lệ so với vùng chết động cơ (`min_pwm` 0,12); pin tối thiểu 11,4 V để bắt đầu chạy, dưới 10,5 V phải sạc.
- **Watchdog 300 ms:** nếu luồng lệnh ngừng, động cơ dừng.

**Thời gian dừng đo ngày 12/11 (bánh xe nhấc khỏi sàn, nhật ký của chính Jetson):** 16 lần thả R1: e-stop **cắt động cơ trung vị 7 ms (5–11 ms)**; bộ điều khiển `robot_udp` thấy chốt khóa trung vị 6–7 ms sau đó và từ chối các lệnh còn gửi tới; 5 lần nhấn nút khác: cắt **7–8 ms**. Watchdog được quan sát tình cờ: động cơ dừng khoảng 0,28–0,30 s sau lệnh cuối. **Chưa đo:** độ trễ không dây của tay cầm và thời gian dừng cơ học của bánh xe (không có bộ mã hóa).

Các công cụ chạy có chuyển động (`find_door`, `approach_door`) còn có quy tắc của người vận hành: phải nhập **khoảng trống sàn đã đo**, công cụ tính quãng đường tối đa theo mô hình tốc độ thận trọng (0,35 m/s ở v = 0,85) và từ chối nếu không đủ chỗ; kiểm tra video còn mới trước mỗi lần di chuyển; đọc to kế hoạch và dừng 4 s để người vận hành hủy. Hai lần robot chạm ghế ngày 12/11 (không hư hại) là lý do của các quy tắc này.

## 3.4 Camera cửa ESP32: tối ưu luồng (Hình F8)

Tốc độ luồng của firmware gốc (VGA, JPEG q25, xung camera 10 MHz) **giảm dần** trên bàn thử từ 8,8 xuống 0,2 fps trong khoảng 90 phút ở cùng thiết lập. Hai tác nhân làm việc song song (kỹ sư đo, nhà phân tích đề xuất) xác định: (1) chân xung camera 20 MHz với độ mạnh ổ đĩa mặc định gây nghẽn gửi hàng giây (dấu hiệu 0,2 fps), độ mạnh 0 ở cùng 20 MHz cho 12,4 fps sạch; (2) không có rò rỉ bộ nhớ hay brownout. Bản "opt4" (cắt cảm biến 640×480 với bộ nhân xung, bộ đệm gửi 23 KB, vòng khởi động thử lại camera) đạt **11,8 fps trong 10 phút** với khuôn mặt khoảng **77 px ở 2,1 m** (firmware gốc: 22–40 px). **Kiểm tra tại cửa, 13/11 (tháp trên pin, cách cửa 1,8 m, một người, một buổi):** chiều rộng khuôn mặt do bộ phát hiện đo được là **89–91 px ở 1,8 m, 76–77 px ở 2,4 m và 68 px ở 3,0 m** (khoảng cách đo bằng thước), cao hơn nhiều so với 22–53 px của các clip D2 cũ. Điểm tương đồng cosin với danh sách trắng (ngưỡng 0,45): với **ảnh đăng ký yếu** (8 khung hình quán cà phê 28/10, mặt 22–52 px, máy ảnh khác) chỉ 6 % khung hình đạt ở 1,8 m và 65 % ở 3,0 m khi nhìn thẳng; với **đăng ký có hướng dẫn** (5 tư thế trên webcam laptop cùng ngày, công cụ `tools/enroll_guided.py`) **100 % khung hình nhìn thẳng đạt ngưỡng ở cả ba khoảng cách** (trung vị 0,61–0,67), còn khi quay đầu khoảng 45° trung vị là 0,56 / 0,48 / 0,51 và 89 % / 80 % khung hình đạt ở 2,4 / 3,0 m. Vậy nguyên nhân chính của điểm thấp là **chất lượng đăng ký**, không phải số điểm ảnh. Hạn chế: một người, cùng ngày và cùng trang phục với ảnh đăng ký, **chưa có điểm của người lạ** nên chưa tính được FAR và ngưỡng 0,45 chưa được kiểm chứng cho camera cửa; tốc độ luồng chỉ 3–12 fps trong các clip (hotspot điện thoại, tín hiệu −56 đến −64 dBm), thấp hơn 12,5 fps trên bàn thử. Chưa kiểm tra với nguồn của tháp đủ lâu và trong buổi có nhiều người.
