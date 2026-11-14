# Phân tích log, overlay và nhịp Phase 2 — 14/11/2026

HNHL phân tích lại ba lượt đã lưu và kiểm tra bản sửa bằng model CUDA thật trên RTX 5060 Laptop. Kết quả pilot nhận diện trước đây giữ nguyên phiên bản code và phạm vi dữ liệu của từng lượt.

## Segment thiếu bằng chứng

| Lượt đã lưu | Quan sát có trong log | Kết luận được hỗ trợ |
| :-- | :-- | :-- |
| P01 đầu, live 2 | 21 unresolved, 2 interrupted, toàn bộ segment có 0 mẫu được giữ | Thiếu mẫu hợp lệ. Lượt này thiếu overlay và diagnostics từng frame, nguyên nhân chưa xác định |
| P01 pilot | 2 unresolved, mỗi segment giữ 2 mẫu. Một interrupted trùng khoảng ngắt xử lý 2,742 s đầu lượt | Hai segment chưa đủ top-K=3. Các mẫu đã giữ có mặt trong overlay, còn thiếu lý do loại từng frame khác |
| Người chưa enrol pilot | 3 unresolved giữ lần lượt 1, 1 và 0 mẫu | Các segment này thiếu bằng chứng. Hai segment đầu dùng cùng track key với một segment queued về sau, cho thấy ranh giới segment tự động cần đối chiếu với lượt đi qua thực tế |

P01 pilot có thêm hai khoảng ngắt giữa frame đã xử lý dài 1,752 và 1,675 s. Lượt impostor có khoảng ngắt đầu 1,715 s. Hai receiver đều ghi 0 reconnect. Log cũ thiếu thời gian từng bước nên chưa thể xác định riêng phần đóng góp của inference, lịch chạy và transport trong từng khoảng ngắt lịch sử.

Overlay cho thấy mặt và thân trên, với bbox người chạm mép ảnh ở một mẫu P01. Body visibility và độ ổn định person tracking cần được đo thêm. Người thao tác đã xác nhận camera hướng ra cửa ở live 2. Ảnh hướng trần được chụp sau lượt đó và nhận định gán góc trần cho toàn lượt đã được rút lại.

Nguồn tổng hợp có hash ở [P01 đầu](p01-first.json), [P01 pilot](p01-pilot.json) và [impostor pilot](impostor-pilot.json). Những trường diagnostics chưa có trong log cũ được giữ là null hoặc chưa ghi nhận.

## Sửa lịch và khởi tạo model

Lịch cũ đặt deadline tiếp theo bằng timestamp frame vừa xử lý cộng 0,2 s. Với nguồn 12 Hz, mỗi lượt phải chờ tới frame thứ ba, làm deadline trôi thành khoảng 0,25 s. Bản sửa giữ pha deadline ban đầu, bỏ các slot đã lỡ và chỉ xử lý frame mới nhất. Kiểm thử nguồn 12 Hz trong 10 giây cho 50 frame được xử lý, 70 frame bỏ theo lịch.

CLI thực hiện 5 vòng warm-up trên đầu vào tổng hợp trước khi mở stream, gồm YOLO/tracking, OSNet, face detection và recognition. Tracker được reset sau warm-up, các đầu vào tổng hợp được loại khỏi entry/counter và có metadata riêng. Warm-up trong phép đo sau sửa mất 2,045 s.

Đã bổ sung `--diagnostics` để ghi `frames.jsonl` riêng dưới data, gồm thời gian wall-clock của tracking/OSNet, face, entry và render/write callback, cùng số lần ghép thất bại hoặc loại mẫu. Entry log ghi tổng mẫu hợp lệ trước các lần reset xác nhận, số reset, lý do loại và trigger kết thúc. Các ngưỡng confidence, width, sharpness, N/M và majority vote tiếp tục lấy từ cấu hình hiện có.

## Đo kiểm soát với CUDA thật

Một JPEG D2 riêng được phát lặp qua HTTP MJPEG localhost 12 Hz. Mỗi bản chạy trong process mới, 20 giây, dùng cùng ảnh, config, weights và whitelist. Baseline dùng `DoorMonitor` tại commit `df513f3`, warm-up tắt. Bản sau dùng lịch mới và warm-up. Phép so sánh đo đồng thời hai thay đổi.

| Chỉ số | Baseline | Bản sửa |
| :-- | --: | --: |
| Frame nguồn decode | 240 | 240 |
| Frame được xử lý | 70 | 100 |
| Thời gian loop | 20,026 s | 20,021 s |
| FPS theo thời gian loop | 3,495 | 4,995 |
| Reconnect | 0 | 0 |
| Segment interrupted | 2 | 0 |

