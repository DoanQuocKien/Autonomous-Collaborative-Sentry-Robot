# Trả lời và khắc phục toàn bộ 6 điểm review của HuynhNguyenHoaiLoc trên PR #93

Cảm ơn bạn @HuynhNguyenHoaiLoc đã review cực kỳ sắc bén, chuẩn xác và chỉ ra đúng các lỗ hổng toán học, biên động cơ và dữ liệu thực tế. Toàn bộ 6 vấn đề (5 P1, 1 P2) đã được xử lý triệt để:

---

### 1. [P1] Bắt buộc áp dụng kiểm tra vùng chết (`legal()`) SAU KHI MIX BÁNH XE, không kiểm tra riêng rẽ $v, w$ (`sentry/nav/controllers.py`)
- **Vấn đề chỉ ra:** `PursuitController().compute(0, 2.0, 0.2)` trả về $(v=0,55, w=0,30)$. Khi qua `mix(v, w)`, bánh trái $= v - w = 0,25 < 0,40$ (vùng chết động cơ JetBot), dẫn tới bánh trái bị nghẽn (stall/whine), robot bị trượt lệch. Khẳng định "mọi lệnh pursuit đều legal" trước đây là sai.
- **Khắc phục:**
  - Khi xe đang tịnh tiến ($v \ne 0$), tốc độ bẻ lái $w$ bị chặn chặt theo biên bánh chậm:
    $$|w| \le \max\left(0.0, |v| - \text{dead\_zone} - 0.01\right)$$
    Với $v = 0,55$ và $\text{dead\_zone} = 0,40$, $|w| \le 0,14$. Hai bánh xe sau mix luôn nằm trong dải $[0,41; 0,69]$, bảo đảm $\ge 0,40$ tuyệt đối.
  - Khi lùi ($v = -0,45$), lệnh lái được cố định $w = 0,0$ để cả hai bánh lùi thẳng $|-0,45| \ge 0,40$, tránh bánh trong rơi vào vùng chết.
  - Khi né vật cản gần mức nguy cấp ($< 0,35\text{ m}$) hoặc khi xe đang dừng ở cự ly standoff mà cần xoay căn giữa: chuyển hẳn sang chế độ xoay tại chỗ ($v = 0,0, |w| \ge 0,45$), hai bánh đạt $(-0,45; +0,45)$ vượt vùng chết.
  - Áp dụng kiểm tra `assert legal(Command(v, w, "", ""), explore_s)` trực tiếp ngay trong phương thức `compute()` của cả `PursuitController` và `HoldController`.
  - Thêm test `test_wheel_mixing_dead_zone_all_cases` kiểm tra toàn bộ các trường hợp tiến, lùi, xoay, dừng và né vật cản.

---

### 2. [P1] Dữ liệu vận tốc chưa đủ bằng chứng KHÔNG ĐƯỢC coi là đứng yên (`sentry/nav/hold_detector.py`)
- **Vấn đề chỉ ra:** `_estimate_velocity()` trả về $0,0$ khi $n < 5$ hoặc $span < 0,2\text{ s}$. Với luồng 4 Hz (`update_world(i*0.25, i*0.25, 0)`), cửa sổ $0,5\text{ s}$ chỉ chứa tối đa 3 mẫu nên vận tốc luôn trả về $0,0$, khiến mục tiêu đang di chuyển $1\text{ m/s}$ bị nhận diện sai thành đứng yên và kích hoạt HOLD sau $2,0\text{ s}$.
- **Khắc phục:**
  - Trong `_estimate_velocity()`: Khi $n < \text{min\_samples}$ hoặc $span < \text{min\_window\_span\_s}$, hàm trả về `(None, None, None)` biểu thị vận tốc chưa xác định/chưa đủ bằng chứng.
  - Kiểu dữ liệu trong `HoldState` chuyển thành `speed_mps: Optional[float]`, `vx_mps: Optional[float]`, `vy_mps: Optional[float]`.
  - Trong `update_world()`: Khi `speed is None`, thời gian dừng được treo/xóa ngay lập tức (`self._stationary_start_t = None`, `dwell_progress = 0.0`). Thời gian dừng chỉ được tích lũy khi vận tốc đã xác định và strictly $< \text{speed\_threshold\_mps}$.
  - Thêm regression test `test_sparse_frame_low_rate_moving_target_never_triggers_hold`: Chạy 17 bước ở 4 Hz với mục tiêu di chuyển $1\text{ m/s}$, kiểm tra `in_hold` không bao giờ bật và `dwell_progress_s == 0.0` liên tục.

