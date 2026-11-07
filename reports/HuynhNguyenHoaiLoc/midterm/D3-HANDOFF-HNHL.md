# Dữ liệu cần bàn giao cho HNHL sau buổi 04/11 và 09/11

**Cập nhật 06/11:** DQK báo camera đã sửa; kiểm tra lại stream/socket và đo self-pose/height trước quay. Chưa có recording D3 mới trong lần cập nhật. Dùng `python -m tools.prepare_d3_recording --recording data/D3/<session> --out-dir data/D3/<session>/prepared` để xuất manifest từ `jetbot_meta.jsonl`; chỉ dùng khi có `READY.json`, giữ folder recording gốc cùng manifests. `truth-template.json` là template objects rỗng, `reviewed=false`, phải gán nhãn thật và lưu `truth.json` trước evaluator. Các epoch restart đánh giá riêng. [Quy trình và giới hạn](update-2026-11-06.md).

Đây là protocol thu thập/bàn giao; chưa có D3 thật hoặc nhãn mới được xác nhận trong hồ sơ này. Nguồn lịch: [checklist tại nhà 04/11](../../../docs/Home%20Session%20Checklist%202026-11-04.md), [công việc lớp học tuần 6](../../../docs/Classroom%20Tasks%20Week%206.md). Phân công quay vẫn theo nhóm; tài liệu này không thay consent hoặc ghi nhận ai đã tham dự.

## 1. Tracking D3 khác với gallery re-ID

- Quay bằng camera JetBot, ưu tiên clip 65–90s để khoảng từ timestamp đầu tới cuối ≥60s. Cảnh ≥2 người gồm đi, dừng, giao nhau, che khuất rồi xuất hiện lại. Giữ mọi frame, kể cả empty, cùng seq và capture timestamps; không thay bằng uniform timestamps xấp xỉ hoặc clip ESP32 D2.
- Nhãn tracking: bbox xyxy theo pixel raw frame, cùng identity qua các lần che khuất, reviewed visibility. Fully occluded không xuất bbox; khi thấy lại giữ ID cũ. Gán nhãn cả distractors. Session restart tạo manifest riêng; không nối timestamp lùi vào cùng run.
- Gallery/query re-ID: ≥5 identities để chấm rank-1≥85%; tách entry/session theo protocol trước khi xem scores, không đặt cùng crop/frame vào cả gallery và query. Với ba thành viên chỉ báo pilot. Dùng cùng architecture, weights hash và preprocessing giữa target reference và tracker; OSNet-AIN và x0.25 là hai embedding spaces khác nhau.
- Log ground-truth target identity và thời điểm target được chọn/mất/khóa lại riêng nếu muốn chấm re-lock. ID-switch thấp không tự chứng minh target lock đúng người.

## 2. Gói dữ liệu private

Đặt dưới `data/D3/<session>/`, không commit raw frames, crops, embeddings hoặc predictions:

```text
README.md             room/floor, camera/mount/pose, people code, consent, actions, timestamps, raw hashes
frames/               ảnh raw JetBot giữ nguyên
frames.json           manifest replay {frames: [{t, image}, ...]}
truth.json            nhãn tracking đã review, đầy đủ mọi frame
annotations/          visibility/target-event notes, reviewer và phiên bản nhãn
reid/                 gallery/query manifests và crops được phép dùng
```

Ví dụ schema bên dưới chỉ có hai frame minh họa, không phải dữ liệu đo và không đủ T1. `reviewed=false` chỉ đổi thành true sau khi HNHL kiểm tra nhãn thật.

```json
{
  "kind": "D3_TRACKING",
  "camera": "jetbot",
  "reviewed": false,
  "frames": [
    {"t": 0.0, "objects": [{"id": "p1", "xyxy": [100, 30, 160, 420]}]},
    {"t": 0.05, "objects": []}
  ]
}
```

`frames.json` dùng đúng các timestamp này và đường dẫn ảnh tương đối. Mọi decoded frame phải xuất hiện ở cả manifest, truth và predictions. `tools.prepare_d3_recording` xuất các `prepared/epoch-NNN/frames.json` trỏ về JPEG gốc, không đổi tên CSV thành JSON hoặc thay timestamp bằng FPS xấp xỉ. Giữ source recording nguyên vẹn.

## 3. Chạy khi dữ liệu thật đã sẵn sàng

```powershell
.venv/Scripts/python.exe -m tools.track_replay --manifest data/D3/<session>/frames.json --out data/D3/<session>/predictions.json
.venv/Scripts/python.exe -m tools.evaluate_tracking --truth data/D3/<session>/truth.json --predictions data/D3/<session>/predictions.json --out reports/HuynhNguyenHoaiLoc/week-05/d3_<session>_metrics.json
```

Replay không target chỉ kiểm tra tracking. Muốn lock một target thật, thêm `--target data/D3/<session>/target.npz` theo [W5-USAGE](../W5-USAGE.md), có `vector` và scalar `model_id` đúng hash; không tự chọn reference từ người được detector nhìn thấy đầu tiên. CLI hiện dùng một reference cho cả clip; event-driven handoff dùng API.

Evaluator báo switch/min, matches/misses/FP, recall, protocol completeness và `switch_limit_met`. `t1_passed` còn có guard bảo thủ không miss/FP; phải đọc cả các trường này, không chỉ exit code. Chưa có evaluator target-lock accuracy tự động; giữ truth/events để review riêng. Chỉ commit aggregate metrics và source hashes, không person IDs/boxes/private predictions.

## 4. D5 và GPU cần kèm theo

- D5 mới: ghi room/floor/session/distance và empty-floor negatives. Matte bổ sung floor control; một glossy session độc lập vẫn hữu ích nhưng không thay matte comparison. Freeze held-out trước selection. Legs, footwear, backpacks **và bags**: R≥90%, P≥80%; wire R≥80% và ≤1 false alarm/20 empty frames. Distance/T2 gates giữ nguyên trong plan.
- RTX4050: ghi power source/limits/clock/runtime, same inputs, model hashes, workload và actual cadence; đo combined budget. FP32/FP16 phải kèm accuracy trên cùng evaluation split; cosine conversion không thay rank-1 hoặc detector accuracy.
- Sau 04/11/09/11: đối chiếu gói với protocol, review labels rồi chạy; cập nhật F14/F18 chỉ khi có phép đo hợp lệ. Nếu chưa có dữ liệu, giữ status pending trong báo cáo. Không sửa số đo cũ hoặc lấy mô phỏng làm T1/T2.
