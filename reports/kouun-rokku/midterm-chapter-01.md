# Chương 1 — Giới thiệu

**Autonomous Collaborative Sentry Robot — CS532**

Báo cáo giữa kỳ • DQK / HNHL / KR • Bản tổng hợp ngày 14/11/2026

**Mục tiêu:** phối hợp một robot di động và một camera cố định tại cửa để phát hiện người chưa được cho phép, tiếp cận họ ở cự ly an toàn và giữ cảnh giới khi họ đứng yên. Ứng dụng hướng tới phòng học hoặc phòng làm việc có một cửa vào, với người vận hành giám sát và quyền dừng robot bằng tay cầm.

## 1.1 Bài toán và ba pha

| Pha | Đầu vào | Xử lý và đầu ra dự kiến |
| :-- | :-- | :-- |
| 1. Triển khai | Video robot, tham chiếu cửa, hiệu chuẩn | Tìm cửa, chọn điểm quan sát, yêu cầu đặt ESP32, xác minh và lùi về chờ |
| 2. Giám sát | Luồng ESP32 tại cửa, whitelist | Xác thực khuôn mặt, tạo hồ sơ người lạ với appearance/sector, đưa vào FIFO |
| 3. Đánh chặn | Video robot, mục tiêu đang hoạt động | PURSUE → HOLD; tìm lại người mất dấu; xử lý người tiếp theo |

Đầu ra phần mềm là trạng thái, lời nhắc âm thanh, hồ sơ mục tiêu và lệnh vận tốc (v, w). Laptop giữ mô hình thị giác và điều phối; JetBot thu hình và chạy động cơ; ESP32 cung cấp góc nhìn tại cửa. Khả năng tự hành được giới hạn bởi độ tin cậy khoảng cách vật cản và định vị không encoder.

## 1.2 Phạm vi đã triển khai

Đã có các module truyền hình/điều khiển, định vị dead reckoning–ArUco, nhận diện cửa, face/re-ID/tracking, hàng đợi, máy trạng thái và bộ điều khiển bám/giữ vị trí. KR đã nối chuỗi Phase 2 → Phase 3 và kiểm thử CPU/mô phỏng; các lượt robot hiện có là thử có giám sát, chưa chứng minh vòng đầy đủ không can thiệp. Né tấn công và coverage search trên robot là mục tiêu sau giữa kỳ.

**Phạm vi số liệu:** kết quả laptop RTX 5060, laptop RTX 4050 và Jetson được ghi riêng. Dữ liệu pilot, dev-val, mô phỏng và thử robot không được dùng thay nhau để nghiệm thu. Số liệu nguồn PR #108 được lưu kèm commit và SHA256, ghi là owner-reported/unmerged; không đưa code PR #108 vào gói này. [S0, D13]

**Tình trạng bàn giao:** đây là bản editor có PDF để review; chốt nội dung theo lịch 18–22/11 và nộp 23/11. Các phép đo còn thiếu được giữ là pending trong chương 7–8.
