# Phase 2 live — HNHL, issue #114

`tools.monitor_door` nhận HTTP MJPEG từ ESP32 bằng một reader, chạy person tracking và face theo lịch 5 Hz, phân đoạn entry, quyết định whitelist và dùng `Phase2Pipeline` để đưa người chưa được chấp nhận vào queue. Cấu hình nằm trong `[door_live]`, `[reid]`, `[thresholds]` và `[sector]` của `config.toml`.

## Chạy trên laptop

Chuẩn bị weights YOLO, OSNet và hai file `det_500m.onnx` / `w600k_mbf.onnx` dưới `data/insightface/models/buffalo_s/`. Vòng live xác minh các file InsightFace tồn tại trước khi khởi tạo model. Whitelist dùng định dạng `.npz` có 3–5 embeddings cho mỗi ID, tương thích enrolment hiện có và `tools.enroll_guided` trong PR #108.

Enrol qua chính camera cửa bằng công cụ dưới đây. Chuẩn bị một người trong ảnh, khuôn mặt ≥80 px và làm theo năm tư thế trên preview. Chỉ khi hoàn thành đủ năm tư thế mới lưu `.npz`. Mẫu thiếu hoặc bấm Esc sẽ hủy lượt. Thông số enrol ở `[door_enrol]`. Mỗi ID dùng file mới.

```powershell
.venv/Scripts/python.exe -m tools.enroll_door --url http://ESP32_IP:81/stream --person-id P01 --out-dir data/door-whitelist --seconds 120 --display
```

Đóng reader ESP32 khác vì board chỉ phục vụ một stream client. Thay địa chỉ mẫu bằng IP Wi-Fi hiện tại của ESP32.

```powershell
$env:YOLO_CONFIG_DIR = Join-Path (Get-Location) 'data/ultralytics'
$env:YOLO_AUTOINSTALL = 'false'
.venv/Scripts/python.exe -m tools.monitor_door --url http://ESP32_IP:81/stream --whitelist data/whitelist --out-dir data/phase2/session-001 --seconds 60 --display
```

Mỗi lần chạy dùng thư mục output mới. Mặc định chỉ lưu log và provenance. `--save-snapshots` lưu crop của intruder; `--save-overlay` lưu AVI cùng `overlay_frames.jsonl`. AVI phát ở nhịp danh nghĩa 5 Hz. Index giữ thời gian nhận từng frame để kiểm tra khoảng trống. Tất cả log riêng, ảnh, embeddings và video nằm dưới `data/` được Git ignore. Chỉ đưa số liệu tổng hợp đã kiểm tra vào reports.

## Quy tắc entry và quyết định

- Một entry cần 3 lần liên tiếp có một face đủ rộng 40 px, confidence ≥0,6 và sharpness ≥25, ghép duy nhất với một person track. Sharpness dùng cùng phép đo 112×112 với D2 offline.
- Chọn 3 frame tốt nhất, ưu tiên frontal từ năm landmarks rồi confidence × width × sharpness. Hai trong ba frame phải chấp nhận cùng một whitelist ID. Ngưỡng cosine lấy từ config, hiện 0,45 và còn provisional.
- Kết thúc sau 3 mẫu được xử lý liên tiếp thiếu face hợp lệ, khi entry đã được xác nhận. Giới hạn một lượt 15 giây. Người chưa có mặt rõ có thể quay về phía camera để bắt đầu entry sau đó. Một track đã hoàn tất được giữ suppressed đến khi person biến mất đủ 3 mẫu.
- Hai person cùng chứa một face, hoặc nhiều face ghép một person, đều không cung cấp mẫu nhận diện. Chưa đủ bằng chứng thì ghi `unresolved`. Rớt stream, reconnect, sequence restart, đổi kích thước ảnh hoặc tracker epoch thì hủy entry dang dở và ghi `interrupted`.
- Lịch dựa trên timestamp frame mới. Không phát lại frame cũ để đếm N/M và không chạy bù backlog. 5 Hz là mức yêu cầu. Inference chậm có thể làm nhịp thực tế thấp hơn.

Deadline giữ pha ban đầu để tránh trôi nhịp theo thời điểm frame đến. CLI chạy warm-up theo số vòng trong `[pipeline_profile].warmup` trước khi mở stream, rồi reset tracker. Warm-up gồm đầu vào tổng hợp cho tracking/OSNet và face, được ghi metadata và loại khỏi entry/counter.
- OSNet dùng crop người nhìn thấy, ghi `crop_scope=visible_body`. Camera thấp có thể chỉ thấy đầu/ngực. DQK cần đo body visibility và team cần kiểm chứng cross-camera trước khi dùng vector này để kết luận re-ID đạt yêu cầu.

## Bàn giao cho KR

