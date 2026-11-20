# HNHL bổ sung giữa kỳ ngày 21 tháng 11

Hồ sơ HNHL còn ghi #113 đang chờ review và F7 thiếu raw CSV. Sau merge #113/#132/#133, bổ sung trạng thái hiện tại, kết quả robot ngày 20/11 và dữ liệu latency thật đã có của DQK để editor chốt Chương 5/7 trước ngày nộp 23/11.

- Thêm addendum, GitHub snapshot và JSON tái lập từ 38 nguồn Git pin ở `55ddfc8`.
- Đối chiếu CSV find-door/handshake/frame/tape note, hai pursuit diagnostics, approach và pose tháp. STANDBY 56,317 s; pursuit distance-in-band 9,4%/18,1%, chưa đạt 80%.
- Tính lại F7 từ raw clocks: 2.351/2.325 frame, 19,588/19,391 FPS, p95 127,923/127,755 ms. F7 đã có dữ liệu; FPS/p95 vẫn chưa đạt, sequence gaps không là packet loss.
- Cập nhật README, checklist, báo cáo tuần 7 và điểm vào Chương 5. Giữ rõ #114 đã đóng là workflow status; full door T1, D3/gallery, D5 độc lập, F11 và RTX4050 precision accuracy vẫn chưa nghiệm thu.
- Mở rộng checker để kiểm tra snapshot mới; thêm regression từ chối sai CSV/summary/state/timestamp/tape và mutable refs. Giữ các snapshot đóng băng theo ngày để truy vết.

Kiểm chứng trên `.venv` HNHL: **12 passed**, 4,12 s; checker đối chiếu 38 nguồn mới, các nguồn lịch sử, hash Word và toàn bộ liên kết nội bộ. Build JSON hai lần có cùng bytes; `git diff --check` đạt. [Bản bổ sung](midterm/update-2026-11-21.md), [log](week-07/review-2026-11-21/tests_midterm.txt), [checker](week-07/review-2026-11-21/midterm_check.json).

Không có inference, camera/motor trial hoặc accuracy benchmark mới trong PR này. Các số CPU/replay 973 passed/PDF/package trong addendum thuộc review #133 đã merge và được ghi rõ candidate. Tag `midterm`, owner sign-off và video tùy chọn thuộc bước chốt của nhóm; không tự tạo tag nộp bài trong PR này.

Refs #111. Reviewers: DQK và KR.
