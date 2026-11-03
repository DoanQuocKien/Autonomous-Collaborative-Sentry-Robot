# Chương 1 — Giới thiệu và bài toán

**Bản thảo kouun-rokku (KR), 2026-11-02.** Ngân sách chương: 1,0 trang theo phân công tại [Mid-Term Report Plan](../../docs/Mid-Term%20Report%20Plan.md). Phản ánh đầy đủ mục tiêu, bối cảnh bài toán, ba giai đoạn vận hành, giới hạn phạm vi và mô tả phần cứng hệ thống.

---

## 1.1 Bối cảnh và bài toán an ninh tự hành

Trong các khu vực văn phòng, hành lang làm việc và phòng thí nghiệm, công tác kiểm soát an ninh truyền thống dựa trên hệ thống camera giám sát cố định thường gặp phải các điểm mù quan sát, không thể phản ứng chủ động hoặc theo dõi liên tục khi đối tượng di chuyển qua nhiều khu vực che khuất. Ngược lại, nếu chỉ sử dụng robot di động tuần tra đơn lẻ thì robot khó có thể túc trực liên tục tại cửa ra vào và dễ bị phân tán năng lượng.

Đề tài **"Autonomous Collaborative Sentry Robot"** giải quyết bài toán trên thông qua mô hình phối hợp giữa:
1. **Trạm kiểm soát cố định tại cửa (Doorway Sentry / ESP32-CAM):** Quan sát trực diện lối vào, ghi nhận người ra vào, đối soát danh sách nhân sự được phép (whitelist) thông qua nhận diện khuôn mặt và trích xuất vector ngoại hình phục vụ bàn giao nhận dạng.
2. **Robot tuần tra mặt sàn (Mobile Sentry / JetBot):** Đóng vai trò phản ứng nhanh, tự hành định vị, tiếp nhận mục tiêu xâm nhập từ hàng đợi, truy bám theo cự ly an toàn, giữ vị trí cảnh giới và tìm kiếm trong phòng khi mục tiêu lẩn khuất.

Mục tiêu chung của hệ thống là tự động hóa toàn bộ chu trình phát hiện, bàn giao và ngăn chặn xâm nhập mà không đòi hỏi sự can thiệp thủ công của nhân viên an ninh trong điều kiện vận hành danh định.

---

## 1.2 Ba giai đoạn hoạt động chính

Hệ thống hoạt động theo 3 giai đoạn rõ ràng được chỉ định trong Đặc tả dự án ([Project Specification §1](../../docs/Project%20Specification.md)):

```
[GIAI ĐOẠN 1: THIẾT LẬP]
Khám phá phòng -> Nhận diện cửa (XFeat) -> Tiếp cận Sweet-spot -> Bắt tay ESP32 -> Lùi về Standby
                                                                                       |
[GIAI ĐOẠN 2: GIÁM SÁT CỬA]                                                           v
ESP32 phát hiện người -> Face Verification -> Whitelist OK: Cho phép (Robot giữ Standby)
                                          -> Kẻ xâm nhập: Trích xuất re-ID & Sector -> TargetQueue
                                                                                       |
[GIAI ĐOẠN 3: ĐÁNH CHẶN]                                                              v
Bàn giao sang StateMachine -> Robot xuất phát (PURSUE, 1.2 m) <--> Mục tiêu dừng (HOLD gần 2.0 s)
                                    |
                    Mục tiêu rời phòng / Tấn công
                                    v
                    SEARCH (Phủ bản đồ) / EVADE (Né đòn)
```