`DoorMonitor(tracker, face_encoder, pipeline, settings, emit, decision_clock=...)` cho phép inject `Phase2Pipeline` với `TargetQueue` và `StateMachine` đang dùng chung. Gọi `process(image_bgr, t, seq, reconnects)` khi có frame mới, `tick(t)` khi chờ stream và `interrupt(t, reason)` khi dừng. Một processing thread sở hữu monitor và thao tác pipeline. Dùng cùng clock domain với state machine.

Pipeline nhận thêm `face_embeddings`, `minimum_face_votes`, `decision_timestamp`, `decision_clock` và `entry_metadata` dưới dạng keyword. Callers dùng một `face_embedding` vẫn hoạt động. `record.timestamp` giữ lúc bắt đầu entry; `enqueued_at` và thời gian event lấy ngay trước enqueue sau appearance inference. Log tính `latency_s` từ face đầu tiên đến mốc quyết định đó. Với MJPEG, đây là thời gian theo clock nhận của laptop. ESP32 chưa gửi capture timestamp.

CLI có queue/state machine trong process của nó. Ứng dụng tổng cần inject cùng các object để KR nhận active target và gọi tracker `set_target_record`. Phase3Runner từ PR #101 đã merge vào main ngày 15/11 giờ Bangkok. Vòng camera này không kết nối transport điều khiển motor. Tích hợp `sync_with` và `TRACK_LOST` còn chờ #119 được merge.

## Replay và chấm kết quả

Replay nhận JSON riêng dưới `data/` với `camera="esp32"`, `timestamp_source` và danh sách `frames`. Mỗi frame có `t`, `seq`, `image`, `image_sha256`. Timestamp/sequence phải tăng. Split thành manifest riêng khi stream restart. Mọi ảnh và hash được kiểm tra trước khi tạo output.

```powershell
.venv/Scripts/python.exe -m tools.monitor_door --replay-manifest data/door-session/frames.json --whitelist data/whitelist --out-dir data/phase2/replay-001
.venv/Scripts/python.exe -m tools.evaluate_door_entries --entries data/phase2/session-001/entries.jsonl --truth data/phase2/session-001/truth.json --out reports/HuynhNguyenHoaiLoc/week-07/door-session-001.json
```

Truth do người review tạo có `camera="esp32"`, `reviewed=true`, `entries=[...]`. Mỗi entry có `entry_id`, `enrolled` boolean và `identity` nếu đã enrol. Ghi cả lượt mong đợi bị bỏ lỡ bằng một ID riêng trong truth. Tool từ chối ID trùng và log chưa có nhãn. TAR chia trên tất cả lượt enrolled. FAR chia trên impostor đã có quyết định authorized/queued, đồng thời ghi `far_all_attempts`, coverage, missing và unresolved. Khi chưa có impostor được quyết định, FAR là null. Kết quả ghi rõ đơn vị entry và không tự chọn ngưỡng hay bật T1 PASS.

T1 cần người đã enrol được authorized, người để ngoài whitelist được queued, có nhãn danh tính đã kiểm tra và latency từng lượt. Tách dữ liệu chọn ngưỡng với dữ liệu kiểm chứng. DQK cung cấp tower/stream, body-visibility và buổi cửa ba người. KR phối hợp queue/Phase 3. Trạng thái được cập nhật ở [báo cáo tuần 7](week-07.md).

## Phân tích runtime và mẫu bị loại

Bật `--diagnostics` để lưu `frames.jsonl` riêng trong run directory. Mỗi frame đã xử lý có wall time của tracking/OSNet, face, entry và callback, cùng các bộ đếm lỗi association/quality. Entry log giữ tổng mẫu hợp lệ qua các lần reset xác nhận, các lý do loại và trigger kết thúc.

Summary có `confirmed_unresolved`: số segment unresolved đã thấy cùng person track đủ N frame liên tiếp (`person_confirmed`). Trường `confirmed` trong entry vẫn chỉ việc xác nhận bằng face hợp lệ. Hai bộ đếm tách biệt để thấy người không có mặt dùng được; không thay đổi chính sách unresolved/no-queue. Log lịch sử chưa có các trường này không được mặc định là 0. [Quyết định ngưỡng và giới hạn dữ liệu](week-07/threshold-118-2026-11-15/README.md).

```powershell
.venv/Scripts/python.exe -m tools.analyse_door_run --run-dir data/phase2/session-001 --out data/phase2/session-001-analysis.json
```

Công cụ đọc được log cũ và giữ các diagnostics thiếu là chưa biết. Khoảng cách giữa frame đã xử lý tự nó chưa xác định nguyên nhân mạng hoặc inference. [Phân tích và phép đo kiểm soát](week-07/analysis-2026-11-14/README.md).
