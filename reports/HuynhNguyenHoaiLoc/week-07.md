# HNHL — Phase 2 live và cập nhật perception

## Chốt công việc tuần 7 ngày 21 tháng 11

Tuần 7 là **16–22/11/2026** theo mục Week 7 của [Implementation Plan](../../docs/Implementation%20Plan.md). HNHL chốt Chương 5 cùng các hình ROC, sai số khoảng cách, GPU/tối ưu và sửa lỗi còn sót tuần 5–6 qua PR. Tuần này không giao tính năng perception mới.

| Phần việc HNHL | Bàn giao |
| :-- | :-- |
| Chương 5 chốt theo bằng chứng hiện có | [Bản Chương 5 ngày 21/11](midterm/chapter-05-final-2026-11-21.md), đồng nhất số liệu với Chương 5 trong [bản ghép nhóm](../midterm_report_draft.md) |
| Hình theo nhiệm vụ | F10 error/coverage; F13 ROC cửa 14/11; F9 GPU RTX5060 với bảng RTX4050 của DQK; F18 FP32/FP16; F20 Nano của DQK, đều có nguồn/hash |
| Perception và handoff tuần 5–6 | #115/#124 đã merge: lịch 5 Hz, counters unresolved, shared queue/Phase3/target-tracker, TRACK_LOST và timestamp 0. Ngưỡng và chính sách unresolved giữ theo quyết định nhóm |
| Review, sửa lỗi và kiểm chứng | #133 đã merge; #134 bổ sung hồ sơ, checker và bản chốt tuần 7 để DQK/KR review |

Các tiêu chí chưa đạt như D3/gallery, D5 per-class/independent session, F11 và full door T1 được viết thành giới hạn và kế hoạch tiếp theo. Không dùng việc chốt Chương 5 để xác nhận các hàng T1/T2 này. Tag `midterm`, gói nộp và owner sign-off toàn nhóm theo KR/DQK ở kế hoạch nộp 23/11.

Các mục ngày cũ bên dưới là bằng chứng lịch sử của từng phiên.

**Cập nhật 21/11:** #113/#132/#133 đã merge; #114 đóng trên GitHub. Hồ sơ giữa kỳ bổ sung 38 nguồn pin cho find-door/pursuit/tower 20/11 và F7 đã có, trạng thái từng phần HNHL và checklist nộp 23/11. STANDBY 56,317 s ở một lượt find-door; hai pursuit diagnostics có distance-in-band 9,4%/18,1%, chưa đạt gate 80%. F7 raw CSV có thật nhưng chưa đạt FPS/p95. [Bổ sung hiện hành](midterm/update-2026-11-21.md), [review #133](reviews/PR-133-2026-11-21.md). Các ghi chú theo ngày bên dưới giữ trạng thái tại thời điểm đó.

**Bổ sung sau freeze 18/11** HNHL đã review/merge #130/#131, sửa freshness/battery/video-IP/obstacle-trigger và tính lại dữ liệu tower của DQK. Pursuit-e đạt tracked 67,2%, trong dải 9,2%, căn tâm 40%, có 12 lượt tránh hoàn tất và một còn active. Detector vật cản tổng quát tắt. #113 đã sửa, chờ DQK review lại. [Nguồn và phạm vi](midterm/update-2026-11-18.md), [review](reviews/2026-11-18.md).

**Cập nhật 16/11** ghi PR #124 đã merge sau review DQK. HNHL đã review/merge #125/#126/#127 và tính lại log pursuit của DQK với 32,2% thời gian trong dải cự ly, 91,1% căn tâm và 0 HOLD. Đã bổ sung deployment thứ 7, pose mới, F3/F17b và lịch video 19/11 vào phần giữa kỳ. [Nguồn và phạm vi đo](midterm/update-2026-11-16.md), [review](reviews/2026-11-16.md).

**Cập nhật tiếp 15/11:** #115 đã được DQK approve/merge; phiên này đã review và merge #108/#122/#123, đưa #116/#119/#121 vào main. HNHL bổ sung shared queue/target-tracker handoff, TRACK_LOST và giữ timestamp 0. Full regression **881 passed,2 skipped,4 GPU deselected,60,06 s**; [log](week-07/integration-2026-11-15/tests_cpu.txt), [review/issue](reviews/followup-2026-11-15.md), [Chương 5/7 mới](midterm/update-2026-11-15.md). Chưa có phép đo recognition hoặc robot mới; #114 vẫn chờ nghiệm thu đầy đủ.

**Bổ sung 15/11:** [quyết định issue #118 và ROC từ dữ liệu DQK](week-07/threshold-118-2026-11-15/README.md): giữ ngưỡng 0,45 và 2/3 mẫu cùng ID ở trạng thái tạm thời. Bổ sung `confirmed_unresolved` để audit person được xác nhận nhưng thiếu bằng chứng nhận diện. Đã review chín PR, merge #101/#117/#120; kết quả và phần còn chờ ở [audit ngày 15/11](reviews/2026-11-15.md).

**Phân tích runtime 14–15/11:** [log/overlay, sửa lịch 5 Hz, warm-up và thời gian từng bước](week-07/analysis-2026-11-14/README.md). Bản sửa xử lý 100 frame/20 giây với CUDA trên MJPEG localhost 12 Hz. Sau khi camera kết nối lại, ESP32 Wi-Fi xử lý 149/375 frame trong 30,024 giây, 4,963 FPS, 0 reconnect; cảnh trống, chỉ kiểm chứng runtime. Các kết quả pilot bên dưới giữ theo code `058c978`.

Regression snapshot đầu ngày 15/11: **801 passed, 2 skipped, 4 GPU deselected, 56,44 s**; [log](week-07/analysis-2026-11-14/tests_cpu.txt). Evidence checker lúc đó đạt 223 liên kết local và giữ hash Word đã review. Các phép đo/kiểm thử bên dưới có ngày riêng.

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

## Trạng thái issue và phối hợp tại snapshot 14 tháng 11

- #114 đã có code, enrol ESP32, pilot genuine/impostor, event/queue thật và latency. Cần protocol đủ thành viên, nhãn entry/attempt đầy đủ và dữ liệu calibration độc lập để chốt ngưỡng. T1 còn mở.
- Crop `visible_body` hiện là mặt/thân trên. DQK cung cấp phép đo body visibility, camera geometry và buổi cửa nhóm. Cross-camera re-ID còn cần dữ liệu robot.
- KR inject queue và state machine dùng chung vào pipeline của monitor. CLI sở hữu queue trong process của nó. Việc ghép với Phase3Runner trong PR #101 và ứng dụng tổng cần phối hợp KR.
- #111 đã bổ sung số đo workload RTX 4050 do DQK thực hiện và đề xuất chair-width. D3 reviewed ≥60 s, hai người và gallery ≥5 identities, D5 độc lập/per-class, F11 world truth, F7 raw latency, màn hình demo và full robot T2 còn chờ.

[Audit issue #111/#114](issues-111-114-2026-11-14.md), [hướng dẫn và API](PHASE2-LIVE-USAGE.md), [PR #115](https://github.com/DoanQuocKien/Autonomous-Collaborative-Sentry-Robot/pull/115).