Các bước sau sửa có wall time như sau.

| Bước | p50 | p95 |
| :-- | --: | --: |
| Tracking + OSNet | 27,80 ms | 51,78 ms |
| Face | 18,93 ms | 24,91 ms |
| Xử lý entry | 0,047 ms | 0,056 ms |
| Toàn bộ process | 49,02 ms | 73,89 ms |

Khoảng cách frame được xử lý có p95 0,253 s và max 0,254 s, không có khoảng ngắt quá 1 s trong lần đo sau sửa. Diagnostics trên JPEG cố định ghi các lần face confidence thấp và thiếu face/person association. Các con số này thuộc đầu vào benchmark, còn nguyên nhân từng frame của pilot lịch sử cần dữ liệu chi tiết hơn.

Đây là kiểm chứng runtime với transport tổng hợp và model thật, một lần cho mỗi bản, ảnh tĩnh lặp và power/thermal chưa kiểm soát. T1 accuracy, coverage pilot và số liệu Wi-Fi cũ có phạm vi riêng. [So sánh và provenance](cadence_comparison.json), [baseline](profile-before.json), [bản sửa](profile-after.json).

Lần thử ESP32 Wi-Fi đầu sau sửa trong 20,53 s nhận 0 frame, có 6 lần reconnect; IP cũ timeout và discovery chưa tìm thấy ESP32. Sau khi người thao tác bật/kết nối lại camera, lượt tiếp theo **nhận/decode 375 frame, xử lý 149 frame trong 30,024 s, đạt 4,963 FPS theo toàn thời gian loop, 0 reconnect**. Nhịp giữa các frame xử lý đạt 4,999 Hz; khoảng frame p95 0,274 s, max 0,364 s. Process wall p50/p95 26,156/35,121 ms.

Lượt Wi-Fi sau là cảnh trống, không thấy person/face và không có quyết định. Máy đồng thời chạy CPU regression; đây là runtime smoke với tải nền đó, chưa đo lại nhận diện người sau sửa. Giữ nguyên lần thử camera mất kết nối để truy vết. [Tổng hợp Wi-Fi sau kết nối lại](wifi-reconnected.json) có hash nguồn và tất cả bộ đếm; không gửi motor commands.

## Tái lập và kiểm thử

Chạy từ repo root với weights và whitelist local. [Script đo localhost](profile_localhost.py) cần JPEG D2 và whitelist P01 riêng của phiên này. Chọn output root mới để giữ nguyên phép đo đã lưu.

```powershell
$env:YOLO_CONFIG_DIR = Join-Path (Get-Location) 'data/ultralytics'
$env:YOLO_AUTOINSTALL = 'false'
.venv/Scripts/python.exe reports/HuynhNguyenHoaiLoc/week-07/analysis-2026-11-14/profile_localhost.py before --out-root data/phase2-profile-rerun
.venv/Scripts/python.exe reports/HuynhNguyenHoaiLoc/week-07/analysis-2026-11-14/profile_localhost.py after --out-root data/phase2-profile-rerun
.venv/Scripts/python.exe -m tools.monitor_door --url http://ESP32_IP:81/stream --whitelist data/door-whitelist-1114 --out-dir data/phase2/diagnostic-run --seconds 60 --diagnostics
.venv/Scripts/python.exe -m tools.analyse_door_run --run-dir data/phase2/diagnostic-run --out data/phase2/diagnostic-analysis.json
```

Sau khi bổ sung counter person-confirmed/unresolved và tích hợp main (#101/#117/#120), full CPU/replay regression đạt **801 passed, 2 skipped, 4 GPU deselected, 56,44 s** ngày 15/11 giờ Bangkok. Hai skip vẫn cần checkerboard và D1 entrance. Kiểm thử gồm deadline không trôi, bỏ slot lỡ, warm-up không sinh entry, lý do loại mẫu, tổng mẫu qua reset, diagnostics CLI, person được xác nhận nhưng không có face và giữ trạng thái chưa biết khi log lịch sử thiếu. [CPU log cuối](tests_cpu.txt).

Bộ trọng tâm trước phần counter/integration đạt **56 passed, 2,14 s**; [log lịch sử](tests_targeted.txt). Lượt trọng tâm bổ sung counter đạt 39 passed trong 6,58 s trước full regression cuối. Log cũ được giữ đúng phạm vi phiên bản, không thay số liệu đo model bằng kết quả unit test.
