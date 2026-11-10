# Gói sửa nội dung HNHL cho editor KR — 09/11/2026

**Đọc thêm nguồn10/11:** [failure/coverage ghế và các phương án range](update-2026-11-10.md) bổ sung0/36 distances, không phải0 error. Thêm failure này bên cạnh F10 cũ, tách gốc tape. Các thử trunk/depth còn một người/dev sets, không T1/T2 hay re-ID. Chương5 hiện hành đã nhận trạng thái này.

**Đã đối chiếu lại head969a5e0:** KR đã sửa phần lớn các dòng dưới (coverage, D5/Wire, FAR, deployment laptop, GPU scope và5 image links). Bảng giữ làm nội dung chuẩn để ghép, không nói các lỗi đó vẫn nguyên. Còn Chương7 distance “ĐẠT T1”, câu gửi appearance vector sang JetBot, F18 và caveats ranging DQK cần sửa/bổ sung. [Review bản mới](followup-pr101-2026-11-09.md).

Đối chiếu Chapter5 của PR #101 head `4d733af`. Bản draft nhóm là bước tổng hợp mới, chưa phải bản chốt. Dùng [Chương5 hiện hành](chapter-05-current.md), [bảng Chương7](chapter-07-rows.md), [F18](figures/F18_d5_precision.png) và [audit09/11](update-2026-11-09.md) để thay các đoạn dưới; Word01/11 vẫn là snapshot cũ, chưa export lại theo nội dung mới.

| Đoạn draft KR | Nội dung sửa để dùng trong báo cáo |
| :-- | :-- |
| “9 vị trí ghế đạt median5,34/p9020,91” | **8/9 IDs có distance**, ID21 thiếu do cắt mép; error trên estimates theo aggregation gốc. P90 tổng chưa đạt20%, chưa đủ≥20IDs/floor/session. Không bỏ missed ID |
| D5 mAP0,810, recallleg96%, Wire “thấp” | 397 ảnh,307train/90dev-val **cùng session**, đã dùng chọn model. E02: Wire recall0%; footwear/bag thiếu gate. Geometric fallback có failure, chưa phải giải pháp đã nghiệm thu. Không independent T1/T2 |
| Face TAR82,99% | Ghi kèm **FAR46,40% tại cosine0,45**,125frame/21entries/3người, nhãn tự động cần review và correlated pilot. Chưa TAR95%@FAR1% |
| “Trên robot, PersonTracker… đảm bảo đúng đối tượng” | PersonTracker/OSNet hiện chạy **trên laptop**; JetBot capture/motor. Thresholds provisional, lock/re-lock cần cùng model/hash, margin/confirmation. Chưa có real target-identity accuracy |
| “100% crossing tracks” | Là **synthetic backend ID agreement**, không ID-switch/min trên D3 hoặc re-ID rank-1. Gallery/query≥5 người và D3 reviewed≥60s hai người vẫn thiếu |
| “GPU RTX5060/4050 full mix, đáp ứng hoàn toàn” | Full-mix workload chỉ đo RTX5060, có synthetic body/face padding và sequential scheduler. 19,65FPS, actual door4,52Hz, sampled NVML0,939GiB; chưa live dual-stream/main-loop hoặc combined4050. RTX4050 đã có **single-model baseline** riêng, power limits khác |
| Thiếu F18 | Native PyTorch RTX5060: FP32/FP16 123,59/107,38FPS; p9512,01/16,35ms; Torch peak allocated32,41/17,53MiB; mAP5081,071/81,072%. Cùng90ảnh dev-val, chưa TensorRT/independent accuracy. Không kết luận FP16 tăng tốc |
| Live pursuit/HOLD và link-cut | DQK có pilot một người, range/tape mismatch và withdrawn hypotheses; video stop proxy481–524ms chưa motor-stop≤350ms. KR T0/replay không thay T2. Giữ protocol thiếu và review blockers |

## Sửa links theo thư mục của file reports/midterm_report_draft.md

Các đường dẫn sau là relative **từ reports/**, không thêm prefix `reports/` một lần nữa:

```text
F1  DoanQuocKien/week-05/figures/F1_system_overview.png
F15 DoanQuocKien/week-05/f15/F15_dead_reckoning.png
F10 HuynhNguyenHoaiLoc/midterm/figures/F10_distance.png
F13 HuynhNguyenHoaiLoc/midterm/figures/F13_face_roc.png
F9  HuynhNguyenHoaiLoc/midterm/figures/F9_gpu.png
F18 HuynhNguyenHoaiLoc/midterm/figures/F18_d5_precision.png
```

`F9_gpu_pie.png` không tồn tại trong evidence HNHL. Hình F9 thật là throughput/memory comparison, không phải pie phân bổ VRAM từng model. F15 là measured endpoints của các run, không ground-truth trajectory từng frame. Page-budget script theo word count chỉ là estimate; phải render/dàn trang để xác nhận10–15trang và kiểm tra figure assets/required chapters. Chương5 tổng3,5trang gồm KR/DQK; editor rút gọn và chọn hình, không cộng nguyên mọi addenda vào bản nộp.

Đã có code: converter và F18 trong PR #100, đang chờ DQK review. Các mục đó không còn “chưa viết/chưa đo”, nhưng D3/re-ID/world map/independent D5/combined4050 vẫn chưa được nghiệm thu. Các thay đổi scope matte/lịch trong #102 chưa merge nên ghi đúng là đề xuất của DQK, không tự coi là toàn nhóm đã chốt.
