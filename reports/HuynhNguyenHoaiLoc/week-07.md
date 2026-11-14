# HNHL — Phase 2 live và cập nhật perception

Kiểm chứng ngày 14/11/2026, Asia/Bangkok, theo issue #114 và snapshot #111. Nhánh `HuynhNguyenHoaiLoc/w07-phase2-live`, base `4f80eac`, code `058c978`. Sau khi enrol P01, vòng ESP32 → face → OSNet → queue đã chạy live với người đã enrol và người chưa enrol.

## Kết quả hai lượt live kiểm chứng

Hai lượt chạy riêng, mỗi lượt khoảng 90 giây, dùng whitelist chỉ có P01 với 5 embeddings từ chính ESP32. Người dùng xác nhận lượt đầu chỉ có P01, lượt sau chỉ có người chưa enrol và thực hiện 3 lần vào–ra. Nhãn cohort dựa trên các xác nhận này. Overlay được kiểm tra về framing và bbox, chưa có bộ nhãn nối từng lần đi qua thực tế với từng segment tự động.

| Cohort | Decoded / processed | Authorized | Queued | Unresolved | Interrupted | Reconnect |
| :-- | --: | --: | --: | --: | --: | --: |
| P01 đã enrol | 1.074 / 336 | 3 | 0 | 2 | 1 | 0 |
| Người chưa enrol | 1.104 / 359 | 0 | 3 | 3 | 0 | 0 |

Mỗi cohort có 6 segment được log, trong đó 3 segment có quyết định, tức coverage theo segment là 50%. Segment tự động và lượt đi qua thực tế là hai đơn vị khác nhau. Giữ toàn bộ 5 unresolved và 1 interrupted khi báo cáo. Kết quả này là pilot hai người cùng session, còn cần mở rộng protocol và nhãn trước khi nghiệm thu T1.

Các mẫu top-K của 3 quyết định authorized có cosine 0,669–0,756. Các mẫu top-K của 3 quyết định queued có cosine 0,076–0,175, với ngưỡng provisional 0,45. Không quan sát thấy enqueue P01 hay authorized người chưa enrol trong hai lượt này. Chưa có calibration/test split độc lập để chọn ngưỡng.

Ba thời gian entry-start → enqueue là **9,387 / 9,355 / 10,245 giây**, median **9,387 giây**. Mốc tính từ frame mặt hợp lệ đầu tiên đến enqueue, bao gồm thời gian người còn trong entry và chờ entry kết thúc. Clock là thời gian nhận trên laptop vì MJPEG chưa gửi camera capture timestamp. Ba quyết định authorized mất 3,075–4,913 giây theo cùng cách đo.

Cả ba lượt người lạ phát `INTRUDER_QUEUED`. Record đầu trở thành active target, hai record tiếp theo vào FIFO, queue length sau từng event là **0 → 1 → 2**, active target vẫn là record đầu. OSNet chạy `cuda:0` và InsightFace detection/recognition có CUDAExecutionProvider đứng đầu. Máy đo là **RTX 5060 Laptop của HNHL**.

Lịch yêu cầu 5 Hz, tốc độ xử lý thực tế lần lượt khoảng 3,73 và 3,98 frame/s trong hai lượt. Đây là workload door gồm YOLO/person tracking, OSNet và face. Các phép đo combined GPU target trong #111 có protocol và nguồn riêng.

Bằng chứng tổng hợp ở [live_adjusted_2026-11-14.json](week-07/live_adjusted_2026-11-14.json) và [toàn bộ segment](week-07/live_adjusted_segments.csv). Video và timestamp index riêng ở `data/phase2-live-2026-11-14/run-p01-adjusted-01/` và `run-impostor-adjusted-01/`. Hai AVI có 336 và 359 frame, phát danh nghĩa 5 Hz. Framing hiện thấy mặt và phần thân trên, cần DQK đo body visibility và kiểm chứng vector với camera robot.

## Triển khai và kiểm thử

