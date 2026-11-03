Cảm ơn bạn @DoanQuocKien đã re-review và kiểm chứng độc lập lại toàn bộ các ca tái hiện (324 ca pursuit và 41 ca hold). Nhóm tác giả đã hoàn thiện ngay 4 lưu ý bạn nêu:

1. **Thay thế `assert legal` bằng cơ chế Fail-Safe an toàn trong luồng điều khiển:**
   - Trong cả `PursuitController.compute` và `HoldController.compute`, đã thay thế câu lệnh `assert legal(...)` bằng kiểm tra điều kiện an toàn:
     ```python
     if not legal(Command(v, w, "", ""), explore_s):
         logger.warning("Controller generated illegal command (v=%.3f, w=%.3f); safe stop (0, 0) applied", v, w)
         return 0.0, 0.0, is_centered, obstacle_active
     ```
   - Điều này đảm bảo khi chạy `python -O` (tự động loại bỏ `assert`) hoặc khi gặp tình huống ngoại lệ trên luồng live, robot sẽ dừng an toàn `(0, 0)` thay vì ném exception làm gián đoạn luồng điều khiển.

2. **Hợp nhất thành một script và một file ảnh duy nhất cho Hình F15:**
   - Đã xóa bỏ hoàn toàn script trùng lặp `tools/plot_f15_localization.py` và ảnh `reports/kouun-rokku/week-05/F15_dead_reckoning_aruco.png`.
   - Toàn bộ tài liệu báo cáo (`week-05.md`, `PR-W5-KR.md`, `W5-USAGE.md`) hiện thống nhất trích dẫn duy nhất file F15 chuẩn của bạn: `tools/plot_f15_dead_reckoning.py` và `reports/DoanQuocKien/week-05/f15/F15_dead_reckoning.png`.

3. **Ghi nhận hành vi phần cứng và hẹn tinh chỉnh tại buổi thực địa 2026-11-09:**
   - Nhất trí hoàn toàn với lưu ý của bạn về việc các lệnh tiến $\ge 0,45$ và xoay $\ge 0,45$ có thể dẫn tới hiện tượng dao động (hunting) quanh biên căn giữa $\pm 10\%$. KR sẽ cùng bạn DQK theo dõi và tinh chỉnh thực tế hệ số PD/dead-zone trên robot vào buổi học thứ Hai tuần sau (09/11).

4. **Giữ vững nhãn `MÔ PHỎNG / T0 (SIMULATION)` trong Bảng 7.2:**
   - Toàn bộ 3 hàng (Hold detector, Hold Standoff, Pursuit) tại Bảng 7.2 (`reports/kouun-rokku/midterm-chapter-07.md`) đều giữ nguyên nhãn **MÔ PHỎNG / T0 (SIMULATION)**, ghi rõ giới hạn chưa qua nghiệm thu thực địa T2 (ảnh hưởng trôi góc heading $\approx 10^\circ/\text{m}$ dội vào vận tốc thế giới và quá trình bám đuổi thực địa).

---
**Kết quả kiểm thử:** Toàn bộ test suite CPU chạy qua lệnh `pytest -m "not gpu and not hil"` tiếp tục đạt **604 passed, 5 skipped, 4 deselected in 22.60s**. Sẵn sàng cho @HuynhNguyenHoaiLoc duyệt chính thức.