1. **Giai đoạn 1 — Thiết lập và Bắt tay (Setup & Handshake):** Robot xuất phát từ vị trí bất kỳ, quét góc phòng, sử dụng mô hình đặc trưng cục bộ XFeat đối sánh với ảnh mẫu cửa $I_{\text{ref}}$ để định vị cửa vào duy nhất của phòng. Robot tự hành di chuyển tới vị trí quan sát tối ưu (sweet-spot cách cửa 1,5–3,0 m), phát âm thanh thông báo `"place_camera"` yêu cầu người vận hành đặt module ESP32-CAM tại cửa. Robot kiểm tra bắt tay quang học (`ESP32Handshake`), xác nhận camera cửa hướng đúng vào phòng (`"camera_verified"`), sau đó lùi về vị trí chờ danh định (`STANDBY`) và lưu bản đồ lưới chiếm chỗ.
2. **Giai đoạn 2 — Giám sát lối vào (Access Monitoring):** Module ESP32-CAM ghi nhận người bước qua cửa. Luồng ảnh được phân tích qua bộ nhận diện khuôn mặt SCRFD/MobileFaceNet (`buffalo_s`). Nếu độ tương đồng cosine $\ge 0,45$ với mẫu đăng ký, đối tượng được xác nhận hợp lệ và ghi log; robot tiếp tục giữ trạng thái `STANDBY`. Nếu đối tượng không khớp whitelist, hệ thống trích xuất vector ngoại hình toàn thân 512D bằng mạng OSNet ($\vec{a}_{\text{target}}$), phân loại sector rời cửa (Trái/Giữa/Phải) dựa trên độ trôi bounding box trong 2,0 s, đẩy bản ghi vào hàng đợi FIFO (`TargetQueue`), và gửi sự kiện `INTRUDER_QUEUED` kích hoạt robot xuất kích.
3. **Giai đoạn 3 — Đánh chặn và Truy bám (Interception & Pursuit):** Robot chuyển sang trạng thái `PURSUE`, sử dụng YOLOv8 kết hợp ByteTrack và bộ lọc ngoại hình OSNet để bám đúng kẻ xâm nhập. Bộ điều khiển PD duy trì cự ly $1,2\text{ m}$ và giữ mục tiêu ở giữa trường nhìn. Nếu có vật cản gần ($d_{\text{obs}} < 0,5\text{ m}$), bộ điều khiển né vật cản được kích hoạt. Khi kẻ xâm nhập dừng bước ($v_{\text{target}} < 0,1\text{ m/s}$ trong $> 2,0\text{ s}$), robot chuyển sang trạng thái `HOLD` (dừng tịnh tiến, xoay tại chỗ căn giữa, tuyệt đối không bay vòng quanh/orbit để tránh mất góc nhìn). Nếu bị tấn công áp sát (kinh nghiệm va chạm nhanh), robot kích hoạt xung né giật lùi (`EVADE`). Khi mục tiêu chủ động thoát khỏi phòng, robot chuyển sang tìm kiếm phủ bản đồ (`SEARCH`) để tìm mục tiêu tiếp theo trong hàng đợi.

---

## 1.3 Phạm vi và các giới hạn giả định

Để đảm bảo tính khả thi trên nền tảng phần cứng học tập và tài nguyên tính toán biên:
- **Giả định cấu trúc phòng:** Mỗi phòng kiểm thử chỉ có một cửa ra vào chính (quyết định kỹ thuật 2026-10-12, [Implementation Plan §1](../../docs/Implementation%20Plan.md)).
- **Mặt sàn di chuyển:** Mặt phẳng sàn cứng trong nhà (gạch men bóng phòng học hoặc sàn nhám); robot sử dụng mô hình động học bánh xe vi sai hiệu chuẩn có bù vùng chết motor.
- **Giới hạn an toàn:** Tốc độ tối đa khi thử nghiệm trên robot thực được khóa cứng ở mức cap 0,3 ($v \approx 0,22\text{ m/s}$) thông qua cờ `--max-speed` trên Jetson. Tay cầm điều khiển đóng vai trò khóa chết (dead-man switch R1) và e-stop ngắt động cơ I2C tức thời khi gặp sự cố.
- **Phân tách xử lý:** Hệ thống cho phép chạy toàn bộ pipeline điều khiển và mô hình thị giác trên Laptop thông qua kết nối Wi-Fi, đồng thời phát triển song song nhánh tối ưu TensorRT FP16 trực tiếp trên Jetson Nano (Extra Stage A/B).

---

## 1.4 Nền tảng phần cứng triển khai

1. **Robot di động (Mobile Sentry):** Khung gầm vi sai 2 bánh JetBot, trang bị máy tính nhúng Nvidia Jetson Nano (4GB RAM, 128-core Maxwell GPU), bộ điều khiển động cơ I2C PCA9685/TB6612FNG, pin Li-ion 3S 11,1–12,6V, và camera góc rộng IMX219 fisheye $160^\circ$ gắn cố định ở độ cao ống kính $H = 0,101\text{ m}$.
2. **Camera cửa (Doorway Sensor):** Vi điều khiển ESP32-CAM gắn đế nguồn MB, trang bị cảm biến ảnh OV2640 phát luồng MJPEG VGA $640\times 480$ qua giao thức HTTP (với phương án dự phòng module GC2145 truyền UDP tiles bayer đổi màu).
3. **Trạm xử lý trung tâm (Base Station / Laptop):** Máy tính xách tay cá nhân (Intel/AMD x86_64, tùy chọn GPU RTX 4050/5060 hoặc thuần CPU) thực thi các luồng điều phối trạng thái, giao diện giám sát và bộ điều khiển trung tâm.