---

### 3. [P1] Đồng bộ hóa việc giải phóng HOLD khi có khoảng trống quan sát (Gap Reset) sang `InterceptionController` (`sentry/nav/controllers.py`)
- **Vấn đề chỉ ra:** Khi mất dấu mục tiêu $> 1,0\text{ s}$, `HoldDetector` âm thầm đặt `in_hold = False` mà không phát ra event nào; `InterceptionController` vẫn giữ nguyên `mode = "HOLD"` và tiếp tục xoay tại chỗ. Các mẫu di chuyển sau đó cũng không phát `TARGET_MOVING` vì detector đã ra khỏi HOLD từ trước.
- **Khắc phục:**
  - Trong `HoldDetector.update_world()`: Khi xảy ra gap $> \text{max\_observation\_gap\_s}$ từ trạng thái HOLD trước đó, phát ra sự kiện tường minh `event = "TARGET_LOST"`.
  - Trong `InterceptionController.step()`: Đồng bộ hóa chế độ:
    ```python
    if event == "TARGET_STATIONARY":
        self._mode = "HOLD"
        self.hold.reset()
    elif event in ("TARGET_MOVING", "TARGET_LOST") or (self._mode == "HOLD" and not hstate.in_hold):
        self._mode = "PURSUE"
        self.pursuit.reset()
    ```
  - Thêm integration test `test_gap_reset_reconciles_interception_controller_mode_and_resumes_pursuit`: Vào HOLD ở 20 Hz trong 3s $\rightarrow$ gap 2s ở $t=5.0\text{ s}$ $\rightarrow$ bộ điều khiển tự động hoàn nguyên về `PURSUE` $\rightarrow$ mục tiêu chuyển động được bám đuổi với $v > 0,4$.

---

### 4. [P1] Từ chối dữ liệu đo không hữu hạn (NaN/Inf) TRƯỚC KHI làm biến đổi trạng thái nội bộ (`sentry/nav/controllers.py`)
- **Vấn đề chỉ ra:** `PursuitController().compute(0, float('nan'), 0)` trả về $v = 0,55$ và làm biến chất `_prev_dist_err = nan`; `HoldController().compute(0, float('nan'))` trả về $w = 0,8$ và làm bẩn `_prev_yaw_err`.
- **Khắc phục:**
  - Xác thực toàn diện tất cả các biến đầu vào (`t`, `target_dist_m`, `yaw_err`, `obstacle_dist_m`, `obstacle_bearing_rad`) bằng `math.isfinite()` và kiểm tra cự ly không âm $\ge 0,0$ ngay tại đầu hàm `compute()`.
  - Nếu dữ liệu không hợp lệ, ném `ValueError` ngay lập tức **trước khi** cập nhật `self._prev_t`, `self._prev_dist_err`, `self._prev_yaw_err`, `self._entered_t`.
  - Thêm test `test_nonfinite_inputs_rejected_without_mutating_state`: Kiểm tra chặn NaN/Inf/cự ly âm, xác nhận biến trạng thái nội bộ không bị thay đổi và bước gọi hợp lệ tiếp theo hồi phục trơn tru.

---