`DoorMonitor` dùng một MJPEG reader, lịch xử lý 5 Hz, N/M theo track, top-K ưu tiên frontal/quality, đa số cùng whitelist ID và suppression của track đã hoàn tất. Stream gián đoạn, reconnect, sequence reset, đổi kích thước và ambiguity có trạng thái log rõ. API một embedding của `Phase2Pipeline` vẫn hoạt động, API mới nhận nhiều mẫu và thời gian enqueue sau inference.

`tools.enroll_door` hướng dẫn năm tư thế trên ESP32 và lưu embeddings local. `tools.monitor_door` hỗ trợ live, replay có timestamp/hash, preview, overlay và snapshot bằng flag. `tools.evaluate_door_entries` chấm truth đã review, giữ missing/unresolved và coverage. Sharpness cùng phép ghép face/person được dùng chung với D2 offline, evaluator lấy session từ thư mục input.

Full CPU/replay selection đạt **762 passed, 2 skipped, 4 GPU deselected, 52,08 s**. Hai ca skip cần checkerboard và D1 entrance chưa có trên máy. Bộ kiểm thử trọng tâm đạt **46 passed, 3,65 s**, bao gồm đa số cùng ID, frontal, ambiguity, nhiều người, stream lỗi/reset/resize, queue một lần, timestamp sau OSNet, cleanup, replay hash/path, output protection và năm tư thế enrol.

```powershell
$env:YOLO_CONFIG_DIR = Join-Path (Get-Location) 'data/ultralytics'
$env:YOLO_AUTOINSTALL = 'false'
.venv/Scripts/python.exe -m pytest -m 'not gpu and not hil' --basetemp=data/pytest-phase2-enrol-release-1114 -p no:cacheprovider -q -rs
.venv/Scripts/python.exe -m pytest tests/test_enroll_door.py tests/test_phase2_live.py tests/test_phase2_reid.py tests/test_phase2_replay.py tests/test_face.py tests/test_d2_pilot.py -p no:cacheprovider -q
```

[CPU log](week-07/tests_cpu.txt) và [targeted log](week-07/tests_targeted.txt). Các phép chạy trước hai lượt kiểm chứng vẫn được giữ trong [runtime_summary.json](week-07/runtime_summary.json), gồm replay 298 ảnh D2 mờ với 4 unresolved, probe receiver, lượt live chưa có entry và lượt P01 đầu với 21 unresolved, 2 interrupted. Lượt enrol đầu timeout ở 2/5, lượt tiếp theo hoàn tất 5/5. Whitelist ở `data/door-whitelist-1114/P01.npz`.

Người thao tác xác nhận camera đã hướng ra cửa ở lượt live 2, tức lượt P01 đầu trong thứ tự chạy của phiên. Ảnh chẩn đoán hướng trần được chụp sau lượt đó. Nhận định trước đây gán góc hướng trần cho cả lượt chạy đã được rút lại. Log của lượt này ghi 0 mẫu mặt hợp lệ trong các segment, nhưng chưa đủ thông tin để xác định nguyên nhân thiếu bằng chứng. Các kết quả số của từng lượt được giữ nguyên.

## Trạng thái issue và phối hợp

- #114 đã có code, enrol ESP32, pilot genuine/impostor, event/queue thật và latency. Cần protocol đủ thành viên, nhãn entry/attempt đầy đủ và dữ liệu calibration độc lập để chốt ngưỡng. T1 còn mở.
- Crop `visible_body` hiện là mặt/thân trên. DQK cung cấp phép đo body visibility, camera geometry và buổi cửa nhóm. Cross-camera re-ID còn cần dữ liệu robot.
- KR inject queue và state machine dùng chung vào pipeline của monitor. CLI sở hữu queue trong process của nó. Việc ghép với Phase3Runner trong PR #101 và ứng dụng tổng cần phối hợp KR.
- #111 đã bổ sung số đo workload RTX 4050 do DQK thực hiện và đề xuất chair-width. D3 reviewed ≥60 s, hai người và gallery ≥5 identities, D5 độc lập/per-class, F11 world truth, F7 raw latency, màn hình demo và full robot T2 còn chờ.

[Audit issue #111/#114](issues-111-114-2026-11-14.md), [hướng dẫn và API](PHASE2-LIVE-USAGE.md), [PR #115](https://github.com/DoanQuocKien/Autonomous-Collaborative-Sentry-Robot/pull/115).
