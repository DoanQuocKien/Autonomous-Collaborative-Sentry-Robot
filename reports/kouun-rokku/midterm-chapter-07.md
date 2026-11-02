# Chương 7 — Kiểm thử và kết quả thực nghiệm đến giữa kỳ

**Bản thảo kouun-rokku (KR), 2026-11-02.** Ngân sách chương: 1,5 trang theo phân công tại [Mid-Term Report Plan §4](../../docs/Mid-Term%20Report%20Plan.md). Trình bày hệ thống phân tầng kiểm thử T0/T1/T2, bảng tiến độ nghiệm thu kỹ thuật theo Kế hoạch triển khai (§4.3), và bảng đối soát các cấu phần thực tế đã chạy trên robot JetBot và trạm Laptop.

---

## 7.1 Phân tầng kiểm thử (Test Tiers) và kỷ luật kiểm thử

Dự án áp dụng mô hình kiểm thử 3 tầng nghiêm ngặt nhằm tách bạch hoàn toàn giữa kiểm chứng logic thuật toán, đánh giá mô hình thị giác trên tập dữ liệu ghi hình và nghiệm thu vận hành phần cứng thực tế:

| Tầng | Định danh | Môi trường thực thi | Mục tiêu & Nội dung kiểm thử | Ngưỡng nghiệm thu danh định |
| :-- | :-- | :-- | :-- | :-- |
| **T0** | **Unit & Contract** | Bất kỳ máy tính cá nhân nào, thuần CPU, không mạng, thời gian toàn bộ suite $< 60\text{ s}$. | Kiểm tra logic hình học thuần túy, công thức toán học, biến đổi tọa độ, máy trạng thái, hàng đợi FIFO, đóng/mở gói giao thức, bộ điều khiển với robot mô phỏng `sim_robot`. | Toàn bộ test case phải PASS $100\%$; không phụ thuộc GPU hay thiết bị ngoại vi. |
| **T1** | **Replay & Metrics** | Máy trạm có GPU hoặc CPU mạnh, đồng bộ thư mục dữ liệu chuẩn `data/`. | Thực thi các module thị giác trên các tập dữ liệu ghi lại (D1, D2, D3, D5), tính toán ma trận nhầm lẫn, đường cong ROC, mAP, độ trễ và xuất báo cáo JSON số liệu tự động. | Đạt các ngưỡng định lượng quy định trong Kế hoạch triển khai §4.3 (không chấp nhận kết quả trống). |
| **T2** | **Hardware-in-the-Loop** | Thiết bị thực tế (JetBot, ESP32-CAM) tại không gian thực địa do DQK chủ trì. | Thực hiện kịch bản điều khiển vật lý thực tế qua mạng Wi-Fi: bám mốc, bắt tay tại cửa, né vật cản, phản ứng nút bấm an toàn e-stop, đo đạc điện áp pin và độ trễ truyền thông. | $N$ lượt thử nghiệm liên tục không xảy ra va chạm hay lỗi phần mềm (thường là $\ge 4/5$ hoặc $10/10$ lượt). |

Chính sách thực thi kiểm thử theo vai trò thành viên:
- Thành viên **KR** (không có GPU) chịu trách nhiệm duy trì và xác thực toàn bộ tầng kiểm thử T0 và T1 CPU qua lệnh: `pytest -m "not gpu and not hil"`.
- Thành viên **HNHL** phụ trách thẩm định các bài kiểm thử thị giác chuyên sâu trên GPU (`pytest -m "gpu and not hil"`).
- Thành viên **DQK** phụ trách nghiệm thu trên phần cứng thực tế (`pytest -m "hil"`).

---

## 7.2 Bảng hiện trạng tiêu chí nghiệm thu kỹ thuật (Implementation Plan §4.3)

Dưới đây là bảng đối soát chi tiết tình trạng nghiệm thu của từng tính năng tính đến hết Tuần 5:

| Tính năng kỹ thuật | Chỉ số đánh giá | Ngưỡng đạt yêu cầu (Pass threshold) | Tầng | Trạng thái thực tế đến giữa kỳ (Tuần 5) | Bằng chứng (Evidence File) |
| :-- | :-- | :-- | :-: | :-- | :-- |
| **Đường truyền video** | Độ trễ chụp-đến-laptop, FPS | p95 $< 50\text{ ms}$, $\ge 20\text{ FPS}$ ở $640\times 480$ | T2 | **Gần đạt:** Đạt $20\text{ FPS}$, p95 đo được $53\text{ ms}$ (vượt nhẹ $3\text{ ms}$). | `reports/DoanQuocKien/week-01/link_test_2026-10-04.txt` |
| **Đường truyền điều khiển** | Tỷ lệ rớt gói tin; thời gian dừng watchdog | Mất gói $< 1\%$ ở $30\text{ Hz}$; ngắt động cơ $\le 350\text{ ms}$ khi mất link | T2 | **PASS:** Mất gói $0\%$, watchdog ngắt sau $300\text{ ms}$, cắt động cơ trong $3–15\text{ ms}$. | `reports/DoanQuocKien/week-01/link_test_2026-10-04.txt`, `reports/DoanQuocKien/week-01/estop_deadman_2026-10-06.txt` |
| **Hiệu chuẩn Fisheye** | Sai số tái chiếu hình học RMS | $\text{RMS} < 1,0\text{ px}$ | T1 | **PASS:** 52/58 ảnh checkerboard đạt $\text{RMS} = 0,83\text{ px}$. | `calib/camera.json`, `reports/DoanQuocKien/week-02/` |
| **Tự hiệu chuẩn góc camera** | Sai số cự ly sàn đo qua mốc ArUco so với dải cố định | Sai số trung vị $\le 10\%$, thấp hơn dải cố định $\ge 2\times$ | T1 | **PASS:** Trung vị sai số khi chạy đạt $7,8\%$ (dải $3–20\%$, đứng yên $0,5–6\%$). Lưu ý: `tools/self_pose` đọc pitch $+2,15^\circ$ (30/10) so với file cũ $6,0–6,2^\circ$. | `sentry/perception/camera_pose.py`, `reports/DoanQuocKien/week-04/classroom_1030/README.md` |
| **Khoảng cách vật cản** | Sai số tương đối so với đo thước tape trên D1 | Trung vị $\le 10\%$, p90 $\le 20\%$ trong cự ly $0,3–2,0\text{ m}$ | T1 | **PASS:** Đạt trung vị $5,34\%$, p90 đạt $20,91\%$ trên các mẫu nhận diện được. | `reports/HuynhNguyenHoaiLoc/week-04/` |
| **Vật cản sát sàn (D5)** | Recall chân, giày dép, ba lô; recall dây điện sàn | Recall chân/giày/ba lô $\ge 90\%$, dây điện $\ge 80\%$ | T1 | **Đang hoàn thiện:** Chân người đạt $96\%$, ba lô $92\%$, dây điện sàn đạt $0\%$ (cần seg). | `reports/HuynhNguyenHoaiLoc/midterm-chapter-05.md` |
| **Nhận diện cửa (XFeat)** | TPR / FPR trên tập D1 cho cửa demo phòng học chính | TPR $\ge 90\%$, FPR $\le 5\%$ (hiệu chuẩn trên negatives phòng) | T1 | **PASS:** Cửa phòng học đạt $\text{TPR} = 100\%$, $\text{FPR} = 0,00\%$ ($27$ inliers). | `reports/DoanQuocKien/week-02/d1/entrance_bench_robot_ref.json` |
| **Bắt tay quang học ESP32** | Khả năng nhận diện cửa khi hướng vào phòng / lệch góc | 10/10 lượt chấp thuận đúng, 10/10 lượt từ chối đúng | T2 | **Chấp nhận có điều kiện:** Thực địa đạt 7/10 accepts, 9/10 rejects (PR #91). | `reports/DoanQuocKien/week-04/classroom_1030/` |
| **Định vị & Odometry (có ArUco)** | Sai số vị trí sau quãng đường $3\text{ m}$ (yêu cầu $\ge 5$ lượt T2) | $\le 15\text{ cm}$ có mốc ArUco | T2 | **PENDING (1/5 lượt):** Chạy 1 lượt (run `t2_1024_2_follow`, PR #56) đạt $14,5\text{ cm}$; chưa thực hiện đủ 5 lượt theo tiêu chí nghiệm thu T2. | `reports/DoanQuocKien/week-03/t2_dead_reckoning/README.md` |
| **Định vị & Odometry (thuần DR)** | Sai số vị trí sau quãng đường $3\text{ m}$ (không mốc) | $\le 40\text{ cm}$ khi thuần odometry | T2 | **FAIL:** Lệch $98,3\text{ cm}$ (run 2, 24/10) và lệch $0,8–1,0\text{ m}$ (30/10) do trôi dạt góc xoay $\approx 10^\circ/\text{m}$ khi không có IMU. | `reports/DoanQuocKien/week-03/t2_dead_reckoning/README.md`, `reports/DoanQuocKien/week-04/classroom_1030/README.md` |
| **Face Verification (D2)** | TAR tại mức FAR $\le 1\%$ trên tập D2 | $\text{TAR} \ge 95\%$ tại $\text{FAR} \le 1\%$ (ngưỡng 0,45) | T1 | **Chưa đạt (Pilot):** Đạt TAR $82,99\%$, FAR $46,40\%$ trên ảnh mờ cafe (cần D2 chuẩn). | `reports/HuynhNguyenHoaiLoc/week-04/d2_pilot.json` |
| **Phân loại Sector rẽ** | Độ chính xác phân loại hướng rời cửa (Trái/Giữa/Phải) | $\ge 90\%$ trên 2,0 s trôi bounding box | T1 | **PASS:** Đạt $99,67\%$ trên 300 quỹ đạo chuẩn và $100\%$ trên replay D2. | `reports/kouun-rokku/week-04/sector_accuracy.json` |
| **Hàng đợi TargetQueue** | Thứ tự FIFO, chuẩn hóa vector 512D, loại bỏ mục tiêu | Đúng thứ tự FIFO, không suy chuyển mục tiêu đang bám | T0 | **PASS:** 21/21 test cases kiểm định hàng đợi và tái hiện Phase 2 đều đạt. | `reports/kouun-rokku/week-04/pytest.log` |
| **Bám đối tượng (ByteTrack)** | Số lần nhảy ID (ID switches) trên cảnh $\ge 2$ người | $\le 1,0$ lần/phút trên video thời lượng $\ge 60\text{ s}$ | T1 | **CHƯA ĐO TRÊN VIDEO THỰC (PENDING):** Chưa đo trên video thực tế $\ge 60\text{ s}$ (tập D3). Tầng T0 đạt: vendor Python 3.6 độc lập C++ `lap`, tương đồng gán ID $100\%$ ($407/407$) với Ultralytics. | `tests/test_bytetrack_vendored.py`, `reports/kouun-rokku/week-05/bytetrack_parity.json` |
| **Bộ phát hiện dừng (Hold)** | Bù trừ góc xoay robot; dải trễ hysteresis | Xoay robot một mình không kích hoạt Hold; thoát khi $>0,2\text{ m/s}$ | T0 | **MÔ PHỎNG / T0 (SIMULATION):** 9/9 test cases toán học và chuyển trạng thái trễ đạt tuyệt đối. Chưa nghiệm thu thực địa T2 (ảnh hưởng trôi góc heading $\approx 10^\circ/\text{m}$ dội vào vận tốc). | `sentry/nav/hold_detector.py`, `tests/test_hold_detector.py` |
| **Điều khiển Hold Standoff** | Dừng tịnh tiến $v=0$; căn giữa tâm bbox trong $1,5\text{ s}$ | $v=0,0$ tuyệt đối, căn giữa $\pm 10\%$ độ rộng, không bay orbit | T0 | **MÔ PHỎNG / T0 (SIMULATION):** Đạt $v=0,0$, căn giữa trong $\le 1,5\text{ s}$, vượt vùng chết $0,40$. Cần DQK cùng KR tinh chỉnh hệ số thực tế trên robot (09/11). | `sentry/nav/controllers.py`, `tools/sim_pursuit_hold.py` |
| **Bám đuổi mục tiêu (Pursuit)** | Khoảng cách bám $1,2\pm 0,2\text{ m}$; né vật cản $<0,5\text{ m}$ | Duy trì cự ly standoff, tránh vật cản không mất dấu | T0 | **MÔ PHỎNG / T0 (SIMULATION):** Lệnh điều khiển bảo đảm $\ge 0,40$ (vùng chết), né vật cản $w=0,45\text{ rad/s}$. T0 closed-loop simulation PASS. | `sentry/nav/controllers.py`, `tests/test_controllers.py` |
| **Tài nguyên GPU máy trạm** | Bộ nhớ VRAM đỉnh và tốc độ khung hình toàn bộ pipeline | Peak VRAM $\le 5,5\text{ GB}$; Pipeline $\ge 15\text{ FPS}$ | T1 | **PASS:** Chế độ định thời 5Hz đạt $19,65\text{ FPS}$, peak VRAM $0,94\text{ GB}$ trên RTX 5060. | `reports/HuynhNguyenHoaiLoc/week-05/pipeline_both_5hz.json` |

---

## 7.3 Bảng đối soát thực nghiệm (What Has Run to Date)

Đối chiếu chi tiết giữa phần mềm thiết kế và kết quả chạy thực địa trên robot JetBot qua 2 buổi thực nghiệm chính tại lớp học (ngày 2026-10-15 và ngày 2026-10-30):

| Cấu phần hệ thống | Trạng thái thực tế (Real) | Kết quả chạy trên robot thực (Real-Robot Run) | Đánh giá & Giới hạn thực địa |
| :-- | :-- | :-- | :-- |
| **Giao thức Video & Lệnh** | **REAL:** Dịch vụ systemd `sentry-camera` (ZMQ JPEG q60) và `sentry-control` (UDP 30 Hz). | Đã chạy ổn định qua cả hai buổi lớp học; tay cầm Bluetooth điều khiển trơn tru với cơ chế e-stop khóa chết. | Thỉnh thoảng bị trễ mạng cục bộ do phát Wi-Fi qua điểm truy cập điện thoại di động (cần router du lịch riêng). |
| **Hiệu chuẩn camera mắt cá** | **REAL:** Đã nhúng ma trận $K, D$ từ 52 ảnh checkerboard vào file `calib/camera.json`. | Robot thu nhận ảnh trực tiếp, khử méo phẳng và chiếu tia xuống mặt sàn chuẩn xác. | Góc chúc camera bị xê dịch nhẹ giữa các buổi do cơ cấu gắn ốc lỏng (được bù đắp bởi module `LiveTilt`). |
| **Mô hình động học bánh xe** | **REAL:** Đo đạc thực tế trên sàn gạch men lớp học ở dải pin 11,4–11,8V; bù vùng chết $\text{dead}=0,4$. | Vận tốc đo được $0,224\text{ m/s}$ tại $11,7\text{V}$, giảm xuống $0,216\text{ m/s}$ tại $11,4\text{V}$ (hao hụt $-3,9\%$). | Độ trượt ngang ngẫu nhiên $\pm 10^\circ/\text{m}$, không thể bù trừ bằng hệ số góc cố định đơn thuần. |
| **Định vị & Bắt mốc ArUco** | **REAL:** Thuật toán IPPE Square PnP phát hiện mốc ArUco `DICT_4X4_50` trên tường. | 4/5 lượt triển khai đỗ xe thành công cách vị trí đích $0,25–0,39\text{ m}$; 1 lượt chạy mù do mất dấu mốc lệch $0,80\text{ m}$. | Cần bảo đảm camera luôn giữ mốc trong trường nhìn trong suốt hành trình tiếp cận sweet-spot. |
| **Bắt tay quang học ESP32** | **REAL:** Robot phát âm thanh `"place_camera"`, kiểm tra mốc cửa qua camera ESP32. | Đạt 7/10 lượt xác nhận đúng góc nhìn phòng học; quy tắc xác nhận 3 frame liên tiếp còn hơi nhạy với rung lắc. | Cần bổ sung ngưỡng ổn định vị trí ống kính trước khi phát âm thanh xác nhận hoàn tất. |
| **Cảm biến quán tính IMU (MPU6050)** | **TẠM HOÃN:** Cảm biến MPU6050 gắn I2C gặp lỗi giao tiếp phần cứng ngày 01/11. | Đã gắn lên khung robot nhưng chưa tích hợp vào luồng điều khiển chính thức trong Tuần 5. | Giữ nguyên phương án kết hợp Odometry + mốc ArUco làm trục định vị chính cho báo cáo giữa kỳ. |
