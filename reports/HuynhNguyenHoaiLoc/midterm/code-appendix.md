# Phụ lục code HNHL cho báo cáo giữa kỳ

Đây là phần HNHL đưa cho KR ghép phụ lục chung. Tag `midterm` và link demo chỉ điền sau khi nhóm chốt; chưa tạo tag trong phiên này. Theo kế hoạch, phụ lục tính trong giới hạn10–15 trang nên cần rút gọn bảng dưới khi ghép.

| Module hoặc tool | Chức năng | Kiểm chứng liên quan |
| :-- | :-- | :-- |
| `sentry/net/zmq_rx.py`, `clock_sync.py`, `latency.py` | Latest multipart video, clock offset, telemetry | W1 unit/localhost evidence; phân biệt HIL |
| `sentry/perception/obstacle.py`, `camera.py`, `floor.py`, `world.py` | Vật cản, projection/contact; optional semantic/world backends | W2 tests, issue43 metrics và GPU runtime |
| `sentry/nav/gridmap.py`, `vantage.py` | Occupancy, reachability, clearance/LOS và vị trí quan sát | Synthetic/unit tests; real map/T2 còn chờ |
| `sentry/perception/face.py`, `tools/enroll_whitelist.py` | Face embedding và whitelist max cosine | T0; D2 pilot E03 chưa nghiệm thu |
| `sentry/perception/reid.py` | Local OSNet và PersonReID, model/hash provenance | W4 GPU tests và runtime smoke |
| `sentry/perception/tracker.py` | ByteTrack + appearance lock/re-lock, epoch reset | `tests/test_tracker.py`, `test_tracker_gpu.py` |
| `tools/track_live.py`, `track_replay.py`, `evaluate_tracking.py` | Receive-only video/replay và D3 metrics | E04; evaluator synthetic tests, real D3 còn chờ |
| `tools/profile_pipeline.py` | Resident model workload, NVML memory và actual door Hz | E05–E07, profiler unit tests |
| `tools/compare_d5_precision.py` | FP32/FP16 CUDA process riêng, accuracy cùng nhãn, dtype checks; giữ dataset gốc | F18/N05, test input/timing guards; chưa TensorRT/HIL |
| `tools/build_midterm_hnhl_followup.py` | Addendum 05/11, F18 và nguồn plan theo commit | N01–N11; checker xác minh hashes, snapshot và nghiệm thu còn thiếu |
| `tools/train_d5.py`, `freeze_d5.py`, `check_d5_onnx.py` | Train/export/freeze/parity development candidate | E02/E08; artifacts local |
| `tools/build_midterm_hnhl.py`, `export_midterm_hnhl_doc.py` | Tạo lại hình, evidence snapshot và Chương5 | Kiểm tra source hashes, số liệu và render Word |
| `tools/build_midterm_hnhl_update.py`, `check_midterm_hnhl.py` | Phụ lục 03/11, F9 single-model và kiểm tra metadata/links/Word hash | Không inference; giữ các nghiệm thu còn thiếu ở trạng thái chưa đo |

## Môi trường và lệnh kiểm tra

Laptop HNHL: repo-local `.venv`, Python3.12; versions/hashes cụ thể tại `week-05/environment.json`. `common/` và `jetson/` giữ Python3.6; không chạy laptop dependencies trên Nano. Cài theo `docs/Setup.md`; không thay torch CUDA bằng wheel CPU.

```powershell
$env:YOLO_CONFIG_DIR = Join-Path (Get-Location) 'data/ultralytics'
$env:YOLO_AUTOINSTALL = 'false'
.venv/Scripts/python.exe tools/check_env.py
.venv/Scripts/python.exe -m pytest -m 'not gpu and not hil' --basetemp=data/pytest-midterm-clean -p no:cacheprovider -q -rs
.venv/Scripts/python.exe -m pytest -m gpu --basetemp=data/pytest-midterm-gpu -p no:cacheprovider -q -rs
```

Các lệnh trên là hướng dẫn; chưa có clean-checkout tag-midterm run. Logs E11/E12 là release W5 hiện có. Clean checkout chung do KR chủ trì trước tag21/11, tất cả thành viên kiểm tra số liệu thuộc phần mình.

## Handoff Phase2 sang tracker

```python
from sentry.perception.tracker import PersonTracker
tracker = PersonTracker.from_config()
if queue.active_target is not None:
    tracker.set_target_record(queue.active_target)
result = tracker(frame.frame_bgr, frame.t_cap)
```

Record phải có appearance thật, model/hash khớp; target None khi chưa khóa hoặc mất dấu. Caller quyết định control/event; tracker không gửi motor commands. Gallery/crops/predictions giữ trong `data/`, không nằm trong appendix hoặc public figures. Lệnh reproduction chi tiết: `W2-USAGE.md`, `W4-USAGE.md`, `W5-USAGE.md` ở thư mục HNHL.
