# HNHL — Phase 2 live và cập nhật perception

Triển khai ngày 14/11/2026, Asia/Bangkok, theo issue #114 và snapshot #111. Nhánh `HuynhNguyenHoaiLoc/w07-phase2-live`, base `4f80eac`. Phần camera đến queue có code, kiểm thử và chạy runtime thật. Nghiệm thu người vào cửa vẫn cần lượt có nhãn cùng ngưỡng/crop đã kiểm chứng.

`DoorMonitor` tái sử dụng face, person tracking, OSNet, sector và `Phase2Pipeline`. Vòng xử lý dùng một MJPEG reader, lịch 5 Hz, xác nhận N/M, top-K face cùng đa số whitelist, suppression theo track, xử lý ambiguity và ngắt phiên khi stream gián đoạn. `tools.enroll_door` bổ sung enrol năm tư thế trên chính ESP32; `tools.evaluate_door_entries` chấm các lượt đã review và giữ missing/unresolved. Log/ảnh/video riêng nằm trong `data/`. Snapshot và overlay cần bật flag.

Pipeline giữ API một embedding cho callers cũ và thêm API nhiều mẫu, thời gian enqueue thực tế sau inference và provenance. Face encoder cung cấp năm landmarks, tương thích dữ liệu thiếu landmarks. Phép đo sharpness D2 và hàm ghép face/person được dùng chung. Evaluator D2 lấy session từ thư mục input để tránh nhãn cố định `1028` trên dữ liệu mới.

## Kiểm chứng

Full CPU/replay selection đã đạt **762 passed, 2 skipped, 4 GPU deselected, 52,08 s** sau phần monitor/scorer. Hai ca skip cần checkerboard và D1 entrance chưa có trên máy. Kiểm thử targeted sau bổ sung enrol đạt **46 passed, 3,65 s**. Các ca gồm quyết định đa số cùng ID, chọn frontal, ambiguity, nhiều người, timeout/reconnect/reset/resize, queue một lần, thời gian sau OSNet, ESP32 down, cleanup, replay hash/path, giữ output cũ, nhãn thiếu và năm tư thế enrol.

```powershell
$env:YOLO_CONFIG_DIR = Join-Path (Get-Location) 'data/ultralytics'
$env:YOLO_AUTOINSTALL = 'false'
.venv/Scripts/python.exe -m pytest -m 'not gpu and not hil' --basetemp=data/pytest-phase2-final-1114 -p no:cacheprovider -q -rs
.venv/Scripts/python.exe -m pytest tests/test_enroll_door.py tests/test_phase2_live.py tests/test_phase2_reid.py tests/test_phase2_replay.py tests/test_face.py tests/test_d2_pilot.py -p no:cacheprovider -q
```

Runtime với model thật dùng **RTX 5060 Laptop**, OSNet `cuda:0`, InsightFace detection/recognition có CUDAExecutionProvider đứng đầu. Hai lần chạy dưới đây có phạm vi riêng.

| Lần chạy | Kết quả | Phạm vi |
| :-- | :-- | :-- |
| Replay 298 ảnh D2 cafe có sẵn | 17 frame được xử lý, 281 bỏ theo lịch. 4 unresolved, mỗi lượt 0 face hợp lệ. 0 queued | Timestamp chia đều xấp xỉ từ clip 3,4 s. Whitelist lấy từ hai subject khác. Runtime smoke |
| Live ESP32 qua Wi-Fi 30 s | 100 frame được xử lý, 183 bỏ theo lịch. 0 entry | Dùng whitelist local hiện có, thiếu nhãn người/điều kiện thử |
| Probe receiver 10,06 s trước live | 27 frame, 640×480, khoảng 2,69 FPS, 3 reconnect | Timeout probe 1 s. Khác cấu hình receiver 2 s của vòng live |

Replay tạo được AVI overlay 17 frame ở nhịp phát danh nghĩa 5 Hz, có index timestamp và đã kiểm tra một frame preview. File là overlay của replay, cần quay màn hình laptop trong buổi demo để hoàn thiện item video. Frame cafe mờ và chưa có face đủ điều kiện nên các lượt unresolved được giữ rõ trong báo cáo.

Thử live xác nhận truy cập được ESP32 và thực thi model/vòng lặp. 0 entry chưa cung cấp TAR/FAR hay độ trễ enqueue thực nghiệm. Log riêng ở `data/phase2-live-2026-11-14/`, replay ở `data/phase2-smoke-2026-11-14/`. Chương trình không kết nối transport motor. Timestamp latency lấy clock nhận trên laptop vì MJPEG chưa có capture clock từ camera.

## Nghiệm thu và phối hợp

- Cần enrol đúng người và ghi các lượt genuine/impostor trước camera. Mỗi lượt có truth được review, quyết định và latency. Ngưỡng 0,45/top-K hiện provisional.
- DQK cần đo body visibility tại ba mốc. Crop `visible_body` có thể chỉ có phần trên thân, còn cần kiểm chứng cross-camera với view robot.
- KR inject queue và state machine dùng chung vào pipeline của monitor. CLI tự chứa queue trong process. Phase3Runner nằm trong PR #101 cần được review/tích hợp theo giao diện nhóm.
- D3 reviewed ≥60 s, hai người và gallery ≥5 identities, D5 độc lập/per-class, F11 world truth, F7 raw latency và full robot T2 còn chờ dữ liệu/robot.

Số đo workload RTX 4050 của DQK đã được đối chiếu và bổ sung ở [audit issue](issues-111-114-2026-11-14.md). Hướng dẫn chạy, định dạng manifest/truth và API ở [PHASE2-LIVE-USAGE.md](PHASE2-LIVE-USAGE.md).

B?ng ch?ng t?ng h?p ? [runtime_summary.json](week-07/runtime_summary.json), [CPU log](week-07/tests_cpu.txt) v? [targeted log](week-07/tests_targeted.txt). Embeddings P01 ? `data/door-whitelist-1114/P01.npz` ch? l?u local. L??t enrol ??u 2/5 timeout, l??t th? l?i v?i feedback c? th? ?? ho?n th?nh 5/5.
