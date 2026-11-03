# Bổ sung sau merge PR #96 ngày 03/11/2026

## Thay đổi đã được chấp thuận

| PR | Trạng thái được kiểm tra | Ý nghĩa với báo cáo |
| :-- | :-- | :-- |
| [#93 KR](https://github.com/DoanQuocKien/Autonomous-Collaborative-Sentry-Robot/pull/93) | Đã merge head `213f81e`, merge `8716668` | Controller/hold/vendored ByteTrack đã vào main. Sáu finding ở review HNHL cũ là lịch sử của head cũ; dùng bản đã sửa khi trình bày code. T0/simulation không thay D3 hoặc T2 robot |
| [#95 HNHL](https://github.com/DoanQuocKien/Autonomous-Collaborative-Sentry-Robot/pull/95) | Đã merge head `10600e0`, merge `4688965` | Hồ sơ Chương 5, hình và audit HNHL đã vào main; không tự hoàn thành các nghiệm thu đang thiếu |
| [#96 DQK](https://github.com/DoanQuocKien/Autonomous-Collaborative-Sentry-Robot/pull/96) | HNHL sửa checklist tại `43831ef`, approve rồi merge `45765cf` | Lịch chuẩn bị 04/11 tại nhà, 09/11 và 16/11 tại lớp đã có protocol; đây là công việc dự kiến, chưa phải kết quả các buổi đó |

[Metadata và hashes nguồn S01–S05](session-followup-2026-11-03.json), [review #96](../reviews/PR-96-2026-11-03.md), [26 tests passed](../reviews/PR-96-2026-11-03-tests.log). Đã chạy lại nhóm controller/hold/ByteTrack/simulation: 26 passed, 8,65s. CLI help và đường dẫn checklist đạt. Không chạy full app suite, không có motor commands hoặc phép đo T1 mới. Không dùng số 26 này thay log release HNHL 584 CPU/4 GPU hoặc dữ liệu thật D3.

## Các điểm cần giữ khi ghép Chương 5/7

- G2 / Stage A chưa được xây dựng theo checklist; fallback của plan là laptop path nếu gate không đạt. Nhóm quyết định và ghi lại ngày 09/11. Giữ kết quả benchmark Jetson đã có, không tự ghi Stage A hoàn thành hoặc tự xóa gate.
- Calibration ngày 30/10 vẫn withdrawn, `usable=false`; cần fit mới có measurement và CHECK độc lập theo floor. Không dùng gain sửa tay để hợp thức hóa một run. Self-pose phải đo lại khi đổi mount/handling.
- Handbook mới tách tracking hai người ≥60s (≤1 switch/phút) khỏi gallery/query re-ID ≥5 identities (rank-1≥85%). Buổi có ba người vẫn hữu ích cho pilot/live rehearsal, chưa đủ gate re-ID.
- [Bảng D5](update-2026-11-03.md) đã đối chiếu đủ §4.3: legs, footwear, backpacks **và bags** cần R≥90%, P≥80%; wire R≥80% và ≤1 alarm/20 empty-floor frames. Footwear/bag hiện thiếu P/R, wire recall 0% và chưa có empty-floor alarm metric. Các class đạt dev-val P/R vẫn còn full held-out/distance/T2 gates.
- F7 cần raw latency samples; F11 cần sweep pose/truth; F14 cần gallery/query hợp lệ; F18 cần paired accuracy/latency/memory. F15 measured endpoints của DQK không thay map/vantage F11. Không có thêm D3 hoặc T1 accuracy từ các PR tài liệu.

## HNHL tiếp tục sau các buổi thu thập

Đã chuẩn bị [hướng dẫn D3 bàn giao](D3-HANDOFF-HNHL.md), gồm folder private, timestamp/frame/identity/visibility contract, schema truth, lệnh replay/evaluate và giới hạn re-lock. Có dữ liệu thật thì review nhãn, freeze split và chạy các tool đã có; các schema ví dụ không phải evidence.

Trong buổi 04/11: ưu tiên D3, measurement metadata và D5 matte nếu có. Tại lớp 09/11: Phase 2 live, hai người pursuit/hold, D3 và overlay recordings nếu chạy được. RTX4050/FP16 profiling có thể làm trên laptop ngoài lớp, nhưng phải có evaluation input phù hợp. Figures freeze 16/11; phần còn thiếu được ghi pending cùng kế hoạch, không hạ gate.

Word/Markdown Chương 5 ngày 01/11 giữ nguyên bản đã render; editor ghép bản đó cùng addendum 03/11 và ghi chú sau merge này. Không tạo báo cáo giả về các buổi chưa diễn ra.