### 5. [P1] Xóa bỏ hoàn toàn đường cong ArUco nhân tạo trong Hình F15 (`tools/plot_f15_localization.py`)
- **Vấn đề chỉ ra:** Đường cong ArUco trong F15 trước đây dùng phương trình hàm sin nhân tạo `s_frac*corr_end_y + 0.018*sin(...)` thay vì dữ liệu đo đạc thực tế 59 lần PnP.
- **Khắc phục:**
  - Hợp nhất PR #94 từ `origin/main` (`63c63ba`).
  - Viết lại hoàn toàn `tools/plot_f15_localization.py` để sử dụng trực tiếp dữ liệu đo đạc thực tế của DQK (`tools/plot_f15_dead_reckoning.py`):
    * Panel A: Điểm kết thúc đo bằng thước dây (Ground Truth) so với ước lượng dead reckoning (open loop vs closed loop ArUco) ngày 24/10. Chỉ vẽ các điểm kết thúc và đoạn thẳng sai số, **không vẽ bất kỳ đường cong nội suy giả lập nào**.
    * Panel B: Sai số vị trí cuối (cm) so sánh với ngưỡng đề cương ($40\text{ cm}$ cho DR thuần, $15\text{ cm}$ cho ArUco).
    * Panel C: 5 lượt chạy triển khai ngày 30/10 với độ lệch thước dây từ sweet-spot theo các kịch bản bám bảng.
  - Xuất lại `reports/kouun-rokku/week-05/F15_dead_reckoning_aruco.png` hoàn toàn từ số liệu thực nghiệm.
  - Cập nhật báo cáo `week-05.md` và `PR-W5-KR.md` ghi rõ F15 chỉ bao gồm điểm đo cuối và độ lệch thước dây.

---

### 6. [P2] Chuẩn hóa lại các chỉ số và nhãn nghiệm thu trong Bảng 7.2 (`reports/kouun-rokku/midterm-chapter-07.md`)
- **Vấn đề chỉ ra:**
  - Khoảng cách vật cản: p90 $= 20,91\%$ vượt ngưỡng $20\%$, chỉ có 8/9 chair IDs đo được khoảng cách (chưa đạt protocol T1) $\rightarrow$ Không thể đánh dấu PASS.
  - Vật cản sát sàn (D5): Nhầm lẫn giữa precision và recall của ba lô trên tập D5-640.
  - Tài nguyên GPU: $0,939\text{ GiB} \approx 1,008\text{ GB}$ (thập phân), nhãn $19,65\text{ FPS}$ là benchmark workload trên RTX 5060, chưa nghiệm thu live song luồng trên RTX 4050.
- **Khắc phục:**
  - Hàng "Khoảng cách vật cản": Đổi thành **FAIL / PENDING (Dev-val only)**: Ghi rõ trung vị đạt $5,34\%$, nhưng p90 đạt $20,91\%$ (vượt ngưỡng $20\%$) và chỉ có 8/9 chair IDs đo được cự ly.
  - Hàng "Vật cản sát sàn (D5)": Sửa lại chính xác theo file nguồn `reports/HuynhNguyenHoaiLoc/week-04/d5_corrected_validation.json`: Chân người recall $96\%$, ba lô **recall đạt $100\%$ ($1,0$), precision đạt $91,8\%$**, dây điện recall $0\%$.
  - Hàng "Tài nguyên GPU máy trạm": Đổi thành **PASS (Workload Benchmark)**: Ghi rõ benchmark workload trên RTX 5060 ở chế độ định thời 5Hz (thực tế đạt $4,52\text{ Hz}$) đạt $19,65\text{ FPS}$, peak VRAM **$0,939\text{ GiB} \approx 1,008\text{ GB}$**; ghi chú rõ giới hạn chưa nghiệm thu trực tiếp trên RTX 4050 / dual-stream live.

---

### Tổng kết kiểm thử tự động
- **Unit test suite:** Toàn bộ test suite CPU chạy qua lệnh `pytest -m "not gpu and not hil"` đạt **604 passed, 5 skipped, 4 deselected in 24.63s**.
- **ByteTrack Parity:** Đạt **100.0%** (407/407).
- **Hold Detector Evaluation:** **PASS** (dwell $2.0\text{ s}$, hysteresis band maintained, 0 false hold).
- **Sim Pursuit Hold:** **PASS** (100% legal commands qua `legal()`).
- **Python 3.6 AST:** 100% các file trong `third_party/bytetrack/` hợp lệ cú pháp Python 3.6.
