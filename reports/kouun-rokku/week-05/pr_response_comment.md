Cảm ơn bạn @DoanQuocKien đã review rất kỹ lưỡng và phát hiện đúng các điểm cốt lõi về dữ liệu thực nghiệm và khoảng cách phần cứng. Toàn bộ các góp ý trong cả hai lượt review đã được khắc phục hoàn toàn trong commit `34d5259`:

### 1. Dữ liệu thực nghiệm & Báo cáo Giữa kỳ
- **Hình F15 (`tools/plot_f15_localization.py`):** Đã xóa toàn bộ số liệu giả lập nhân tạo (`0.065 rad/s`, `ay *= 0.25`). Hình F15 hiện được vẽ trực tiếp từ dữ liệu log vật lý thực tế của run `t2_1024_2_follow` (2026-10-24, PR #56): tích hợp 304 lệnh thực tế từ `commands.csv` cho đường thuần dead-reckoning (lệch $98,3\text{ cm}$, góc xoay kết thúc $-51,7^\circ$) và quỹ đạo bám chuỗi mốc với 59 lần PnP fix (lệch $14,5\text{ cm}$) so với vạch thước đo thực địa ($2,95\text{ m}$). Chú thích hình và Báo cáo ghi rõ trạng thái: **PENDING (1/5 lượt)** vì tiêu chí T2 yêu cầu tối thiểu 5 lượt đạt liên tục; thuần DR xác nhận **FAIL** ($98,3\text{ cm}$ so với ngưỡng $40\text{ cm}$).
- **Hình F12 (`tools/plot_f12_entrance.py`):** Điều chỉnh trục Y và dời legend sang góc trên bên phải; nhãn số liệu $100.0\%$ hiện rõ ràng không còn bị che khuất. Chú thích rõ ràng ORB là "(Baseline, dropped in plan)".
- **Bảng 7.2 Chương 7 (`reports/kouun-rokku/midterm-chapter-07.md`):**
  - Tách hàng "Định vị & Odometry" thành 2 hàng riêng biệt:
    * *Có mốc ArUco:* PENDING (1/5 lượt, đạt $14,5\text{ cm}$, trích dẫn `reports/DoanQuocKien/week-03/t2_dead_reckoning/README.md`).
    * *Thuần Dead Reckoning:* FAIL (lệch $98,3\text{ cm}$ ngày 24/10 và $0,8–1,0\text{ m}$ ngày 30/10).
  - Hàng "Bám đối tượng (ByteTrack)": Đánh dấu chỉ số $\le 1$ lần/phút trên video $\ge 60\text{ s}$ là **CHƯA ĐO TRÊN VIDEO THỰC (PENDING)**; tầng T0 đạt tương đồng gán ID $100\%$ với Ultralytics.
  - Hàng "Bộ phát hiện dừng (Hold)", "Điều khiển Hold Standoff", "Bám đuổi mục tiêu (Pursuit)": Ghi rõ **MÔ PHỎNG / T0 (SIMULATION)**, chưa qua nghiệm thu thực địa T2 (chưa kiểm thử ảnh hưởng trôi heading $\approx 10^\circ/\text{m}$ dội vào vận tốc thế giới của mục tiêu).
  - Hàng "Tự hiệu chuẩn góc camera": Báo cáo rõ sai số trung vị khi chạy đạt $7,8\%$ (dải $3–20\%$, ngưỡng $\le 10\%$), đồng thời ghi nhận hiện tượng ngày 30/10 đọc được $+2,15^\circ$ trong khi các run trước dùng file cấu hình cũ $6,0–6,2^\circ$.
  - Hàng "Đường truyền điều khiển (T2)": Trích dẫn file đo thực địa `reports/DoanQuocKien/week-01/link_test_2026-10-04.txt` và `estop_deadman_2026-10-06.txt`.

### 2. Bộ điều khiển & Vùng chết động cơ (Motor Dead Zone)
- **Chuẩn hóa Mode Name:** Đổi đồng nhất thành `"PURSUE"` và `"HOLD"` trên toàn bộ các file code, output telemetry, và bài test (khớp với `sentry.app.state_machine.State.PURSUE`).
- **Bù vùng chết động cơ ($\text{dead} = 0,40$):**
  - Trong `HoldController`: Khi lệch tâm ($> \pm 10\%$), lệnh xoay chủ động được nâng lên $|w| \ge 0,45$ ($w_{\text{spin}}$), chống hiện tượng động cơ JetBot chỉ kêu rít mà không quay. Khi đã căn giữa trong dải cho phép, dừng triệt để ($v=0, w=0$). Toàn bộ lệnh đều đạt `legal()`.
  - Trong `PursuitController`: Vận tốc lùi tối đa sửa thành $v_{\text{min\_reverse}} = -0,45$ (thay vì $-0,3$ bị kẹt dưới vùng chết). Khi bám đuổi, các lệnh được kiểm soát qua `legal()`.
  - Trong mô phỏng `tools/sim_pursuit_hold.py`: Các lệnh điều khiển được chạy qua `legal()` từ `sentry.nav.explore`; nếu lệnh không hợp lệ sẽ bị coi như động cơ bị stall ($v=0, w=0$). Kết quả mô phỏng xác nhận $100\%$ lệnh gửi tới SimRobot đều là `legal`.
- **Đo đạc và cưỡng chế thời gian căn giữa (`max_recenter_time_s = 1.5s`):** `HoldController` theo dõi thời gian căn giữa `max_observed_recenter_time_s`, kiểm tra `recenter_requirement_met <= 1.5s` trong cả unit test và mô phỏng kín.
- **Triệt tiêu Derivative Kick:** Khống chế thành phần vi phân khi $\Delta t > 0,2\text{ s}$ hoặc khi có khoảng trống khung hình để tránh giật đột ngột khi camera bị lag.
- **Phân định quyền sở hữu:** Ghi nhận `nav/controllers.py` là sản phẩm hợp tác giữa KR (khung tham chiếu toán học/mô phỏng trong W5) và DQK (chủ trì tinh chỉnh tham số trên phần cứng robot JetBot vào buổi thực địa 2026-11-09).

### 3. Vendored ByteTrack & Parity Test
- **Bản quyền & API Chuẩn:** `third_party/bytetrack/` đã chuẩn hóa hoàn toàn về API chuẩn của `ifzhang/ByteTrack` (MIT, 2021) với các tham số `track_thresh`, `track_buffer`, `match_thresh`, nhận mảng NumPy thuần `[x1, y1, x2, y2, score, ...]`, loại bỏ hoàn toàn các cấu trúc wrapper của Ultralytics (AGPL) và xóa bỏ ghi chú về `lap` fast-path không tồn tại.
- **Parity Test Khắt khe:** Nâng cấp phương pháp so sánh sang Hungarian matching theo từng frame và **tính tất cả các track bị rớt/không khớp như một disagreement**. Kiểm tra cả kịch bản đa mục tiêu lẫn kịch bản 2 đối tượng giao cắt và che khuất: đạt **$100.0\%$ ID agreement** (407/407 lượt đánh giá).

### 4. Single Source of Truth trong `config.toml`
- Xóa bỏ toàn bộ các tham số trùng lặp trong `[hold]` và `[pursuit]`. Tất cả các ngưỡng vật lý (`standoff_m`, `standoff_tolerance_m`, `obstacle_pursuit_m`, `stationary_speed_mps`, `stationary_time_s`, `stationary_exit_speed_mps`) đều được tải trực tiếp từ mục gốc `[thresholds]`.

---
**Kết quả kiểm thử toàn diện:** Toàn bộ test suite CPU (`pytest -m "not gpu and not hil"`) chạy sạch: **600 passed, 5 skipped, 4 deselected in 21.63s**. Log kiểm thử và số liệu đã được cập nhật tại `reports/kouun-rokku/week-05/`.
