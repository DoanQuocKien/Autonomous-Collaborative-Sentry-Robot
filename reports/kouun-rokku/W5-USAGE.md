# Hướng dẫn sử dụng module Tuần 5 — kouun-rokku (KR)

Tài liệu hướng dẫn lập trình và sử dụng các module Tuần 5: bộ phát hiện dừng bước `HoldDetector`, bộ điều khiển truy bám `PursuitController`, bộ điều khiển dừng canh gác `HoldController`, bộ theo dõi `third_party/bytetrack/`, và công cụ mô phỏng kín `tools.sim_pursuit_hold`.

---

## 1. Sử dụng HoldDetector (Nhận diện dừng bước có bù trừ chuyển động robot)

Module: `sentry.nav.hold_detector`

```python
from sentry.nav.hold_detector import HoldConfig, HoldDetector

# Khởi tạo detector từ config.toml [hold]
cfg = HoldConfig.from_toml()
detector = HoldDetector(cfg)

# Cập nhật trong vòng lặp điều khiển (30 - 50 Hz):
# robot_pose: (x_r, y_r, theta_r) hoặc sentry.nav.localization.RobotPose
# target_local_pos: (forward_m, left_m) từ CameraGeometry.ground_point
state = detector.update(t=current_time_s, robot_pose=pose, target_local_pos=(fwd_m, left_m))

print(f"Vận tốc mặt sàn: {state.speed_mps:.3f} m/s (vx={state.vx_mps:.3f}, vy={state.vy_mps:.3f})")
print(f"Đang ở trạng thái HOLD: {state.in_hold}")

if state.event == "TARGET_STATIONARY":
    print("Mục tiêu đã dừng bước > 2.0 s -> Chuyển sang HOLD!")
elif state.event == "TARGET_MOVING":
    print("Mục tiêu bước tiếp > 0.2 m/s -> Thoát HOLD, trở lại PURSUE!")
```

### Các nguyên tắc quan trọng:
- Luôn truyền đúng pose robot $(x_r, y_r, \theta_r)$. Nếu robot tự xoay thân tại chỗ với $\omega = 1,5\text{ rad/s}$, thuật toán tự động bù trừ góc xoay $\theta_r$ để không sinh ra vận tốc giả.
- Dải trễ $[0,1; 0,2]\text{ m/s}$ chống giật trạng thái: khi đang trong `HOLD`, mục tiêu phải vượt quá $0,2\text{ m/s}$ mới kích hoạt trở lại `PURSUE`.
- Khi chuyển đổi mục tiêu mới hoặc reset luồng video, gọi `detector.reset()` để xóa lịch sử vận tốc.

---

## 2. Sử dụng PursuitController & HoldController

Module: `sentry.nav.controllers`

```python
from sentry.nav.controllers import (
    InterceptionController,
    PursuitConfig,
    HoldBehaviorConfig,
)

# Khởi tạo bộ điều phối tích hợp Phase 3
controller = InterceptionController(
    pursuit_cfg=PursuitConfig.from_toml(),
    hold_behavior_cfg=HoldBehaviorConfig.from_toml(),
)

# Trong mỗi nhịp điều khiển:
# yaw_err: góc phương vị bearing (rad, dương về bên trái) hoặc độ lệch tâm chuẩn hóa
# obs_dist_m: khoảng cách tới vật cản sàn nhà gần nhất (nếu có)
out = controller.step(
    t=current_time_s,
    robot_pose=(x, y, theta),
    target_local_pos=(fwd_m, left_m),
    yaw_err=bearing_rad,
    obstacle_dist_m=obs_dist_m,
    obstacle_bearing_rad=obs_bearing_rad,
)

# Gửi lệnh trực tiếp sang robot hoặc mô phỏng:
print(f"Chế độ hiện tại: {out.mode}")  # 'PURSUIT' hoặc 'HOLD'
print(f"Lệnh động cơ: v={out.v:.3f}, w={out.w:.3f}")
print(f"Đã căn giữa tâm: {out.is_centered}, Né vật cản: {out.obstacle_override}")
```

### Các ràng buộc:
- Trong chế độ `HOLD`: vận tốc dài $v = 0,0$ tuyệt đối. Robot chỉ dùng $w$ để xoay thân tại chỗ căn giữa bbox, không bay vòng quanh mục tiêu (no orbit).
- Khi vật cản $d_{\text{obs}} < 0,5\text{ m}$: tự động bẻ lái né ngược hướng vật cản. Nếu $d_{\text{obs}} < 0,35\text{ m}$, vận tốc tiến bị khóa $v \le 0$.

---

## 3. Sử dụng Vendored ByteTrack trên Python 3.6 (Jetson Nano)

Module: `third_party.bytetrack`

```python
import numpy as np
from third_party.bytetrack import BYTETracker

# Khởi tạo tracker thuần NumPy/SciPy (tương thích Python 3.6, không cần lap)
tracker = BYTETracker({
    "track_high_thresh": 0.25,
    "track_low_thresh": 0.10,
    "new_track_thresh": 0.25,
    "match_thresh": 0.80,
    "track_buffer": 30,
    "fuse_score": True,
})

# Detections: Nx6 array [[x1, y1, x2, y2, score, class_id], ...]
detections = np.array([
    [100.0, 50.0, 160.0, 180.0, 0.92, 0],
    [220.0, 60.0, 270.0, 190.0, 0.85, 0],
], dtype=np.float32)

# Cập nhật và nhận mảng kết quả 8 phần tử:
# [x1, y1, x2, y2, track_id, score, cls, idx]
observed_tracks = tracker.update(detections)

for row in observed_tracks:
    bbox = row[:4]
    track_id = int(row[4])
    score = row[5]
    print(f"Track ID {track_id} tại {bbox} (score={score:.2f})")
```

---

## 4. Chạy các công cụ đánh giá số liệu & kiểm thử

```bash
# 1. Chạy mô phỏng kín Pursuit & Standoff Hold (50 Hz):
python3 -m tools.sim_pursuit_hold --out reports/kouun-rokku/week-05/sim_pursuit_hold.json

# 2. Đánh giá tính nhất quán ID giữa Vendored ByteTrack và Ultralytics:
python3 -m tools.evaluate_bytetrack_parity --out reports/kouun-rokku/week-05/bytetrack_parity.json

# 3. Đánh giá chỉ số độ trễ và bất biến xoay của HoldDetector:
python3 -m tools.evaluate_hold_detector --out reports/kouun-rokku/week-05/hold_detector_metrics.json

# 4. Xuất các đồ thị F12, F15, F16:
python3 -m tools.plot_f12_entrance
python3 -m tools.plot_f15_localization
python3 -m tools.plot_f16_state_machine

# 5. Chạy toàn bộ test suites tầng T0:
pytest tests/test_hold_detector.py tests/test_controllers.py tests/test_bytetrack_vendored.py tests/test_pursuit_hold_sim.py
```
