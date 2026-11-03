# HNHL — Tuần 5: tracking, target lock và GPU workload

Chuẩn bị/kiểm chứng **2026-11-01**, Asia/Bangkok, cho tuần 02–08/11. Nhánh `HuynhNguyenHoaiLoc/w05-tracking-gpu`, base **36cb701**. Phần triển khai và đo laptop đã có; **T1 D3 và RTX4050 còn chờ**, không đánh dấu toàn bộ tuần 5 đã nghiệm thu. [API/reproduction](W5-USAGE.md), [PR text](PR-W5-HNHL.md).

**Đối chiếu 03/11/2026:** [PR #92](https://github.com/DoanQuocKien/Autonomous-Collaborative-Sentry-Robot/pull/92) đã được review/merge ngày 02/11 tại `e487e97`. [Audit từng nhiệm vụ](midterm/week-05-audit.md): phần code hoàn thành, các T1 và extra FP16 rank-1 chưa hoàn tất. [Hồ sơ giữa kỳ](midterm/README.md) có Word 3 trang, F9/F10/F13 và [bổ sung 03/11](midterm/update-2026-11-03.md). Chưa có D3 mới hoặc combined workload RTX4050 để thay trạng thái nghiệm thu.

**Sau review/merge #96:** #93 KR và #95 HNHL đã merge; HNHL sửa các điểm checklist lỗi thời rồi approve/merge #96 tại `45765cf`. Nhóm controller/hold/ByteTrack/simulation: 26 passed (8,65s), không chạy hardware. [Ghi chú giữa kỳ sau merge](midterm/session-followup-2026-11-03.md) và [D3 handoff](midterm/D3-HANDOFF-HNHL.md) bổ sung đầu vào cần có cho buổi 04/11/09/11. T1/T2 còn thiếu giữ nguyên.

## Review và merge trước khi triển khai

Theo yêu cầu HNHL, đã review và merge PR DQK **#88 → #89 → #91 → #90**. Sửa trực tiếp vào #90 trước merge: không CHECK PASS nếu thiếu/nonfinite measurement, không nhận session gain đã withdrawn hoặc nonphysical, marker median có age limit 1 s, replay ghi analysis_summary thay vì ghi đè summary gốc. Calibration provisional top-level được đánh dấu unusable; snapshot lịch sử trong reports giữ nguyên.

Checkout kết hợp sau sửa: **569 CPU passed**, 3 skip do assets ở worktree riêng, 3 GPU deselected; targeted review 36 passed, common/jetson AST Python3.6 đạt. [Review/merge metadata](week-05/dqk_pr_reviews.json), [review tests](week-05/review_pytest.log). Approval cho code/evidence, không cấp ngoại lệ cho handshake 7/10 accepts và 9/10 rejects. Không chạy robot/hardware trong phiên này.

## Triển khai HNHL

- `sentry/perception/tracker.py`: YOLOv8n raw BGR → upstream Ultralytics ByteTrack → crop từng track đang được quan sát → OSNet-AIN/x0.25. Giữ low-confidence detections cho second association; không xuất lost Kalman predictions làm người đang thấy.
- Target lock: same model/hash, cosine threshold + separation margin, hai frame confirmation; không tin track ID đơn lẻ, không tự cập nhật target reference. Thiếu/mơ hồ → target None. Che khuất/đổi ID cần re-confirm. Seq reset/gap có epoch mới để ID tái sử dụng không thành cùng key.
- `set_target_record` nối Phase2 IntruderRecord thật của KR, từ chối vector simulated và model/hash khác. Threshold 0,70 vẫn provisional, chưa có calibration/re-lock accuracy D3.
- `tools.track_live` nhận latest VideoFrame của JetBot, không gửi motor commands. `tools.track_replay` chạy cùng API. Predicted boxes/IDs chỉ ghi dưới data/.
- `tools.evaluate_tracking`: aligned full-frame timestamps, Hungarian IoU matches, ID switches/min, misses/FP/recall và guard protocol. Empty tracker không tạo T1 PASS. Giới hạn plan ≤1 ID switch/phút trong cảnh hai người giữ nguyên.
- `tools.profile_pipeline`: đo model resident cùng lúc, NVML VRAM gồm Torch/ORT; face/entrance tùy chọn wall-clock schedule. `lap` và `nvidia-ml-py` khai báo dependencies; assets chuẩn bị trước, inference chặn download.

## Replay thật trên D2 hiện có

Đã chạy toàn bộ **822 frames** của ba clip cafe: **298 / 258 / 266**. Có output tracks trong **262 / 242 / 234** frames. Đây là workload/runtime trên ảnh thật, không phải body detection recall: ảnh có bystanders, không có body/track identity ground truth đầy đủ. Không đếm ID switches từ track ID tự sinh.

Không cung cấp reference nên mọi frame giữ lock UNSET, không tự chọn mục tiêu. Timestamp replay là uniform approximation từ độ dài clip, không phải capture timestamps đo được. Bbox/private predictions giữ trong data; chỉ aggregate [D2 runtime JSON](week-05/d2_tracking_runtime.json) được commit. **D3 chưa có; ID-switch T1 và target re-lock accuracy chưa đo.**

## GPU workload — RTX5060 Laptop, không thay target RTX4050

9 ảnh D2 làm input workload; model resident: YOLOv8n + ByteTrack + OSNet-AIN, YOLOv8n-pose, SCRFD/MobileFaceNet, XFeat, DINOv2-B ở chế độ both. Cùng ảnh phục vụ các model thay cho hai camera riêng. Body/face được pad ít nhất hai crop khi ít detections để không benchmark trên pipeline rỗng; pad là synthetic và không phải identity evidence. 5 warmup, 100 iterations; DINO FP16, Torch khác FP32.

| Cấu hình workload | FPS | p95/frame (ms) | NVML peak device-used (GiB) | So ≥15 FPS/≤5,5 GB decimal |
| :-- | --: | --: | --: | :-- |
| Đủ model, mọi stage mỗi frame | 12,719 | 90,751 | 0,939 | Chưa đạt FPS |
| XFeat, không DINO, mỗi frame | 14,245 | 82,986 | 0,622 | Chưa đạt FPS |
| Đủ model resident; face/entrance yêu cầu 5 Hz | 19,652 | 87,621 | 0,939 | Đạt cho workload đo trên máy này |

Run scheduled thực tế **4,520 door updates/s**, không ghi tròn thành 5 Hz. p95 vẫn cao vì các frame có stage cửa phải chạy nhiều model. Scheduler này hiện ở profiler, chưa tích hợp thành vòng main app. Các run tuần tự, không phải so sánh causal có kiểm soát nhiệt/power/clock. AC/battery của laptop chưa được người dùng xác nhận.

[All JSON](week-05/pipeline_both.json), [XFeat JSON](week-05/pipeline_xfeat.json), [scheduled JSON](week-05/pipeline_both_5hz.json), [F9 PNG](week-05/F9_pipeline_gpu.png). NVML device-used bao gồm ORT/Torch/driver/process khác, lấy mẫu 20 ms nên có thể bỏ lỡ spike ngắn; Torch peak allocated/reserved được tách riêng. Không suy ra transport latency hoặc RTX4050/GPU-budget T1 PASS từ số này. Mọi report giữ `t1_accepted=false`.

## Kiểm chứng và phần còn chờ

Logs cuối: [CPU](week-05/pytest_cpu.log) **584 passed**, 2 skipped (D1 checkerboard/entrance replay chưa có), 4 GPU deselected, **26,06 s**; [GPU](week-05/pytest_gpu.log) **4 passed**, 586 deselected, **8,94 s**. Tests gồm upstream ByteTrack high/low score, mất dấu, ID reuse, model hash mismatch, ties, confirmation/reacquisition, timestamp reset/gap, empty output không PASS, switch sau occlusion, false positives và protocol thiếu. GPU test chạy YOLO thật + ByteTrack + OSNet CUDA offline; dùng bbox synthetic tường minh để bảo đảm nhánh embedding/lock được thực thi, không claim accuracy. AST common/jetson Python3.6, CLI help và whitespace đạt. [Environment/source hashes](week-05/environment.json).

| Yêu cầu | Trạng thái |
| :-- | :-- |
| Tracker/OSNet target lock/re-lock code | Có API, CLI và tests |
| Live JetBot tracking | Có receive-only CLI; chưa chạy robot |
| D3 ≤1 ID switch/phút, hai người | Chờ DQK ghi D3 và reviewed IDs/visibility/timestamps |
| GPU budget toàn model | Có workload measurements RTX5060; RTX4050/live dual-stream còn chờ |
| Extra OSNet FP16 rank-1 trên Nano | Chờ D2/D3 gallery hợp lệ, engine/Nano; không dùng conversion cosine thay rank-1 |
| Báo cáo giữa kỳ | Có F9/F10/F13 và [hồ sơ Chương 5](midterm/README.md); F10 hiện là pilot ghế glossy, F7 CDF/F11/F14/F18 còn cần bằng chứng tương ứng |

Không có ảnh/crops/vector/private predictions/model artifacts mới trong PR. Không có motor commands. Không tự ghi timesheet. Review/merge PR #92 đã xong; full Definition of Done vẫn cần T1 thật nêu trên.
