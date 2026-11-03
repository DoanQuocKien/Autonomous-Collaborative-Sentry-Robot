# Đối chiếu nhiệm vụ tuần 5 HNHL ngày 03/11/2026

**Kết luận: phần triển khai laptop đã merge, nhưng chưa hoàn tất nghiệm thu tuần 5.** Tuần 5 theo plan là 02–08/11; buổi robot tiếp theo ghi trong plan là 09/11. Definition of Done yêu cầu cả code đã review/merge, tests đúng tầng đạt và evidence trong weekly report. Merge PR không tự hoàn thành T1 còn thiếu.

Nguồn phân công: [Implementation Plan — Week 5 và Definition of Done](../../../docs/Implementation%20Plan.md). Nguồn GitHub tại lúc kiểm tra: [snapshot 03/11](github-2026-11-03.json).

Cập nhật sau merge #96: [metadata mới](session-followup-2026-11-03.json) xác nhận #93/#95/#96 đã merge; snapshot trước đó giữ nguyên để truy vết. Các nghiệm thu dữ liệu thật dưới đây vẫn chưa có kết quả mới.

| Nhiệm vụ HNHL | Bằng chứng hiện có | Đánh giá |
| :-- | :-- | :-- |
| YOLOv8 + ByteTrack trên stream JetBot | `PersonTracker`, `tools.track_live`, `tools.track_replay`; [PR #92](https://github.com/DoanQuocKien/Autonomous-Collaborative-Sentry-Robot/pull/92) đã merge ngày 02/11 tại `e487e97` | Code xong; live JetBot chưa chạy trong phiên HNHL |
| OSNet target lock và re-lock sau occlusion | Same model/hash, cosine + margin, hai frame confirmation, target None khi mơ hồ, epoch reset/gap; tests W5 | Logic/contract xong; thresholds provisional và re-lock accuracy trên người thật chưa đo |
| GPU profiling toàn model cùng nạp | Ba workload RTX5060, có NVML/Torch memory, cadence và actual door Hz; F9 | Đo laptop đã có; RTX4050 combined/live dual-stream chưa có |
| T1 ID switches trên D3 | Có evaluator protocol/full-frame matching; D2 runtime 822 frame không có body-ID truth | Chưa xong: thiếu D3 hai người, reviewed IDs/visibility và timestamps; mục tiêu ≤1 switch/phút chưa nghiệm thu |
| T1 GPU ≥15 FPS / ≤5,5 GB decimal | Scheduled workload 19,65 FPS, 0,939 GiB, actual door 4,52Hz trên RTX5060; hai mode mọi-stage mỗi frame dưới 15 FPS | Chỉ đạt workload đã ghi; chưa đạt Definition of Done cho target RTX4050 và live loop |
| Extra: OSNet x0.25/AIN TensorRT FP16 rank-1 | Có code hai encoder và conversion parity stock; gallery D2 hiện thiếu 2/3 người | Chưa xong: cần gallery/query hợp lệ ≥5 identities, đúng hash/architecture và inference Nano; cosine parity không thay rank-1 |
| Báo cáo giữa kỳ và hình HNHL | Word 3 trang, Markdown, F9/F10/F13, Ch7 rows, appendix, bổ sung 03/11 và F9 single-model | Bản đóng góp dùng được để editor ghép; F7 CDF/F11/F14/F18 còn chờ, cần rút gọn cùng KR/DQK theo page budget |
| Review PR KR | Request changes HNHL cho head `0239832`; bản sửa cuối `213f81e` đã merge qua #93 | Code mới vào main; 26 controller/hold/ByteTrack tests được chạy lại trong lần review #96. Chưa phải D3/T2 |

Logs W5 hiện có: [584 CPU passed](../week-05/pytest_cpu.log), [4 GPU passed](../week-05/pytest_gpu.log), không chạy lại inference trong lần biên soạn này. Suite review #93 đạt 605 CPU tests thuộc checkout tích hợp riêng, không được thay log release W5 của HNHL.

## Việc có thể làm ngay và phần cần dữ liệu

- Đã bổ sung baseline RTX4050 từng model từ evidence DQK, bảng D5 precision/recall đầy đủ, log video/watchdog/e-stop, runtime Jetson + freshness ESP32 và nguồn F15 đo thật vào [bản bổ sung giữa kỳ](update-2026-11-03.md).
- D3: DQK ghi JetBot một/hai người, đi–dừng–che khuất–giao nhau. Cần ≥60s phù hợp protocol, reviewed body IDs/visibility, đủ empty frames và timestamp. Khi nhận được sẽ replay/evaluate bằng tool đã có, kiểm tra ID switches và target re-lock riêng.
- GPU: cần máy RTX4050 chạy cùng resident-model workload/cadence và protocol nguồn điện đã ghi; baseline single-model sẵn có không thay phép đo này.
- Extra FP16 rank-1: cần gallery/query đúng re-ID protocol và engine/runtime Nano, giữ model hashes/preprocessing; không chọn winner từ tập không đủ gallery.
- F11 cần sweep có poses/truth/door range; F7 CDF cần raw latency samples; F18 cần paired FP32/FP16 latency/memory/accuracy trên cùng tập. Không tạo các hình này từ dữ liệu giả.

Không thấy D3 hoặc gallery mới trong nguồn repo/data và tên gói Downloads đã kiểm tra. D2 vẫn là batch 28/10, D5 vẫn batch 24/10; không coi metadata GitHub hoặc hình F15 mới là dữ liệu re-ID bổ sung. Lộ trình chi tiết: [update-checklist.md](update-checklist.md).
